"""End-to-end pipeline on real Sentinel-2 fixture crops.

Uses a small randomly initialised U-Net checkpoint: this verifies georeferencing,
file formats and plumbing, NOT model accuracy.
"""

import json

import numpy as np
import rasterio
import torch

from forestwatch.change.compare import ChangeParams
from forestwatch.geo.raster_io import grid_of
from forestwatch.ml.unet import UNet
from forestwatch.pipeline import detect_change, segment_product
from forestwatch.preprocessing.bands import BAND_NAMES


def make_ckpt(path):
    torch.manual_seed(0)
    m = UNet(10, 5, 8, 2)
    torch.save(
        {
            "state_dict": m.state_dict(),
            "model_config": m.config,
            "bands": BAND_NAMES,
            "norm_stats": {"mean": [0.05] * 10, "std": [0.05] * 10},
            "class_names": ["a", "b", "c", "d", "e"],
            "temperature": 1.0,
        },
        path,
    )
    return path


def test_segmentation_preserves_grid(fixture_products, tmp_path):
    ck = make_ckpt(tmp_path / "m.pt")
    meta = segment_product(fixture_products[0], ck, tmp_path / "seg")
    g_in = grid_of(fixture_products[0] / "stack.tif")
    for f in ("probs.tif", "class.tif", "entropy.tif"):
        assert grid_of(tmp_path / "seg" / f).to_dict() == g_in.to_dict()
    with rasterio.open(tmp_path / "seg" / "probs.tif") as src:
        p = src.read().astype(float)
    valid = p[0] != 255
    np.testing.assert_allclose((p[:, valid] / 250).sum(axis=0), 1.0, atol=0.03)
    assert 0 <= meta["summary"]["tree_cover_fraction_of_valid"] <= 1


def test_change_detection_end_to_end(fixture_products, tmp_path):
    ck = make_ckpt(tmp_path / "m.pt")
    s = detect_change(fixture_products, ck, tmp_path / "chg", ChangeParams(min_mapping_unit_ha=0.1), run_id="T")
    g_in = grid_of(fixture_products[0] / "stack.tif")
    for f in ("category.tif", "delta_p_tree.tif", "delta_indices.tif"):
        assert grid_of(tmp_path / "chg" / f).to_dict() == g_in.to_dict()
    fc = json.loads((tmp_path / "chg" / "regions.geojson").read_text())
    assert fc["type"] == "FeatureCollection"
    assert s["n_loss_regions"] == sum(1 for f in fc["features"] if f["properties"]["change_type"] == "potential_loss")
    areas = s["category_areas"]
    assert abs(sum(a["fraction"] for a in areas.values()) - 1) < 1e-9
    assert s["date_before"][0] < s["date_after"][0]
    for f in fc["features"]:
        p = f["properties"]
        assert p["area_ha"] >= 0.1 * 0.95 and p["evidence_level"] in ("potential", "spectrally_supported", "corroborated_hansen")
