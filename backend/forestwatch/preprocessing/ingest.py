"""Turn a Sentinel-2 L2A scene (or several, as a composite) into an analysis-ready product.

Output, on the AOI's shared 10 m UTM grid:
  stack.tif    int16, 10 bands, surface reflectance x 10000 (nodata -32768)
  quality.tif  uint8 quality codes (see masking.QUALITY_NAMES)
  meta.json    provenance (scene ids, baseline, scaling, masking, resampling)
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

from ..geo.grid import Grid
from ..geo.raster_io import read_onto_grid, read_stack, write_cog
from ..providers.base import SceneInfo
from ..settings import configure_gdal_env
from .bands import BAND_NAMES, BANDS
from .masking import Q_VALID, build_quality, dn_to_reflectance, offset_for_baseline, quality_summary

NODATA_I16 = -32768
REFL_SCALE = 10000.0


def read_scene(scene: SceneInfo, grid: Grid, progress=None) -> tuple[np.ndarray, np.ndarray]:
    """Return (reflectance float32 (10,H,W) with NaN for nodata, quality uint8 (H,W))."""
    configure_gdal_env()
    keys = [b.asset for b in BANDS]
    missing = [k for k in keys + ["scl"] if k not in scene.assets]
    if missing:
        raise ValueError(f"Scene {scene.id} is missing assets {missing}")

    def _read(key: str) -> np.ndarray:
        if key in ("scl", "cloud"):
            return read_onto_grid(scene.assets[key], grid, Resampling.nearest, dst_nodata=0)
        return read_onto_grid(scene.assets[key], grid, Resampling.bilinear, src_nodata=0, dst_nodata=0)

    all_keys = keys + ["scl"] + (["cloud"] if "cloud" in scene.assets else [])
    results: dict[str, np.ndarray] = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        for i, (k, arr) in enumerate(zip(all_keys, ex.map(_read, all_keys))):
            results[k] = arr
            if progress:
                progress((i + 1) / len(all_keys), f"read {k}")

    dn = np.stack([results[k] for k in keys])
    offset = offset_for_baseline(scene.processing_baseline, scene.collection)
    refl = dn_to_reflectance(dn, offset=offset)
    nodata = (dn == 0).any(axis=0)
    q = build_quality(results["scl"], nodata, results.get("cloud"))
    refl[:, q != Q_VALID] = np.nan
    return refl, q


def save_product(
    out_dir: Path,
    refl: np.ndarray,
    quality: np.ndarray,
    grid: Grid,
    meta: dict,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    i16 = np.where(np.isfinite(refl), np.clip(np.round(refl * REFL_SCALE), -32767, 32767), NODATA_I16).astype(
        np.int16
    )
    write_cog(out_dir / "stack.tif", i16, grid, nodata=NODATA_I16, band_names=BAND_NAMES)
    write_cog(out_dir / "quality.tif", quality, grid, resampling_overview="nearest")
    qs = quality_summary(quality)
    meta = {
        **meta,
        "grid": grid.to_dict(),
        "bands": BAND_NAMES,
        "reflectance_scale": 1 / REFL_SCALE,
        "nodata": NODATA_I16,
        "quality_summary": qs,
        "valid_fraction": qs["valid"],
        "created_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return meta


def group_by_acquisition(scenes: list[SceneInfo]) -> list[list[SceneInfo]]:
    """Group scenes of the same platform and day (adjacent MGRS tiles of one overpass)."""
    groups: dict[tuple, list[SceneInfo]] = {}
    for s in scenes:
        groups.setdefault((s.platform, s.datetime.date()), []).append(s)
    return list(groups.values())


def read_mosaic(scenes: list[SceneInfo], grid: Grid, progress=None) -> tuple[np.ndarray, np.ndarray]:
    """Same-day mosaic: pixels invalid in one tile are filled from the next tile."""
    refl, q = read_scene(scenes[0], grid, progress)
    for s in scenes[1:]:
        if (q == Q_VALID).all():
            break
        r2, q2 = read_scene(s, grid)
        fill = (q != Q_VALID) & ((q2 == Q_VALID) | (q == 1))
        refl[:, fill] = r2[:, fill]
        q[fill] = q2[fill]
    return refl, q


def ingest_scene(scene: SceneInfo | list[SceneInfo], grid: Grid, out_dir: Path, progress=None) -> dict:
    scenes = scene if isinstance(scene, list) else [scene]
    refl, q = read_mosaic(scenes, grid, progress)
    scene = scenes[0]
    meta = {
        "kind": "scene" if len(scenes) == 1 else "same_day_mosaic",
        "scene_ids": [s.id for s in scenes],
        "acquired": [scene.datetime.isoformat()],
        "provider": scene.provider,
        "collection": scene.collection,
        "processing_baselines": [s.processing_baseline for s in scenes],
        "platform": scene.platform,
        "mgrs_tile": ",".join(str(s.mgrs_tile) for s in scenes),
        "scene_cloud_cover": scene.cloud_cover,
        "source_assets": {s.id: s.assets for s in scenes},
        "processing": [
            "windowed read of COG band assets onto shared UTM 10 m grid (rasterio WarpedVRT)",
            "10 m bands: bilinear (grid-aligned, effectively unchanged); 20 m bands: bilinear "
            "upsampling to 10 m (no new spatial information)",
            "SCL and cloud-probability: nearest neighbour",
            f"reflectance = DN * 1e-4 + ({offset_for_baseline(scene.processing_baseline, scene.collection)})",
            "masked: SCL 0,1 (no data), 3 (shadow), 8,9,10 (cloud/cirrus), cloud prob >= 40%, "
            "2,11 (dark/snow, low quality), 4 px (40 m) dilation buffer around clouds and shadows",
        ],
        "attribution": f"Contains modified Copernicus Sentinel data {scene.datetime.year}",
    }
    return save_product(out_dir, refl, q, grid, meta)


def composite(product_dirs: list[Path], out_dir: Path, meta_extra: dict | None = None) -> dict:
    """Per-pixel median of valid observations across several analysis-ready products."""
    stacks, metas, grid = [], [], None
    for d in product_dirs:
        data, g, _ = read_stack(d / "stack.tif")
        if grid is None:
            grid = g
        elif g.to_dict() != grid.to_dict():
            raise ValueError("All products in a composite must share the same grid")
        stacks.append(np.where(data == NODATA_I16, np.nan, data / REFL_SCALE).astype(np.float32))
        metas.append(json.loads((d / "meta.json").read_text()))
    arr = np.stack(stacks)  # (n, bands, H, W)
    with np.errstate(all="ignore"):
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            med = np.nanmedian(arr, axis=0)
    n_valid = np.isfinite(arr[:, 0]).sum(axis=0)
    q = np.where(n_valid > 0, Q_VALID, 1).astype(np.uint8)
    meta = {
        "kind": "composite",
        "scene_ids": sum((m["scene_ids"] for m in metas), []),
        "acquired": sum((m["acquired"] for m in metas), []),
        "provider": metas[0]["provider"],
        "collection": metas[0]["collection"],
        "processing_baselines": sum((m["processing_baselines"] for m in metas), []),
        "processing": metas[0]["processing"]
        + [f"per-pixel median of valid observations across {len(metas)} acquisitions"],
        "observations_per_pixel": {"min": int(n_valid.min()), "max": int(n_valid.max())},
        "attribution": metas[0]["attribution"],
        **(meta_extra or {}),
    }
    return save_product(out_dir, med, q, grid, meta)


def load_product(product_dir: Path) -> tuple[np.ndarray, np.ndarray, Grid, dict]:
    """Return (reflectance float32 with NaN, quality, grid, meta)."""
    data, grid, _ = read_stack(product_dir / "stack.tif")
    refl = np.where(data == NODATA_I16, np.nan, data / REFL_SCALE).astype(np.float32)
    q, _, _ = read_stack(product_dir / "quality.tif")
    meta = json.loads((product_dir / "meta.json").read_text())
    return refl, q[0], grid, meta
