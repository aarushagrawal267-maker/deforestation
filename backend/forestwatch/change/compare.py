"""Multi-date forest change classification from calibrated U-Net probabilities.

The output describes *potential* forest-cover change. A detected change is not a
verified deforestation event, and satellite data alone cannot establish its cause.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

INVALID, STABLE_FOREST, POTENTIAL_LOSS, POTENTIAL_GAIN, STABLE_NONFOREST, UNCERTAIN = 0, 1, 2, 3, 4, 5
CATEGORIES = [
    {"id": INVALID, "key": "invalid", "name": "Cloud / invalid observation", "color": "#6b7280"},
    {"id": STABLE_FOREST, "key": "stable_forest", "name": "Stable forest", "color": "#2f8f5b"},
    {"id": POTENTIAL_LOSS, "key": "potential_loss", "name": "Potential forest loss", "color": "#e4572e"},
    {"id": POTENTIAL_GAIN, "key": "potential_gain", "name": "Potential vegetation / tree-cover gain", "color": "#3ba7d9"},
    {"id": STABLE_NONFOREST, "key": "stable_nonforest", "name": "Non-forest stable", "color": "#3a3f3c"},
    {"id": UNCERTAIN, "key": "uncertain", "name": "Uncertain change", "color": "#d9a441"},
]


@dataclass
class ChangeParams:
    forest_hi: float = 0.6  # P(tree) at or above: confidently tree
    forest_lo: float = 0.4  # P(tree) at or below: confidently not tree
    min_delta: float = 0.3  # minimum |delta P(tree)| for loss/gain
    max_entropy: float = 0.8  # normalised entropy above which a pixel is uncertain
    spectral_ndvi_drop: float = -0.10
    spectral_nbr_drop: float = -0.10
    require_spectral_support: bool = False  # if True, loss without spectral support -> uncertain
    fire_dnbr: float = -0.27  # Key & Benson dNBR threshold (sign: later - earlier)
    opening_px: int = 1  # morphological opening radius to suppress edge/misregistration strips
    min_mapping_unit_ha: float = 0.5
    coreg_max_shift_px: float = 0.5

    @classmethod
    def from_dict(cls, d: dict | None) -> ChangeParams:
        d = d or {}
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return asdict(self)


def _open(mask: np.ndarray, r: int) -> np.ndarray:
    if r <= 0 or not mask.any():
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, k).astype(bool)


def classify_change(
    p1: np.ndarray,
    p2: np.ndarray,
    ent1: np.ndarray,
    ent2: np.ndarray,
    d_ndvi: np.ndarray,
    d_nbr: np.ndarray,
    params: ChangeParams,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """Per-pixel change category from P(tree) at two dates.

    Inputs are NaN where an observation is invalid. Returns (category uint8, aux masks).
    """
    hi, lo = params.forest_hi, params.forest_lo
    valid = np.isfinite(p1) & np.isfinite(p2)
    a, b = np.nan_to_num(p1), np.nan_to_num(p2)
    dp = b - a
    uncertain_ent = (np.nan_to_num(ent1, nan=1) > params.max_entropy) | (np.nan_to_num(ent2, nan=1) > params.max_entropy)

    stable_f = valid & (a >= hi) & (b >= hi)
    stable_n = valid & (a <= lo) & (b <= lo)
    loss = valid & (a >= hi) & (b <= lo) & (dp <= -params.min_delta)
    gain = valid & (a <= lo) & (b >= hi) & (dp >= params.min_delta)

    spectral = np.nan_to_num(d_ndvi, nan=0) <= params.spectral_ndvi_drop
    spectral |= np.nan_to_num(d_nbr, nan=0) <= params.spectral_nbr_drop
    contradicted = loss & ~spectral
    if params.require_spectral_support:
        loss &= spectral
    loss &= ~uncertain_ent
    gain &= ~uncertain_ent

    loss_clean = _open(loss, params.opening_px)
    gain_clean = _open(gain, params.opening_px)

    cat = np.full(p1.shape, UNCERTAIN, np.uint8)
    cat[stable_n] = STABLE_NONFOREST
    cat[stable_f] = STABLE_FOREST
    cat[gain_clean] = POTENTIAL_GAIN
    cat[loss_clean] = POTENTIAL_LOSS
    cat[~valid] = INVALID
    aux = {
        "dp": np.where(valid, dp, np.nan).astype(np.float32),
        "spectral_support": spectral & valid,
        "fire_like": (np.nan_to_num(d_nbr, nan=0) <= params.fire_dnbr) & valid,
        "removed_by_opening": (loss & ~loss_clean) | (gain & ~gain_clean),
        "loss_without_spectral_support": contradicted & loss_clean,
    }
    return cat, aux


def category_areas(cat: np.ndarray, pixel_area_m2: float = 100.0) -> dict:
    out = {}
    for c in CATEGORIES:
        n = int((cat == c["id"]).sum())
        out[c["key"]] = {"pixels": n, "hectares": n * pixel_area_m2 / 1e4, "fraction": n / cat.size}
    return out
