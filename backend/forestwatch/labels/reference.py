"""Reference datasets: ESA WorldCover and Hansen Global Forest Change.

Only the tiles intersecting an AOI are read (windowed reads of public COG/GeoTIFFs),
then warped onto the AOI's analysis grid.
"""

from __future__ import annotations

import math

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from ..geo.grid import Grid
from ..settings import configure_gdal_env

WORLDCOVER = {
    2020: {
        "version": "v100",
        "url": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v100/2020/map/ESA_WorldCover_10m_2020_v100_{tile}_Map.tif",
    },
    2021: {
        "version": "v200",
        "url": "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{tile}_Map.tif",
    },
}
HANSEN_VERSION = "GFC-2025-v1.13"
HANSEN_LAST_YEAR = 2025
HANSEN_URL = (
    "https://storage.googleapis.com/earthenginepartners-hansen/"
    + HANSEN_VERSION
    + "/Hansen_"
    + HANSEN_VERSION
    + "_{layer}_{tile}.tif"
)

DATASET_INFO = {
    "worldcover": {
        "name": "ESA WorldCover",
        "provider": "European Space Agency (ESA) / WorldCover consortium",
        "versions": "2020 v100, 2021 v200",
        "resolution": "10 m",
        "crs": "EPSG:4326 (3x3 degree tiles)",
        "licence": "CC BY 4.0",
        "source": "https://esa-worldcover.org/en/data-access",
        "role": "Default training labels (2021 v200) and reference comparison",
        "limitations": [
            "Model-generated map derived from Sentinel-1 and Sentinel-2: not independent ground truth.",
            "Reported overall accuracy roughly 74% (2020) and 77% (2021).",
            "2020 and 2021 maps use different algorithm versions: differences are not real change.",
            "Annual product: within-year changes are not represented.",
        ],
        "attribution": "ESA WorldCover project / Contains modified Copernicus Sentinel data (2020, 2021) processed by ESA WorldCover consortium",
    },
    "hansen": {
        "name": "Hansen Global Forest Change",
        "provider": "University of Maryland (Hansen et al. 2013)",
        "versions": HANSEN_VERSION,
        "resolution": "1 arc-second (about 30 m)",
        "crs": "EPSG:4326 (10x10 degree tiles)",
        "licence": "CC BY 4.0",
        "source": "https://glad.earthengine.app/view/global-forest-change",
        "role": "Independent (Landsat-based) reference for tree-cover extent and loss corroboration; label masking",
        "limitations": [
            "Tree-cover loss = stand-replacing disturbance (clearing, harvest, fire, storms): not equal to deforestation.",
            "About 30 m resolution; annual loss years only.",
            "Methodology updates over time make year-to-year trend comparison inconsistent.",
            "treecover2000 describes the year 2000 baseline.",
        ],
        "attribution": "Hansen/UMD/Google/USGS/NASA",
    },
}


def worldcover_tiles(bbox: tuple[float, float, float, float]) -> list[str]:
    minlon, minlat, maxlon, maxlat = bbox
    tiles = []
    for lat in range(math.floor(minlat / 3) * 3, math.floor(maxlat / 3) * 3 + 1, 3):
        for lon in range(math.floor(minlon / 3) * 3, math.floor(maxlon / 3) * 3 + 1, 3):
            ns = f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"
            ew = f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"
            tiles.append(ns + ew)
    return tiles


def hansen_tiles(bbox: tuple[float, float, float, float]) -> list[str]:
    minlon, minlat, maxlon, maxlat = bbox
    tiles = []
    # Hansen tiles are named by their top-left corner
    for top in range(math.ceil(minlat / 10) * 10, math.ceil(maxlat / 10) * 10 + 1, 10):
        for left in range(math.floor(minlon / 10) * 10, math.floor(maxlon / 10) * 10 + 1, 10):
            ns = f"{abs(top):02d}{'N' if top >= 0 else 'S'}"
            ew = f"{abs(left):03d}{'E' if left >= 0 else 'W'}"
            tiles.append(f"{ns}_{ew}")
    return sorted(set(tiles))


def _mosaic_onto_grid(urls: list[str], grid: Grid, resampling: Resampling, src_nodata=None) -> np.ndarray:
    configure_gdal_env()
    FILL = 255
    out = np.full(grid.shape, FILL, dtype=np.uint8)
    for url in urls:
        try:
            with rasterio.open(url) as src:
                with WarpedVRT(
                    src,
                    crs=grid.crs,
                    transform=grid.transform,
                    width=grid.width,
                    height=grid.height,
                    resampling=resampling,
                    src_nodata=src_nodata if src_nodata is not None else src.nodata,
                    nodata=FILL,
                ) as vrt:
                    arr = vrt.read(1)
        except rasterio.errors.RasterioIOError:
            continue  # e.g. ocean tiles that do not exist
        sel = arr != FILL
        out[sel] = arr[sel]
    return out


def worldcover_on_grid(grid: Grid, year: int = 2021) -> np.ndarray:
    """WorldCover class codes on the grid (0 where unavailable)."""
    spec = WORLDCOVER[year]
    urls = [spec["url"].format(tile=t) for t in worldcover_tiles(grid.bounds_lonlat())]
    arr = _mosaic_onto_grid(urls, grid, Resampling.nearest, src_nodata=0)
    arr[arr == 255] = 0
    return arr


def hansen_on_grid(grid: Grid, layer: str) -> np.ndarray:
    """Hansen layer on the grid. treecover2000: percent (255 = unavailable); lossyear: 0 none, 1..25 = 2001..2025."""
    urls = [HANSEN_URL.format(layer=layer, tile=t) for t in hansen_tiles(grid.bounds_lonlat())]
    res = Resampling.bilinear if layer == "treecover2000" else Resampling.nearest
    return _mosaic_onto_grid(urls, grid, res)
