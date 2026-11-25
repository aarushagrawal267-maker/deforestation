"""Reference baselines and sampling uncertainty for the held-out test evaluation.

``evaluate_checkpoint`` reports point estimates only. This module puts them in context:

* **Baselines** fitted on the *training* regions only and scored on the test regions with the same
  labels, ignore mask and metric code as the U-Net:
  - majority class (the most frequent training label everywhere);
  - NDVI threshold for tree cover (threshold chosen to maximise tree IoU on the training regions);
  - per-pixel gradient-boosted classifier on the same 10 bands (no spatial context), with the
    class weights the U-Net v1 used (``freq ** -0.5``).
* **Spatial block bootstrap**: the test pixels are split into square blocks and blocks are resampled with
  replacement, which respects spatial autocorrelation far better than a per-pixel bootstrap. Model
  comparisons are paired (the same resampled blocks for every model).

The bootstrap only describes sampling variability *within these two test regions*. It does not cover
variability between regions, between training seeds, or between data versions (scene mosaics), which are
all larger here, so the intervals are lower bounds on the real uncertainty.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..labels.classes import CLASS_NAMES, IGNORE, NUM_CLASSES, TREE
from .dataset import class_weights, load_region
from .evaluate import hansen_tree_agreement, pooled_binary_metrics
from .infer import load_checkpoint, predict_probs
from .metrics import confusion, metrics_from_confusion

BLOCK = 128  # px (1.28 km): much longer than the label/prediction autocorrelation length at 10 m


def block_confusions(pred: np.ndarray, target: np.ndarray, block: int = BLOCK, k: int = NUM_CLASSES) -> np.ndarray:
    """Confusion matrices of each ``block`` x ``block`` tile with at least one labelled pixel, shape (B, k, k)."""
    H, W = target.shape
    out = []
    for y in range(0, H, block):
        for x in range(0, W, block):
            t = target[y : y + block, x : x + block]
            if (t != IGNORE).any():
                out.append(confusion(pred[y : y + block, x : x + block], t, k))
    return np.stack(out) if out else np.zeros((0, k, k), np.int64)


def _miou_tree_iou(cms: np.ndarray, tree_class: int = TREE) -> tuple[np.ndarray, np.ndarray]:
    """Vectorised mean IoU (over classes present in the reference) and tree IoU for (N, k, k) matrices.

    Same definition as ``metrics_from_confusion``.
    """
    cms = cms.astype(np.float64)
    tp = np.diagonal(cms, axis1=1, axis2=2)
    ref = cms.sum(axis=2)
    pred = cms.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = tp / (ref + pred - tp)
    iou = np.where(ref > 0, iou, np.nan)
    return np.nanmean(iou, axis=1), iou[:, tree_class]


def block_bootstrap(
    blocks: dict[str, np.ndarray], n_boot: int = 1000, seed: int = 0, alpha: float = 0.05, tree_class: int = TREE
) -> dict:
    """Paired spatial block bootstrap of pooled mean IoU and tree IoU.

    ``blocks`` maps a model name to its (B, k, k) block confusions; all models must share the block order.
    Returns percentile intervals per model and for each model's difference to the first model.
    """
    names = list(blocks)
    if not names:
        raise ValueError("No models given")
    n = len(blocks[names[0]])
    if n == 0 or any(len(b) != n for b in blocks.values()):
        raise ValueError("All models need the same, non-zero number of blocks")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_boot, n))
    lo, hi = 100 * alpha / 2, 100 * (1 - alpha / 2)
    # how often each block is drawn in each replicate; resampled confusion = weighted sum of block confusions
    counts = np.stack([np.bincount(row, minlength=n) for row in idx])  # (n_boot, n)
    stats = {name: _miou_tree_iou(np.einsum("rb,bij->rij", counts, blocks[name]), tree_class) for name in names}
    out: dict = {"n_blocks": int(n), "block_px": BLOCK, "n_boot": n_boot, "alpha": alpha, "models": {}, "differences": {}}
    for name in names:
        m, t = stats[name]
        out["models"][name] = {
            "mean_iou_ci": [float(np.percentile(m, lo)), float(np.percentile(m, hi))],
            "tree_iou_ci": [float(np.percentile(t, lo)), float(np.percentile(t, hi))],
        }
    ref_m, ref_t = stats[names[0]]
    for name in names[1:]:
        dm, dt = stats[name][0] - ref_m, stats[name][1] - ref_t
        out["differences"][f"{name} - {names[0]}"] = {
            "mean_iou_ci": [float(np.percentile(dm, lo)), float(np.percentile(dm, hi))],
            "tree_iou_ci": [float(np.percentile(dt, lo)), float(np.percentile(dt, hi))],
            "p_mean_iou_le_0": float((dm <= 0).mean()),
        }
    return out


def ndvi(refl: np.ndarray, bands: list[str]) -> np.ndarray:
    red, nir = refl[bands.index("B4")], refl[bands.index("B8")]
    with np.errstate(divide="ignore", invalid="ignore"):
        return (nir - red) / (nir + red)


def fit_ndvi_threshold(regions, bands: list[str], grid: np.ndarray | None = None) -> float:
    """NDVI threshold that maximises pooled tree IoU against the labels of ``regions`` (training only)."""
    grid = np.round(np.arange(0.30, 0.951, 0.01), 2) if grid is None else grid
    tp = np.zeros(len(grid))
    fp = np.zeros(len(grid))
    fn = np.zeros(len(grid))
    for r in regions:
        v = ndvi(r.refl, bands)
        m = (r.labels != IGNORE) & np.isfinite(v)
        vv, tree = v[m], r.labels[m] == TREE
        for i, th in enumerate(grid):
            p = vv >= th
            tp[i] += (p & tree).sum()
            fp[i] += (p & ~tree).sum()
            fn[i] += (~p & tree).sum()
    iou = tp / np.maximum(1, tp + fp + fn)
    return float(grid[int(np.argmax(iou))])


def _sample_pixels(regions, per_region: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    xs, ys = [], []
    for r in regions:
        flat = r.refl.reshape(r.refl.shape[0], -1)
        lab = r.labels.ravel()
        ids = np.flatnonzero(np.isfinite(flat).all(axis=0) & (lab != IGNORE))
        ids = rng.choice(ids, size=min(per_region, len(ids)), replace=False)
        xs.append(flat[:, ids].T)
        ys.append(lab[ids])
    return np.concatenate(xs).astype(np.float32), np.concatenate(ys).astype(np.int64)


def fit_pixel_classifier(regions, per_region: int = 50_000, seed: int = 0):
    """Gradient-boosted per-pixel classifier on the raw bands, weighted like U-Net v1 (freq ** -0.5)."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    X, y = _sample_pixels(regions, per_region, seed)
    w = class_weights(regions, power=0.5)
    clf = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.1, random_state=seed)
    clf.fit(X, y, sample_weight=w[y])
    return clf


