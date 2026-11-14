"""Live provider tests (opt-in: SYLVA_RUN_NETWORK=1)."""

import pytest

from forestwatch.geo.grid import Grid
from forestwatch.labels.reference import hansen_on_grid, worldcover_on_grid
from forestwatch.preprocessing.ingest import load_product
from forestwatch.providers.earth_search import EarthSearchProvider, EarthSearchLegacyProvider

BBOX = (-55.40, -7.07, -55.38, -7.05)


@pytest.mark.network
def test_earth_search_search_and_windowed_ingest(tmp_path):
    from forestwatch.preprocessing.ingest import ingest_scene

    scenes = EarthSearchProvider().search(BBOX, "2024-07-01", "2024-07-31", max_cloud=10, limit=5)
    assert scenes and all(s.collection == "sentinel-2-c1-l2a" for s in scenes)
    g = Grid.from_bbox_lonlat(BBOX)
    meta = ingest_scene(scenes[0], g, tmp_path / "obs")
    r, q, g2, _ = load_product(tmp_path / "obs")
    assert g2.to_dict() == g.to_dict() and r.shape[0] == 10
    assert meta["scene_ids"] == [scenes[0].id]


@pytest.mark.network
def test_legacy_collection_fills_2022():
    s = EarthSearchLegacyProvider().search(BBOX, "2022-06-01", "2022-09-30", max_cloud=30, limit=5)
    assert s and s[0].provider == "earth-search-legacy"


@pytest.mark.network
def test_reference_layers():
    g = Grid.from_bbox_lonlat(BBOX)
    wc = worldcover_on_grid(g, 2021)
    assert (wc == 10).any()
    loss = hansen_on_grid(g, "lossyear")
    assert loss.max() <= 25
