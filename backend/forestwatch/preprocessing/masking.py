"""Radiometric scaling and quality masking for Sentinel-2 L2A.

Scene Classification Layer (SCL) values (Sen2Cor):
 0 no data, 1 saturated/defective, 2 dark area / topographic shadow, 3 cloud shadow,
 4 vegetation, 5 not vegetated, 6 water, 7 unclassified, 8 cloud medium prob,
 9 cloud high prob, 10 thin cirrus, 11 snow/ice.
"""

from __future__ import annotations

import cv2
import numpy as np

SCL_NAMES = {
    0: "no_data",
    1: "saturated_defective",
    2: "dark_area",
    3: "cloud_shadow",
    4: "vegetation",
    5: "not_vegetated",
    6: "water",
    7: "unclassified",
    8: "cloud_medium",
    9: "cloud_high",
    10: "thin_cirrus",
    11: "snow_ice",
}
SCL_CLOUD = (8, 9, 10)
SCL_SHADOW = (3,)
SCL_INVALID = (0, 1)
SCL_LOWQ = (2, 11)

# Quality codes written to the quality band of every analysis-ready product
Q_VALID, Q_NODATA, Q_CLOUD, Q_SHADOW, Q_BUFFER, Q_LOWQ = 0, 1, 2, 3, 4, 5
QUALITY_NAMES = {
    Q_VALID: "valid",
    Q_NODATA: "no data",
    Q_CLOUD: "cloud",
    Q_SHADOW: "cloud shadow",
    Q_BUFFER: "cloud/shadow buffer",
    Q_LOWQ: "dark area / snow (low quality)",
}


def dn_to_reflectance(dn: np.ndarray, scale: float = 1e-4, offset: float = -0.1) -> np.ndarray:
    """Convert L2A digital numbers to surface reflectance.

    Collection-1 products (and legacy products with processing baseline >= 04.00)
    use reflectance = DN * 1e-4 - 0.1. Legacy products with baseline < 04.00 use
    offset 0; pass ``offset=0`` for those so mixed archives are harmonised.
    """
    refl = dn.astype(np.float32) * scale + offset
    refl[dn == 0] = np.nan
    return refl


def offset_for_baseline(baseline: str | None, collection: str) -> float:
    if "c1" in collection:
        return -0.1
    try:
        return -0.1 if float(baseline or "0") >= 4.0 else 0.0
    except ValueError:
        return -0.1


def _dilate(mask: np.ndarray, px: int) -> np.ndarray:
    if px <= 0 or not mask.any():
        return mask
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * px + 1, 2 * px + 1))
    return cv2.dilate(mask.astype(np.uint8), k).astype(bool)


def build_quality(
    scl: np.ndarray,
    nodata: np.ndarray,
    cloud_prob: np.ndarray | None = None,
    cloud_prob_threshold: int = 40,
    buffer_px: int = 4,
) -> np.ndarray:
    """Per-pixel quality code (uint8). Only ``Q_VALID`` pixels are used downstream.

    SCL under-detects cloud edges and shadows, so clouds and shadows are dilated by
    ``buffer_px`` pixels (default 4 px = 40 m) and the Sen2Cor cloud-probability
    layer, when available, adds pixels above ``cloud_prob_threshold`` percent.
    """
    q = np.zeros(scl.shape, dtype=np.uint8)
    cloud = np.isin(scl, SCL_CLOUD)
    if cloud_prob is not None:
        cloud |= cloud_prob >= cloud_prob_threshold
    shadow = np.isin(scl, SCL_SHADOW)
    buffer = _dilate(cloud | shadow, buffer_px) & ~(cloud | shadow)
    q[np.isin(scl, SCL_LOWQ)] = Q_LOWQ
    q[buffer] = Q_BUFFER
    q[shadow] = Q_SHADOW
    q[cloud] = Q_CLOUD
    q[nodata | np.isin(scl, SCL_INVALID)] = Q_NODATA
    return q


def quality_summary(q: np.ndarray) -> dict:
    total = q.size
    return {QUALITY_NAMES[k]: float((q == k).sum() / total) for k in QUALITY_NAMES}
