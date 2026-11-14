"""Segmentation metrics from a confusion matrix (rows = reference, cols = prediction)."""

from __future__ import annotations

import numpy as np

from ..labels.classes import IGNORE


def confusion(pred: np.ndarray, target: np.ndarray, num_classes: int) -> np.ndarray:
    m = target != IGNORE
    t = target[m].astype(np.int64)
    p = pred[m].astype(np.int64)
    return np.bincount(t * num_classes + p, minlength=num_classes**2).reshape(num_classes, num_classes)


def metrics_from_confusion(cm: np.ndarray, class_names: list[str] | None = None) -> dict:
    cm = cm.astype(np.float64)
    tp = np.diag(cm)
    ref = cm.sum(axis=1)
    pred = cm.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        iou = tp / (ref + pred - tp)
        precision = tp / pred
        recall = tp / ref
        f1 = 2 * precision * recall / (precision + recall)
    present = ref > 0
    names = class_names or [str(i) for i in range(len(cm))]

    def clean(a):
        return [None if not np.isfinite(v) else float(v) for v in a]

    total = cm.sum()
    return {
        "overall_accuracy": float(tp.sum() / total) if total else None,
        "mean_iou": float(np.nanmean(iou[present])) if present.any() else None,
        "mean_dice": float(np.nanmean(f1[present])) if present.any() else None,
        "macro_precision": float(np.nanmean(precision[present])) if present.any() else None,
        "macro_recall": float(np.nanmean(recall[present])) if present.any() else None,
        "per_class": [
            {
                "class": names[i],
                "iou": clean(iou)[i],
                "precision": clean(precision)[i],
                "recall": clean(recall)[i],
                "f1": clean(f1)[i],
                "dice": clean(f1)[i],
                "support": int(ref[i]),
            }
            for i in range(len(cm))
        ],
        "confusion_matrix": cm.astype(int).tolist(),
        "pixels": int(total),
    }


def binary_metrics(pred: np.ndarray, ref: np.ndarray, valid: np.ndarray) -> dict:
    p, r = pred[valid].astype(bool), ref[valid].astype(bool)
    tp = float((p & r).sum())
    fp = float((p & ~r).sum())
    fn = float((~p & r).sum())
    tn = float((~p & ~r).sum())
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    iou = tp / (tp + fp + fn) if tp + fp + fn else None
    return {
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "iou": iou,
        "accuracy": (tp + tn) / max(1.0, tp + tn + fp + fn),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
    }


def expected_calibration_error(conf: np.ndarray, correct: np.ndarray, bins: int = 15) -> tuple[float, list[dict]]:
    edges = np.linspace(0, 1, bins + 1)
    ece, rows = 0.0, []
    n = len(conf)
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        acc, c = float(correct[m].mean()), float(conf[m].mean())
        ece += m.sum() / n * abs(acc - c)
        rows.append({"bin_low": float(lo), "bin_high": float(hi), "confidence": c, "accuracy": acc, "count": int(m.sum())})
    return float(ece), rows
