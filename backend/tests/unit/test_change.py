import numpy as np
from affine import Affine
from pyproj import CRS

from forestwatch.change.compare import (
    INVALID,
    POTENTIAL_GAIN,
    POTENTIAL_LOSS,
    STABLE_FOREST,
    STABLE_NONFOREST,
    UNCERTAIN,
    ChangeParams,
    category_areas,
    classify_change,
)
from forestwatch.change.coregister import apply_shift, estimate_shift
from forestwatch.change.polygons import vectorize_regions
from forestwatch.geo.grid import Grid


def _run(p1, p2, ent=0.1, dndvi=-0.3, dnbr=-0.3, **kw):
    p1, p2 = np.asarray(p1, np.float32), np.asarray(p2, np.float32)
    e = np.full(p1.shape, ent, np.float32)
    params = ChangeParams(**{"opening_px": 0, "gain_opening_px": 0, **kw})
    return classify_change(p1, p2, e, e, np.full(p1.shape, dndvi, np.float32), np.full(p1.shape, dnbr, np.float32), params)


def test_truth_table():
    p1 = [[0.9, 0.9, 0.1, 0.1, 0.5, np.nan, 0.65]]
    p2 = [[0.9, 0.1, 0.1, 0.9, 0.5, 0.2, 0.39]]
    cat, aux = _run(p1, p2)
    # 4th pixel: 0.1 -> 0.9 but NDVI fell, so gain is not spectrally supported -> uncertain
    assert cat.tolist() == [[STABLE_FOREST, POTENTIAL_LOSS, STABLE_NONFOREST, UNCERTAIN, UNCERTAIN, INVALID, UNCERTAIN]]
    # last pixel: hi->lo but delta 0.26 < 0.3 -> uncertain
    assert np.isnan(aux["dp"][0, 5])


def test_gain_is_strict():
    # supported: P 0.1 -> 0.9 with NDVI rise
    cat, aux = _run([[0.1, 0.35, 0.1]], [[0.9, 0.9, 0.7]], dndvi=0.2, dnbr=0.2)
    # 2nd: before 0.35 > gain_lo 0.2; 3rd: after 0.7 < gain_hi 0.8 -> both uncertain
    assert cat.tolist() == [[POTENTIAL_GAIN, UNCERTAIN, UNCERTAIN]]
    assert aux["gain_rejected_strict"].tolist() == [[False, True, True]]
    # NDVI rise too small
    cat, _ = _run([[0.1]], [[0.9]], dndvi=0.05, dnbr=0.05)
    assert cat[0, 0] == UNCERTAIN


def test_high_entropy_blocks_loss():
    cat, _ = _run([[0.9]], [[0.1]], ent=0.95)
    assert cat[0, 0] == UNCERTAIN


def test_spectral_support_requirement():
    cat, aux = _run([[0.9]], [[0.1]], dndvi=0.05, dnbr=0.05)
    assert cat[0, 0] == POTENTIAL_LOSS and aux["loss_without_spectral_support"][0, 0]
    cat, _ = _run([[0.9]], [[0.1]], dndvi=0.05, dnbr=0.05, require_spectral_support=True)
    assert cat[0, 0] == UNCERTAIN


def test_opening_removes_one_pixel_strips():
    p1 = np.full((20, 20), 0.9, np.float32)
    p2 = p1.copy()
    p2[:, 5] = 0.1  # 1 px wide strip (misregistration-like)
    p2[8:16, 10:18] = 0.1  # solid block
    e = np.zeros_like(p1)
    d = np.full_like(p1, -0.3)
    cat, aux = classify_change(p1, p2, e, e, d, d, ChangeParams(opening_px=1))
    assert not (cat[:, 5] == POTENTIAL_LOSS).any()
    assert (cat[10:14, 12:16] == POTENTIAL_LOSS).all()
    assert aux["removed_by_opening"][:, 5].all()


def test_category_areas():
    cat = np.array([[POTENTIAL_LOSS, POTENTIAL_LOSS, INVALID, STABLE_FOREST]], np.uint8)
    a = category_areas(cat, 100)
    assert a["potential_loss"]["hectares"] == 0.02 and a["invalid"]["fraction"] == 0.25


def _grid(n=100):
    return Grid(CRS.from_epsg(32721), Affine(10, 0, 700000, 0, -10, 9200000), n, n)


def test_polygon_area_and_mmu():
    g = _grid()
    m = np.zeros(g.shape, bool)
    m[10:20, 10:20] = True  # 100 px = 1 ha
    m[50:53, 50:53] = True  # 9 px = 0.09 ha < MMU
    attrs = {"v": np.full(g.shape, 0.5, np.float32)}
    feats = vectorize_regions(m, g, 0.5, attrs, np.zeros(g.shape, bool), "T")
    assert len(feats) == 1
    p = feats[0]["properties"]
    assert p["pixel_count"] == 100 and p["pixel_area_ha"] == 1.0
    assert abs(p["area_ha"] - 1.0) < 0.01  # geodesic vs UTM: < 1% at this latitude
    assert abs(p["area_uncertainty_ha"] - 400 * 5 / 1e4) < 1e-6  # perimeter 400 m x 5 m
    assert p["v"] == 0.5 and p["id"] == "T-0001"
    lon, lat = p["centroid_lon"], p["centroid_lat"]
    assert -57 < lon < -51 and -10 < lat < -5


def test_polygon_distance_to_invalid():
    g = _grid()
    m = np.zeros(g.shape, bool)
    m[40:60, 40:60] = True
    inv = np.zeros(g.shape, bool)
    inv[40:60, 70] = True  # 10 px to the right of the region edge
    f = vectorize_regions(m, g, 0.5, {}, inv, "T")[0]
    assert 95 <= f["properties"]["distance_to_invalid_m"] <= 115


def test_coregistration_recovers_shift(fixture_products):
    from forestwatch.preprocessing.ingest import load_product

    r, *_ = load_product(fixture_products[0])
    nir = r[6]
    shifted = apply_shift(nir, -2.0, 1.0)  # content displaced by (+2, -1) px
    est = estimate_shift(nir[10:-10, 10:-10], shifted[10:-10, 10:-10])
    assert abs(est["dx"] - 2.0) < 0.2 and abs(est["dy"] + 1.0) < 0.2
    realigned = apply_shift(shifted, est["dx"], est["dy"])
    assert np.nanmean(np.abs(realigned - nir)[15:-15, 15:-15]) < 0.002
