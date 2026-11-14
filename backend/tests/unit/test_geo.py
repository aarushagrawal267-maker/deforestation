import numpy as np
import rasterio

from forestwatch.geo.grid import Grid, geodesic_area_km2, utm_epsg_for
from forestwatch.geo.raster_io import read_onto_grid, read_stack, write_cog


def test_utm_zone_selection():
    assert utm_epsg_for(-55.38, -7.05) == 32721
    assert utm_epsg_for(101.45, 0.51) == 32647
    assert utm_epsg_for(10.0, 50.0) == 32632


def test_grid_snapped_and_covers_bbox():
    bbox = (-55.47, -7.14, -55.29, -6.96)
    g = Grid.from_bbox_lonlat(bbox, res=10)
    assert g.crs.to_epsg() == 32721
    assert g.transform.a == 10 and g.transform.e == -10
    assert g.transform.c % 10 == 0 and g.transform.f % 10 == 0
    lb = g.bounds_lonlat()
    assert lb[0] <= bbox[0] and lb[1] <= bbox[1] and lb[2] >= bbox[2] and lb[3] >= bbox[3]
    # ~0.18 deg at -7 lat ~ 19.9 km
    assert 1900 < g.width < 2100 and 1900 < g.height < 2100


def test_grid_roundtrip_dict():
    g = Grid.from_bbox_lonlat((-60.1, -3.2, -60.0, -3.1))
    assert Grid.from_dict(g.to_dict()) == g


def test_geodesic_area():
    # 0.1 x 0.1 degree at the equator: 11.132 km x 11.057 km ~ 123.09 km2
    a = geodesic_area_km2({"type": "Polygon", "coordinates": [[[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1], [0, 0]]]})
    assert abs(a - 123.09) < 0.1


def test_cog_roundtrip_preserves_georeferencing(tmp_path):
    g = Grid.from_bbox_lonlat((-55.40, -7.10, -55.39, -7.09))
    data = np.arange(g.width * g.height, dtype=np.int16).reshape(g.shape)
    p = write_cog(tmp_path / "x.tif", data, g, nodata=-1)
    arr, g2, _ = read_stack(p)
    assert g2.to_dict() == g.to_dict()
    np.testing.assert_array_equal(arr[0], data)
    with rasterio.open(p) as src:
        assert src.driver == "GTiff" and src.profile.get("tiled")


def test_read_onto_same_grid_is_identity(tmp_path):
    g = Grid.from_bbox_lonlat((-55.40, -7.10, -55.38, -7.08))
    data = (np.random.default_rng(0).random(g.shape) * 1000 + 1).astype(np.uint16)
    p = write_cog(tmp_path / "y.tif", data, g, nodata=0)
    out = read_onto_grid(str(p), g, dst_nodata=0)
    np.testing.assert_array_equal(out, data)
