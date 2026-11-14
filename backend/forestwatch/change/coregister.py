"""Residual co-registration check between two dates (phase correlation on NIR)."""

from __future__ import annotations

import cv2
import numpy as np


def _prep(band: np.ndarray) -> np.ndarray:
    b = band.astype(np.float32)
    m = np.isfinite(b)
    fill = float(np.nanmedian(b)) if m.any() else 0.0
    b = np.where(m, b, fill)
    # high-pass to emphasise edges, reduce sensitivity to radiometric differences
    return b - cv2.GaussianBlur(b, (0, 0), 5)


def estimate_shift(a: np.ndarray, b: np.ndarray) -> dict:
    """Displacement (dx, dy) in pixels of ``b`` relative to ``a`` (phase correlation).

    ``apply_shift(b, dx, dy)`` re-aligns ``b`` onto ``a``. Integer shifts are recovered to
    ~0.05 px; sub-pixel estimates are approximate (~0.3 px), which is why the pipeline only
    corrects shifts above 0.5 px and otherwise relies on edge suppression.
    """
    A, B = _prep(a), _prep(b)
    win = cv2.createHanningWindow(A.shape[::-1], cv2.CV_32F)
    (dx, dy), response = cv2.phaseCorrelate(A, B, win)
    return {"dx": float(dx), "dy": float(dy), "magnitude": float(np.hypot(dx, dy)), "response": float(response)}


def apply_shift(arr: np.ndarray, dx: float, dy: float, nearest: bool = False) -> np.ndarray:
    """Shift a (H,W) or (C,H,W) array by (-dx,-dy) so it aligns with the reference; NaN outside."""
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    interp = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR

    def one(x):
        x = x.astype(np.float32)
        valid = np.isfinite(x).astype(np.float32)
        out = cv2.warpAffine(np.nan_to_num(x), M, x.shape[::-1], flags=interp, borderValue=0)
        v = cv2.warpAffine(valid, M, x.shape[::-1], flags=cv2.INTER_NEAREST, borderValue=0)
        out[v < 0.5] = np.nan
        return out

    if arr.ndim == 2:
        return one(arr)
    return np.stack([one(c) for c in arr])
