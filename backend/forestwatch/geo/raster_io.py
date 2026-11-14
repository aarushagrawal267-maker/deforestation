"""Raster reading/writing helpers that preserve georeferencing exactly."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

from .grid import Grid


def read_onto_grid(
    src_path: str,
    grid: Grid,
    resampling: Resampling = Resampling.bilinear,
    band: int = 1,
    dtype: str | None = None,
    src_nodata: float | None = None,
    dst_nodata: float | None = 0,
) -> np.ndarray:
    """Read one band of a (local or remote) raster, warped onto ``grid``.

    Only the window covering the grid is fetched, which keeps remote reads of
    cloud-optimised GeoTIFFs small.
    """
    with rasterio.open(src_path) as src:
        nodata = src_nodata if src_nodata is not None else src.nodata
        opts = dict(
            crs=grid.crs,
            transform=grid.transform,
            width=grid.width,
            height=grid.height,
            resampling=resampling,
        )
        if nodata is not None:
            opts["src_nodata"] = nodata
            opts["nodata"] = dst_nodata if dst_nodata is not None else nodata
        with WarpedVRT(src, **opts) as vrt:
            arr = vrt.read(band)
    return arr.astype(dtype) if dtype else arr


def write_cog(
    path: Path,
    data: np.ndarray,
    grid: Grid,
    nodata: float | None = None,
    band_names: list[str] | None = None,
    tags: dict | None = None,
    resampling_overview: str = "average",
) -> Path:
    """Write a Cloud-Optimised GeoTIFF on ``grid`` (data shape (bands,H,W) or (H,W))."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if data.ndim == 2:
        data = data[None]
    if data.shape[1:] != grid.shape:
        raise ValueError(f"Array shape {data.shape[1:]} does not match grid {grid.shape}")
    profile = dict(
        driver="COG",
        dtype=str(data.dtype),
        count=data.shape[0],
        width=grid.width,
        height=grid.height,
        crs=grid.crs,
        transform=grid.transform,
        compress="deflate",
        blocksize=256,
        overview_resampling=resampling_overview,
        BIGTIFF="IF_SAFER",
    )
    if nodata is not None:
        profile["nodata"] = nodata
    tmp = path.with_suffix(".tmp.tif")
    with rasterio.open(tmp, "w", **profile) as dst:
        dst.write(data)
        if band_names:
            for i, n in enumerate(band_names, start=1):
                dst.set_band_description(i, n)
        if tags:
            dst.update_tags(**{k: json.dumps(v) if not isinstance(v, str) else v for k, v in tags.items()})
    tmp.replace(path)
    return path


def read_stack(path: Path) -> tuple[np.ndarray, Grid, list[str]]:
    with rasterio.open(path) as src:
        data = src.read()
        grid = Grid(src.crs, src.transform, src.width, src.height)
        names = [d or f"b{i + 1}" for i, d in enumerate(src.descriptions)]
    return data, grid, names


def grid_of(path: Path) -> Grid:
    with rasterio.open(path) as src:
        return Grid(src.crs, src.transform, src.width, src.height)
