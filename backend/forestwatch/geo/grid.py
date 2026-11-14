"""Analysis grids: every product for an AOI is written on one shared UTM 10 m grid.

Sharing an exact grid (CRS, origin and pixel size) between dates is what makes
pixel-wise multi-date comparison valid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from affine import Affine
from pyproj import CRS, Geod, Transformer
from shapely.geometry import box, mapping, shape

GEOD = Geod(ellps="WGS84")


def _reproject(geom, transformer):
    import numpy as _np

    return shapely.transform(geom, lambda c: _np.column_stack(transformer.transform(c[:, 0], c[:, 1])))


def utm_epsg_for(lon: float, lat: float) -> int:
    zone = int(math.floor((lon + 180) / 6) % 60) + 1
    return (32600 if lat >= 0 else 32700) + zone


@dataclass(frozen=True)
class Grid:
    crs: CRS
    transform: Affine
    width: int
    height: int

    @property
    def res(self) -> float:
        return self.transform.a

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        minx, maxy = self.transform.c, self.transform.f
        return (minx, maxy - self.height * self.res, minx + self.width * self.res, maxy)

    @property
    def shape(self) -> tuple[int, int]:
        return (self.height, self.width)

    def bounds_lonlat(self) -> tuple[float, float, float, float]:
        t = Transformer.from_crs(self.crs, 4326, always_xy=True)
        minx, miny, maxx, maxy = self.bounds
        xs, ys = t.transform([minx, maxx, maxx, minx], [miny, miny, maxy, maxy])
        return (min(xs), min(ys), max(xs), max(ys))

    def to_dict(self) -> dict:
        return {
            "crs": self.crs.to_string(),
            "transform": list(self.transform)[:6],
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Grid:
        return cls(CRS.from_user_input(d["crs"]), Affine(*d["transform"]), d["width"], d["height"])

    @classmethod
    def from_bbox_lonlat(cls, bbox: tuple[float, float, float, float], res: float = 10.0) -> Grid:
        """UTM grid (zone of the bbox centre) with its origin snapped to a multiple of ``res``."""
        minlon, minlat, maxlon, maxlat = bbox
        if not (minlon < maxlon and minlat < maxlat):
            raise ValueError("Invalid bbox: expected (minlon, minlat, maxlon, maxlat)")
        epsg = utm_epsg_for((minlon + maxlon) / 2, (minlat + maxlat) / 2)
        crs = CRS.from_epsg(epsg)
        t = Transformer.from_crs(4326, crs, always_xy=True)
        poly = _reproject(box(minlon, minlat, maxlon, maxlat).segmentize(0.01), t)
        x0, y0, x1, y1 = poly.bounds
        x0 = math.floor(x0 / res) * res
        y0 = math.floor(y0 / res) * res
        x1 = math.ceil(x1 / res) * res
        y1 = math.ceil(y1 / res) * res
        width, height = int(round((x1 - x0) / res)), int(round((y1 - y0) / res))
        return cls(crs, Affine(res, 0, x0, 0, -res, y1), width, height)


def geodesic_area_km2(geom_lonlat: dict) -> float:
    g = shape(geom_lonlat)
    area, _ = GEOD.geometry_area_perimeter(g)
    return abs(area) / 1e6


def bbox_geojson(bbox: tuple[float, float, float, float]) -> dict:
    return mapping(box(*bbox))