def _predict_pixels(clf, refl: np.ndarray, valid: np.ndarray) -> np.ndarray:
    pred = np.full(valid.shape, IGNORE, np.uint8)
    X = refl.reshape(refl.shape[0], -1)[:, valid.ravel()].T
    pred[valid] = clf.predict(X).astype(np.uint8)
    return pred


def run_baselines(
    regions_dir: Path,
    train_regions: list[str],
    test_regions: list[str],
    checkpoints: list[Path],
    n_boot: int = 1000,
    seed: int = 0,
    progress=None,
) -> dict:
    """Score baselines and checkpoints on the test regions, with paired block-bootstrap intervals."""
    if not train_regions or not test_regions:
        raise ValueError("Baselines need built train and test regions (python -m forestwatch.cli build-regions)")
    overlap = set(train_regions) & set(test_regions)
    if overlap:
        raise ValueError(f"Regions in both train and test: {sorted(overlap)}")
    say = progress or (lambda msg: None)
    models = {}
    for c in checkpoints:
        model, ckpt = load_checkpoint(c)
        tc = ckpt.get("train_config") or {}
        seen = set(test_regions) & (set(tc.get("train_regions", [])) | set(tc.get("val_regions", [])))
        if seen:
            raise ValueError(f"{c}: regions {sorted(seen)} were used to train or select this model")
        models[c.parent.name] = (model, ckpt)
    bands = next(iter(models.values()))[1]["bands"] if models else ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]

    say("loading training regions")
    train = [load_region(regions_dir / n, bands) for n in train_regions]
    counts = np.zeros(NUM_CLASSES, np.int64)
    for r in train:
        counts += np.bincount(r.labels[r.labels != IGNORE].ravel(), minlength=NUM_CLASSES)[:NUM_CLASSES]
    majority = int(np.argmax(counts))
    say("fitting NDVI threshold")
    ndvi_th = fit_ndvi_threshold(train, bands)
    say("fitting per-pixel classifier")
    clf = fit_pixel_classifier(train, seed=seed)
    del train

    names = [*models, "pixel_gbdt", "majority_class"]
    cms = {n: np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64) for n in names}
    blocks: dict[str, list] = {n: [] for n in names}
    tree_cms = {n: np.zeros((2, 2), np.int64) for n in [*models, "ndvi_threshold"]}
    tree_blocks: dict[str, list] = {n: [] for n in tree_cms}
    hansen = {n: {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0} for n in tree_cms}
    for name in test_regions:
        say(f"scoring {name}")
        r = load_region(regions_dir / name, bands)
        valid = np.isfinite(r.refl).all(axis=0)
        target = np.where(valid, r.labels, IGNORE)
        tree_target = np.where(target == IGNORE, IGNORE, (target == TREE).astype(np.uint8))
        year = int(r.meta.get("label_year", 2021))
        preds = {}
        for mname, (model, ckpt) in models.items():
            probs = predict_probs(model, r.refl, ckpt["norm_stats"], ckpt.get("temperature", 1.0))
            preds[mname] = np.where(valid, np.nan_to_num(probs).argmax(axis=0), IGNORE).astype(np.uint8)
        preds["pixel_gbdt"] = _predict_pixels(clf, r.refl, valid)
        preds["majority_class"] = np.where(valid, majority, IGNORE).astype(np.uint8)
        for n in names:
            cms[n] += confusion(preds[n], target, NUM_CLASSES)
            blocks[n].append(block_confusions(preds[n], target))
        tree_preds = {m: preds[m] == TREE for m in models}
        tree_preds["ndvi_threshold"] = np.nan_to_num(ndvi(r.refl, bands), nan=-1.0) >= ndvi_th
        for n, tp_ in tree_preds.items():
            bt = np.where(valid, tp_, 0).astype(np.uint8)
            tree_cms[n] += confusion(bt, tree_target, 2)
            tree_blocks[n].append(block_confusions(bt, tree_target, k=2))
            hm = hansen_tree_agreement(regions_dir, name, year, tp_, valid)
            for k in hansen[n]:
                hansen[n][k] += hm[k]

    def summary(cm):
        m = metrics_from_confusion(cm, CLASS_NAMES)
        return {
            "mean_iou": m["mean_iou"],
            "mean_dice": m["mean_dice"],
            "overall_accuracy": m["overall_accuracy"],
            "per_class_iou": {c["class"]: c["iou"] for c in m["per_class"]},
            "per_class_f1": {c["class"]: c["f1"] for c in m["per_class"]},
            "pixels": m["pixels"],
        }

    def tree_summary(cm2, h):
        m = metrics_from_confusion(cm2, ["non-tree", "tree"])["per_class"][1]
        return {"tree_iou": m["iou"], "tree_f1": m["f1"], "hansen_tree_f1": pooled_binary_metrics(h)["f1"]}

    say("bootstrapping")
    boot5 = block_bootstrap({n: np.concatenate(blocks[n]) for n in names}, n_boot=n_boot, seed=seed)
    boot2 = block_bootstrap({n: np.concatenate(tree_blocks[n]) for n in tree_cms}, n_boot=n_boot, seed=seed, tree_class=1)
    return {
        "train_regions": train_regions,
        "test_regions": test_regions,
        "majority_class": CLASS_NAMES[majority],
        "ndvi_tree_threshold": ndvi_th,
        "five_class": {n: summary(cms[n]) for n in names},
        "tree_vs_non_tree": {n: tree_summary(tree_cms[n], hansen[n]) for n in tree_cms},
        "bootstrap_five_class": boot5,
        "bootstrap_tree_binary": {
            "n_blocks": boot2["n_blocks"],
            "tree_iou_ci": {n: v["tree_iou_ci"] for n, v in boot2["models"].items()},
            "differences_tree_iou_ci": {n: v["tree_iou_ci"] for n, v in boot2["differences"].items()},
        },
        "notes": [
            "Baselines are fitted on the training regions only; the test regions are untouched until scoring.",
            "Intervals are a spatial block bootstrap within the two test regions (128 px blocks). They exclude "
            "between-region, training-seed and data-version variability, so they understate the real uncertainty.",
        ],
    }
