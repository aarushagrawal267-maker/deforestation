"""High-level analysis pipelines used by the API worker and the CLI.

segment_product: analysis-ready product + checkpoint -> probability / class / uncertainty maps
detect_change:   two (or more) products + checkpoint -> change categories + attributed regions
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from .change.compare import (
    CATEGORIES,
    INVALID,
    POTENTIAL_GAIN,
    POTENTIAL_LOSS,
    ChangeParams,
    category_areas,
    classify_change,
)
from .change.coregister import apply_shift, estimate_shift
from .change.polygons import vectorize_regions
from .geo.grid import Grid
from .geo.raster_io import read_stack, write_cog
from .labels.classes import CLASS_NAMES, CLASSES, TREE, WORLDCOVER_NAMES
from .labels.reference import HANSEN_LAST_YEAR, HANSEN_VERSION, hansen_on_grid, worldcover_on_grid
from .ml.infer import entropy, file_sha256, load_checkpoint, predict_probs
from .preprocessing.bands import BAND_NAMES
from .preprocessing.indices import compute_indices
from .preprocessing.ingest import load_product

PROB_SCALE = 250.0
NODATA_U8 = 255


def _to_u8(p: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(p), np.round(np.clip(p, 0, 1) * PROB_SCALE), NODATA_U8).astype(np.uint8)


def _from_u8(a: np.ndarray) -> np.ndarray:
    return np.where(a == NODATA_U8, np.nan, a / PROB_SCALE).astype(np.float32)


def _select_bands(refl: np.ndarray, names: list[str], bands: list[str]) -> np.ndarray:
    return refl[[names.index(b) for b in bands]]


def segment_product(product_dir: Path, checkpoint: Path, out_dir: Path, progress=None, shift: tuple[float, float] | None = None) -> dict:
    model, ckpt = load_checkpoint(checkpoint)
    refl, q, grid, pmeta = load_product(product_dir)
    if shift:
        refl = apply_shift(refl, *shift)
    x = _select_bands(refl, pmeta["bands"], ckpt["bands"])
    probs = predict_probs(model, x, ckpt["norm_stats"], ckpt.get("temperature", 1.0), progress=progress)
    ent = entropy(probs)
    valid = np.isfinite(probs).all(axis=0)
    cls = np.where(valid, np.nan_to_num(probs).argmax(axis=0), NODATA_U8).astype(np.uint8)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_cog(out_dir / "probs.tif", _to_u8(probs), grid, nodata=NODATA_U8, band_names=CLASS_NAMES)
    write_cog(out_dir / "class.tif", cls, grid, nodata=NODATA_U8, resampling_overview="nearest")
    write_cog(out_dir / "entropy.tif", _to_u8(ent), grid, nodata=NODATA_U8)

    px_ha = grid.res**2 / 1e4
    tree_p = probs[TREE]
    tree_px = int((valid & (tree_p >= 0.5)).sum())
    summary = {
        "valid_fraction": float(valid.mean()),
        "valid_area_ha": float(valid.sum() * px_ha),
        "tree_cover_ha": tree_px * px_ha,
        "tree_cover_fraction_of_valid": tree_px / max(1, int(valid.sum())),
        "tree_cover_uncertain_ha": float((valid & (tree_p > 0.4) & (tree_p < 0.6)).sum() * px_ha),
        "class_areas_ha": {CLASSES[c]["key"]: float(((cls == c)).sum() * px_ha) for c in range(len(CLASSES))},
        "mean_entropy": float(np.nanmean(ent)) if valid.any() else None,
        "area_note": "Mapped area = count of 10 m pixels with calibrated P(tree) >= 0.5 among valid pixels. "
        "Pixels with 0.4 < P < 0.6 are reported separately as uncertain. Not a sample-based area estimate.",
    }
    meta = {
        "kind": "segmentation",
        "product": str(product_dir),
        "product_acquired": pmeta.get("acquired"),
        "scene_ids": pmeta.get("scene_ids"),
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": file_sha256(checkpoint),
        "temperature": ckpt.get("temperature", 1.0),
        "calibrated": "calibration" in ckpt,
        "bands": ckpt["bands"],
        "grid": grid.to_dict(),
        "shift_applied_px": shift,
        "summary": summary,
        "created_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return meta


def load_segmentation(seg_dir: Path) -> tuple[np.ndarray, np.ndarray, Grid, dict]:
    probs, grid, _ = read_stack(seg_dir / "probs.tif")
    ent, _, _ = read_stack(seg_dir / "entropy.tif")
    return _from_u8(probs), _from_u8(ent[0]), grid, json.loads((seg_dir / "meta.json").read_text())


def _year(iso: str) -> int:
    return int(iso[:4])


def detect_change(
    product_dirs: list[Path],
    checkpoint: Path,
    out_dir: Path,
    params: ChangeParams | None = None,
    run_id: str = "RUN",
    progress=None,
    log=print,
) -> dict:
    """Compare the first and second products; any further products are used for persistence."""
    params = params or ChangeParams()
    if len(product_dirs) < 2:
        raise ValueError("At least two observations are required")
    out_dir.mkdir(parents=True, exist_ok=True)
    prog = progress or (lambda f, m: None)

    r1, q1, g1, m1 = load_product(product_dirs[0])
    r2, q2, g2, m2 = load_product(product_dirs[1])
    if g1.to_dict() != g2.to_dict():
        raise ValueError("Observations are not on the same grid; ingest both for the same AOI")
    if m1["acquired"][0] >= m2["acquired"][0]:
        raise ValueError("The earlier observation must be acquired before the later one")

    # 1. residual co-registration
    nir = BAND_NAMES.index("B8")
    shift = estimate_shift(r1[nir], r2[nir])
    applied = None
    if shift["magnitude"] > params.coreg_max_shift_px and shift["response"] > 0.05:
        applied = (shift["dx"], shift["dy"])
        log(f"Residual shift {shift['magnitude']:.2f} px detected; aligning later observation")
        r2 = apply_shift(r2, *applied)
    prog(0.05, "co-registration checked")

    # 2. segmentation of both dates with the same checkpoint
    seg_dirs = []
    for i, pd in enumerate(product_dirs):
        sd = out_dir / f"seg_{i}"
        segment_product(
            pd,
            checkpoint,
            sd,
            progress=lambda f, m, i=i: prog(0.05 + 0.6 * (i + f) / len(product_dirs), f"segmenting date {i + 1}: {m}"),
            shift=applied if i == 1 else None,
        )
        seg_dirs.append(sd)
    p1, e1, _, s1 = load_segmentation(seg_dirs[0])
    p2, e2, _, s2 = load_segmentation(seg_dirs[1])

    # 3. spectral indices
    i1, i2 = compute_indices(r1), compute_indices(r2)
    d_idx = {k: i2[k] - i1[k] for k in i1}

    # 4. classification
    cat, aux = classify_change(p1[TREE], p2[TREE], e1, e2, d_idx["NDVI"], d_idx["NBR"], params)
    prog(0.7, "change classified")

    # 5. persistence with later observations
    persistence = None
    if len(seg_dirs) > 2:
        later = [load_segmentation(sd)[0][TREE] for sd in seg_dirs[2:]]
        stack = np.stack(later)
        observed = np.isfinite(stack)
        still_nonforest = (np.nan_to_num(stack, nan=1) <= params.forest_lo) & observed
        persistence = {
            "persistent": still_nonforest.any(axis=0) & ~((np.nan_to_num(stack, nan=0) >= params.forest_hi) & observed).any(axis=0),
            "observed": observed.any(axis=0),
        }

    # 6. reference data on the grid
    y1, y2 = _year(m1["acquired"][0]), _year(m2["acquired"][-1])
    hansen_loss = None
    hansen_note = None
    try:
        hl = hansen_on_grid(g1, "lossyear")
        if y1 <= HANSEN_LAST_YEAR:
            codes = list(range(max(1, y1 - 2000), min(HANSEN_LAST_YEAR, y2) - 2000 + 1))
            hansen_loss = np.isin(hl, codes)
            hansen_note = f"Hansen {HANSEN_VERSION} loss years {2000 + codes[0]}-{2000 + codes[-1]}" if codes else None
            if y2 > HANSEN_LAST_YEAR:
                hansen_note = (hansen_note or "") + f" (no Hansen data after {HANSEN_LAST_YEAR})"
        else:
            hansen_note = f"Hansen {HANSEN_VERSION} ends in {HANSEN_LAST_YEAR}; no corroboration possible"
    except Exception as e:  # network failure must not break the analysis
        hansen_note = f"Hansen data unavailable: {e}"
    wc_year = 2021 if y1 >= 2021 else 2020
    try:
        wc = worldcover_on_grid(g1, wc_year)
    except Exception:
        wc = None
    prog(0.8, "reference data loaded")

    # 7. polygons
    invalid = cat == INVALID
    attrs = {
        "p_tree_before": p1[TREE],
        "p_tree_after": p2[TREE],
        "delta_p_tree": aux["dp"],
        "delta_ndvi": d_idx["NDVI"],
        "delta_nbr": d_idx["NBR"],
        "delta_ndmi": d_idx["NDMI"],
        "ndvi_before": i1["NDVI"],
        "ndvi_after": i2["NDVI"],
        "nbr_before": i1["NBR"],
        "nbr_after": i2["NBR"],
        "ndmi_before": i1["NDMI"],
        "ndmi_after": i2["NDMI"],
        "entropy_before": e1,
        "entropy_after": e2,
        "spectral_support_fraction": aux["spectral_support"].astype(np.float32),
        "fire_like_fraction": aux["fire_like"].astype(np.float32),
    }
    if hansen_loss is not None:
        attrs["hansen_loss_fraction"] = hansen_loss.astype(np.float32)
    if persistence is not None:
        attrs["persistence_fraction"] = np.where(persistence["observed"], persistence["persistent"], np.nan).astype(np.float32)
    if wc is not None:
        attrs["worldcover_tree_fraction"] = np.where(wc > 0, wc == 10, np.nan).astype(np.float32)

    loss_feats = vectorize_regions(cat == POTENTIAL_LOSS, g1, params.min_mapping_unit_ha, attrs, invalid, f"{run_id}-L")
    gain_feats = vectorize_regions(cat == POTENTIAL_GAIN, g1, params.min_mapping_unit_ha, attrs, invalid, f"{run_id}-G")

    for f in loss_feats:
        p = f["properties"]
        p["change_type"] = "potential_loss"
        level = "potential"
        if (p.get("spectral_support_fraction") or 0) >= 0.5:
            level = "spectrally_supported"
        if (p.get("hansen_loss_fraction") or 0) >= 0.3:
            level = "corroborated_hansen"
        p["evidence_level"] = level
        p["possible_fire_related"] = (p.get("fire_like_fraction") or 0) >= 0.5
        if persistence is not None:
            p["persistent"] = (p.get("persistence_fraction") or 0) >= 0.5
        p["date_before"] = m1["acquired"][0]
        p["date_after"] = m2["acquired"][0]
    for f in gain_feats:
        f["properties"]["change_type"] = "potential_gain"
        f["properties"]["evidence_level"] = "potential"
        f["properties"]["date_before"] = m1["acquired"][0]
        f["properties"]["date_after"] = m2["acquired"][0]

    # 8. rasters
    write_cog(out_dir / "category.tif", cat, g1, resampling_overview="nearest")
    dp_i8 = np.where(np.isfinite(aux["dp"]), np.round(aux["dp"] * 100), -128).astype(np.int8)
    write_cog(out_dir / "delta_p_tree.tif", dp_i8, g1, nodata=-128)
    write_cog(
        out_dir / "delta_indices.tif",
        np.stack([np.where(np.isfinite(d_idx[k]), np.round(d_idx[k] * 1000), -32768).astype(np.int16) for k in ("NDVI", "NBR", "NDMI")]),
        g1,
        nodata=-32768,
        band_names=["dNDVI_x1000", "dNBR_x1000", "dNDMI_x1000"],
    )
    fc = {"type": "FeatureCollection", "features": loss_feats + gain_feats}
    (out_dir / "regions.geojson").write_text(json.dumps(fc))

    areas = category_areas(cat, g1.res**2)
    valid_frac = 1 - areas["invalid"]["fraction"]
    loss_area = sum(f["properties"]["area_ha"] for f in loss_feats)
    loss_unc = sum(f["properties"]["area_uncertainty_ha"] for f in loss_feats)
    gain_area = sum(f["properties"]["area_ha"] for f in gain_feats)
    summary = {
        "run_id": run_id,
        "date_before": m1["acquired"],
        "date_after": m2["acquired"],
        "persistence_dates": [json.loads((pd / "meta.json").read_text())["acquired"] for pd in product_dirs[2:]],
        "scene_ids_before": m1["scene_ids"],
        "scene_ids_after": m2["scene_ids"],
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": s1["checkpoint_sha256"],
        "calibrated": s1["calibrated"],
        "coregistration": {**shift, "applied": applied is not None},
        "params": params.to_dict(),
        "category_areas": areas,
        "valid_fraction_both_dates": valid_frac,
        "tree_cover_before_ha": s1["summary"]["tree_cover_ha"],
        "tree_cover_after_ha": s2["summary"]["tree_cover_ha"],
        "potential_loss_ha": loss_area,
        "potential_loss_uncertainty_ha": loss_unc,
        "potential_gain_ha": gain_area,
        "n_loss_regions": len(loss_feats),
        "n_gain_regions": len(gain_feats),
        "evidence_counts": {
            lvl: sum(1 for f in loss_feats if f["properties"]["evidence_level"] == lvl)
            for lvl in ("potential", "spectrally_supported", "corroborated_hansen")
        },
        "hansen_reference": hansen_note,
        "worldcover_reference": f"ESA WorldCover {wc_year}" if wc is not None else None,
        "grid": g1.to_dict(),
        "categories": CATEGORIES,
        "area_note": "Region areas are geodesic areas of the vectorised mapped pixels (minimum mapping unit "
        f"{params.min_mapping_unit_ha} ha). Uncertainty = perimeter x half a pixel (boundary placement only); "
        "classification errors are not included. These are potential changes, not verified deforestation.",
        "created_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    prog(1.0, "done")
    return summary


def worldcover_name(code: int) -> str:
    return WORLDCOVER_NAMES.get(code, "unknown")
