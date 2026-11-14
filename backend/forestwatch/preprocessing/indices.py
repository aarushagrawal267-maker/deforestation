"""Spectral indices (computed on surface reflectance). Supporting indicators only."""

from __future__ import annotations

import numpy as np

from .bands import BAND_NAMES


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / (a + b)
    out[~np.isfinite(out)] = np.nan
    return np.clip(out, -1, 1).astype(np.float32)


def compute_indices(refl: np.ndarray, names: list[str] = BAND_NAMES) -> dict[str, np.ndarray]:
    """NDVI (greenness), NBR (structure/burn), NDMI (canopy moisture)."""
    g = {n: refl[i] for i, n in enumerate(names)}
    return {
        "NDVI": _nd(g["B8"], g["B4"]),
        "NBR": _nd(g["B8"], g["B12"]),
        "NDMI": _nd(g["B8"], g["B11"]),
    }
