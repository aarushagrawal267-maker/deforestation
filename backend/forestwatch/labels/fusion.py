"""Build weak training labels from reference products.

Labels are *model-generated reference labels* (WorldCover, optionally Dynamic World),
not independent ground truth. Uncertain pixels get ``IGNORE`` and are excluded from
the loss.
"""

from __future__ import annotations

import cv2
import numpy as np

from ..preprocessing.masking import Q_VALID
from .classes import DYNAMIC_WORLD_MAP, IGNORE, NUM_CLASSES, WORLDCOVER_MAP, map_codes


def class_boundaries(labels: np.ndarray, width_px: int = 1) -> np.ndarray:
    """Pixels within ``width_px`` of a class boundary."""
    k = np.ones((2 * width_px + 1, 2 * width_px + 1), np.uint8)
    mx = cv2.dilate(labels, k)
    mn = cv2.erode(labels, k)
    return mx != mn


def build_labels(
    worldcover: np.ndarray,
    quality: np.ndarray,
    hansen_lossyear: np.ndarray | None = None,
    label_year: int = 2021,
    dw_probs: np.ndarray | None = None,
    dw_threshold: float = 0.6,
    boundary_px: int = 1,
) -> tuple[np.ndarray, dict]:
    """Return (labels uint8 with IGNORE, report dict).

    Rules:
      * WorldCover codes are mapped to Sylva classes (snow/moss/no-data ignored).
      * Pixels within ``boundary_px`` of a class boundary are ignored (registration and
        10 m mixed-pixel uncertainty).
      * Pixels with Hansen loss in label_year-1 .. label_year+1 are ignored (the label may
        describe the landscape before or after the change).
      * Pixels not valid in the imagery (cloud, shadow, buffer, no data) are ignored.
      * If Dynamic World probabilities (9, H, W) are given, a pixel is kept only where the
        DW top class has probability >= ``dw_threshold`` and agrees with WorldCover.
    """
    labels = map_codes(worldcover, WORLDCOVER_MAP)
    report: dict = {"total_pixels": int(labels.size)}
    ignore = labels == IGNORE
    report["ignored_reference_nodata_or_out_of_scope"] = int(ignore.sum())

    if boundary_px > 0:
        b = class_boundaries(labels, boundary_px) & ~ignore
        report["ignored_class_boundary"] = int(b.sum())
        ignore |= b

    if hansen_lossyear is not None:
        codes = [label_year - 2000 + d for d in (-1, 0, 1)]
        loss = np.isin(hansen_lossyear, codes) & ~ignore
        report["ignored_hansen_recent_loss"] = int(loss.sum())
        ignore |= loss

    inval = (quality != Q_VALID) & ~ignore
    report["ignored_invalid_imagery"] = int(inval.sum())
    ignore |= inval

    if dw_probs is not None:
        top = dw_probs.argmax(axis=0).astype(np.uint8)
        conf = dw_probs.max(axis=0)
        dw_cls = map_codes(top, DYNAMIC_WORLD_MAP)
        disagree = ((dw_cls != labels) | (conf < dw_threshold)) & ~ignore
        report["ignored_dynamic_world_disagreement_or_low_confidence"] = int(disagree.sum())
        ignore |= disagree

    labels = labels.copy()
    labels[ignore] = IGNORE
    report["labelled_pixels"] = int((labels != IGNORE).sum())
    report["labelled_fraction"] = report["labelled_pixels"] / max(1, labels.size)
    report["class_counts"] = {int(c): int((labels == c).sum()) for c in range(NUM_CLASSES)}
    return labels, report
