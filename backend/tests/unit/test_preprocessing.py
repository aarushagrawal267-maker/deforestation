import numpy as np

from forestwatch.preprocessing.indices import compute_indices
from forestwatch.preprocessing.ingest import composite, load_product
from forestwatch.preprocessing.masking import (
    Q_BUFFER,
    Q_CLOUD,
    Q_LOWQ,
    Q_NODATA,
    Q_SHADOW,
    Q_VALID,
    build_quality,
    dn_to_reflectance,
    offset_for_baseline,
)


def test_reflectance_scaling_and_nodata():
    dn = np.array([[0, 1000, 2000]], dtype=np.uint16)
    r = dn_to_reflectance(dn)
    assert np.isnan(r[0, 0])
    np.testing.assert_allclose(r[0, 1:], [0.0, 0.1], atol=1e-6)
    np.testing.assert_allclose(dn_to_reflectance(dn, offset=0)[0, 1:], [0.1, 0.2], atol=1e-6)


def test_baseline_harmonisation():
    assert offset_for_baseline("05.00", "sentinel-2-c1-l2a") == -0.1
    assert offset_for_baseline("03.01", "sentinel-2-l2a") == 0.0
    assert offset_for_baseline("04.00", "sentinel-2-l2a") == -0.1
    assert offset_for_baseline("05.10", "sentinel-2-l2a") == -0.1


def test_quality_codes_and_buffer():
    scl = np.full((20, 20), 4, dtype=np.uint8)
    scl[10, 10] = 9  # cloud
    scl[0, 0] = 3  # shadow
    scl[19, 19] = 2  # dark area
    nodata = np.zeros_like(scl, bool)
    nodata[19, 0] = True
    q = build_quality(scl, nodata, buffer_px=2)
    assert q[10, 10] == Q_CLOUD
    assert q[0, 0] == Q_SHADOW
    assert q[19, 19] == Q_LOWQ
    assert q[19, 0] == Q_NODATA
    assert q[10, 12] == Q_BUFFER and q[12, 10] == Q_BUFFER
    assert q[10, 14] == Q_VALID
    assert q[5, 15] == Q_VALID


def test_cloud_probability_adds_cloud():
    scl = np.full((5, 5), 4, np.uint8)
    prob = np.zeros((5, 5), np.uint8)
    prob[2, 2] = 80
    q = build_quality(scl, np.zeros((5, 5), bool), prob, buffer_px=0)
    assert q[2, 2] == Q_CLOUD and (q == Q_VALID).sum() == 24


def test_indices_ranges():
    refl = np.zeros((10, 2, 2), np.float32)
    refl[2] = 0.05  # red
    refl[6] = 0.4  # nir
    refl[8] = 0.2  # swir1
    refl[9] = 0.1  # swir2
    ind = compute_indices(refl)
    np.testing.assert_allclose(ind["NDVI"], (0.4 - 0.05) / 0.45, rtol=1e-5)
    np.testing.assert_allclose(ind["NBR"], 0.3 / 0.5, rtol=1e-5)
    np.testing.assert_allclose(ind["NDMI"], 0.2 / 0.6, rtol=1e-5)


def test_fixture_products_are_real_and_aligned(fixture_products):
    assert len(fixture_products) == 2
    r1, q1, g1, m1 = load_product(fixture_products[0])
    r2, q2, g2, m2 = load_product(fixture_products[1])
    assert g1.to_dict() == g2.to_dict()
    assert r1.shape == (10, 160, 160)
    assert m1["acquired"][0] < m2["acquired"][0]
    assert "sentinel-2" in m1["platform"]
    valid = np.isfinite(r1).all(axis=0)
    assert valid.mean() > 0.9
    # plausible surface reflectance
    assert 0 < np.nanmedian(r1[6]) < 0.6


def test_composite_median(fixture_products, tmp_path):
    meta = composite(fixture_products, tmp_path / "comp")
    assert meta["kind"] == "composite" and len(meta["scene_ids"]) == 2
    r, q, g, _ = load_product(tmp_path / "comp")
    r1, *_ = load_product(fixture_products[0])
    r2, *_ = load_product(fixture_products[1])
    exp = np.nanmedian(np.stack([r1, r2]), axis=0)
    np.testing.assert_allclose(r, exp, atol=1.5e-4, equal_nan=True)
