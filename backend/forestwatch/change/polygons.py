"""Vectorise potential-change pixels into attributed regions."""

from __future__ import annotations

import cv2
import numpy as np
import shapely
from pyproj import Transformer
from rasterio.features import shapes
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

from ..geo.grid import GEOD, Grid


def _reproject(geom, transformer):
    import numpy as _np

    return shapely.transform(geom, lambda c: _np.column_stack(transformer.transform(c[:, 0], c[:, 1])))


def _mean_by_label(values: np.ndarray, labels: np.ndarray, n: int) -> np.ndarray:
    v = np.nan_to_num(values.astype(np.float64))
    finite = np.isfinite(values)
    s = np.bincount(labels.ravel(), weights=(v * finite).ravel(), minlength=n)
    c = np.bincount(labels.ravel(), weights=finite.ravel().astype(np.float64), minlength=n)
    with np.errstate(invalid="ignore", divide="ignore"):
        return s / c


def vectorize_regions(
    mask: np.ndarray,
    grid: Grid,
    min_area_ha: float,
    attributes: dict[str, np.ndarray],
    invalid: np.ndarray,
    id_prefix: str,
    simplify_m: float = 5.0,
) -> list[dict]:
    """Connected components (8-connectivity) of ``mask`` -> GeoJSON features (EPSG:4326).

    ``attributes`` maps name -> per-pixel array; the mean over each region is reported.
    Area is geodesic (WGS84 ellipsoid). Boundary uncertainty = perimeter x 1/2 pixel.
    """
    if not mask.any():
        return []
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    pix_area = grid.res * grid.res
    min_px = int(np.ceil(min_area_ha * 1e4 / pix_area))
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_px
    if not keep.any():
        return []
    lab = np.where(keep[lab], lab, 0).astype(np.int32)
    means = {k: _mean_by_label(v, lab, n) for k, v in attributes.items()}

    # distance (m) from each pixel to the nearest invalid (cloud / no-data) pixel
    if invalid.any():
        dist = cv2.distanceTransform((~invalid).astype(np.uint8), cv2.DIST_L2, 5).astype(np.float64) * grid.res
    else:
        dist = np.full(mask.shape, np.inf)
    min_dist = np.full(n, np.inf)
    np.minimum.at(min_dist, lab.ravel(), dist.ravel())

    to_ll = Transformer.from_crs(grid.crs, 4326, always_xy=True)
    geoms: dict[int, list] = {}
    for geom, val in shapes(lab, mask=lab > 0, transform=grid.transform, connectivity=8):
        geoms.setdefault(int(val), []).append(shape(geom))

    feats = []
    for k, (label, parts) in enumerate(sorted(geoms.items()), start=1):
        g_utm = unary_union(parts).simplify(simplify_m, preserve_topology=True)
        g_ll = _reproject(g_utm, to_ll)
        area_m2, perim_m = GEOD.geometry_area_perimeter(g_ll)
        area_ha = abs(area_m2) / 1e4
        c = g_ll.centroid
        props = {
            "id": f"{id_prefix}-{k:04d}",
            "label": int(label),
            "centroid_lon": round(c.x, 6),
            "centroid_lat": round(c.y, 6),
            "bbox": [round(v, 6) for v in g_ll.bounds],
            "pixel_count": int(stats[label, cv2.CC_STAT_AREA]),
            "area_ha": round(area_ha, 4),
            "area_uncertainty_ha": round(abs(perim_m) * grid.res / 2 / 1e4, 4),
            "pixel_area_ha": round(stats[label, cv2.CC_STAT_AREA] * pix_area / 1e4, 4),
            "distance_to_invalid_m": None if not np.isfinite(min_dist[label]) else float(min_dist[label]),
        }
        for name, arr in means.items():
            v = arr[label]
            props[name] = None if not np.isfinite(v) else round(float(v), 4)
        feats.append({"type": "Feature", "geometry": mapping(g_ll), "properties": props})
    return feats
