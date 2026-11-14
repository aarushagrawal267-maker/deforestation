"""Optional Dynamic World (GOOGLE/DYNAMICWORLD/V1) support.

Dynamic World is only distributed through Google Earth Engine, which requires a
(free, noncommercial) Earth Engine account and a Google Cloud project. Use
``scripts/export_dynamic_world.py`` to export the probability bands for a
Sentinel-2 image to a GeoTIFF, then place it next to a region's labels as
``dynamic_world.tif``. When present, label fusion uses it; otherwise Sylva
falls back to WorldCover-only labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

from ..geo.grid import Grid
from ..geo.raster_io import read_onto_grid
from .classes import DYNAMIC_WORLD_BANDS


def load_dynamic_world(path: Path, grid: Grid) -> np.ndarray | None:
    if not Path(path).exists():
        return None
    probs = [
        read_onto_grid(str(path), grid, Resampling.bilinear, band=i + 1, dtype="float32", dst_nodata=None)
        for i in range(len(DYNAMIC_WORLD_BANDS))
    ]
    return np.stack(probs)
