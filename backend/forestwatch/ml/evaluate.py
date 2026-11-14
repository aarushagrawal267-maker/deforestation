"""Full-region evaluation on geographically held-out regions.

Two kinds of numbers are produced and must be read differently:
  * agreement with the model-generated reference labels (WorldCover-derived);
  * agreement with Hansen GFC tree cover (Landsat-based, independent algorithm).
Neither is accuracy against independent ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ..geo.raster_io import read_stack, write_cog
from ..labels.classes import CLASS_NAMES, IGNORE, NUM_CLASSES, TREE
from .dataset import load_region
from .infer import load_checkpoint, predict_probs
from .metrics import binary_metrics, confusion, metrics_from_confusion


def hansen_tree_reference(regions_dir: Path, name: str, year: int, threshold: int = 30) -> tuple[np.ndarray, np.ndarray]:
    """Hansen-derived tree cover for ``year``: treecover2000 >= threshold and no loss up to ``year``."""
    tc, _, _ = read_stack(regions_dir / name / "hansen_treecover2000.tif")
    loss, _, _ = read_stack(regions_dir / name / "hansen_lossyear.tif")
    tc, loss = tc[0], loss[0]
    valid = tc != 255
    lost = (loss > 0) & (loss <= year - 2000)
    return (tc >= threshold) & ~lost, valid


def _block_mode(a: np.ndarray, f: int = 3) -> np.ndarray:
    H, W = (a.shape[0] // f) * f, (a.shape[1] // f) * f
    return a[:H, :W].reshape(H // f, f, W // f, f).mean(axis=(1, 3))


def evaluate_checkpoint(ckpt_path: Path, regions_dir: Path, region_names: list[str], out_dir: Path, progress=None) -> dict:
    model, ckpt = load_checkpoint(ckpt_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    total_cm = np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64)
    per_region = []
    hansen_all = {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    for i, name in enumerate(region_names):
        r = load_region(regions_dir / name, ckpt["bands"])
        probs = predict_probs(model, r.refl, ckpt["norm_stats"], ckpt.get("temperature", 1.0))
        valid_px = np.isfinite(probs).all(axis=0)
        pred = np.where(valid_px, np.nan_to_num(probs).argmax(axis=0), IGNORE).astype(np.uint8)
        target = np.where(valid_px, r.labels, IGNORE)
        cm = confusion(pred, target, NUM_CLASSES)
        total_cm += cm
        m = metrics_from_confusion(cm, CLASS_NAMES)

        # Hansen agreement at ~30 m (3x3 block aggregation of 10 m predictions)
        year = int(r.meta.get("label_year", 2021))
        href, hvalid = hansen_tree_reference(regions_dir, name, year)
        tree_frac = _block_mode(np.where(valid_px, pred == TREE, 0).astype(np.float32))
        valid_frac = _block_mode(valid_px.astype(np.float32))
        h_frac = _block_mode(href.astype(np.float32))
        hv = _block_mode(hvalid.astype(np.float32)) == 1
        v = (valid_frac == 1) & hv
        hm = binary_metrics(tree_frac >= 0.5, h_frac >= 0.5, v)
        for k in hansen_all:
            hansen_all[k] += hm[k]

        # Save prediction and comparison rasters for the evaluation page
        from ..geo.grid import Grid

        grid = Grid.from_dict(r.meta["grid"])
        write_cog(out_dir / f"{name}_pred.tif", pred, grid, nodata=IGNORE, resampling_overview="nearest")
        per_region.append(
            {
                "region": name,
                "reference_agreement": m,
                "hansen_tree_agreement": hm,
                "valid_fraction": float(valid_px.mean()),
                "scene_ids": r.meta.get("scene_ids"),
            }
        )
        if progress:
            progress((i + 1) / len(region_names), f"evaluated {name}")

    def agg(d):
        tp, fp, fn, tn = d["tp"], d["fp"], d["fn"], d["tn"]
        p = tp / (tp + fp) if tp + fp else None
        rc = tp / (tp + fn) if tp + fn else None
        return {
            "precision": p,
            "recall": rc,
            "f1": 2 * p * rc / (p + rc) if p and rc else None,
            "iou": tp / (tp + fp + fn) if tp + fp + fn else None,
            "accuracy": (tp + tn) / max(1, tp + fp + fn + tn),
            **d,
        }

    result = {
        "checkpoint": str(ckpt_path),
        "regions": region_names,
        "overall_reference_agreement": metrics_from_confusion(total_cm, CLASS_NAMES),
        "overall_hansen_tree_agreement": agg(hansen_all),
        "per_region": per_region,
        "calibration": ckpt.get("calibration"),
        "notes": [
            "Reference agreement compares predictions with WorldCover-derived labels, which are themselves model outputs.",
            "Hansen agreement compares the tree class with Hansen treecover2000>=30% minus loss up to the label year, at ~30 m.",
            "Ignored pixels (class boundaries, recent loss, clouds) are excluded from all metrics.",
        ],
    }
    (out_dir / "evaluation.json").write_text(json.dumps(result, indent=2))
    return result
