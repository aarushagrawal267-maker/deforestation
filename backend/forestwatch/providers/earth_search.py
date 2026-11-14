"""Element 84 Earth Search (AWS Open Data) Sentinel-2 Collection-1 L2A provider.

No credentials are required. Bands are Cloud-Optimised GeoTIFFs, so Sylva reads
only the AOI window of each band instead of downloading whole ~1 GB scenes.
Data: Copernicus Sentinel-2 (ESA), redistributed on AWS Open Data.
"""

from __future__ import annotations

from datetime import datetime

from pystac_client import Client

from ..settings import get_settings
from .base import Provider, SceneInfo

ASSET_KEYS = [
    "blue",
    "green",
    "red",
    "rededge1",
    "rededge2",
    "rededge3",
    "nir",
    "nir08",
    "swir16",
    "swir22",
    "scl",
    "cloud",
]


def _to_scene(item, collection: str) -> SceneInfo:
    p = item.properties
    assets = {k: a.href for k, a in item.assets.items() if k in ASSET_KEYS}
    thumb = item.assets.get("thumbnail") or item.assets.get("preview")
    return SceneInfo(
        id=item.id,
        provider="earth-search",
        collection=collection,
        datetime=datetime.fromisoformat(p["datetime"].replace("Z", "+00:00")),
        platform=p.get("platform", "sentinel-2"),
        cloud_cover=p.get("eo:cloud_cover"),
        mgrs_tile=p.get("grid:code"),
        processing_baseline=p.get("s2:processing_baseline"),
        bbox=list(item.bbox),
        geometry=item.geometry,
        assets=assets,
        thumbnail=thumb.href if thumb else None,
        properties={
            k: p.get(k)
            for k in (
                "s2:product_uri",
                "s2:vegetation_percentage",
                "s2:cloud_shadow_percentage",
                "s2:nodata_pixel_percentage",
                "s2:high_proba_clouds_percentage",
                "s2:thin_cirrus_percentage",
                "view:sun_azimuth",
                "view:sun_elevation",
            )
            if k in p
        },
    )


class EarthSearchProvider(Provider):
    name = "earth-search"

    def __init__(self, url: str | None = None, collection: str | None = None):
        s = get_settings()
        self.url = url or s.stac_url
        self.collection = collection or s.stac_collection
        self._client = None

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = Client.open(self.url)
        return self._client

    def search(self, bbox, start, end, max_cloud=60.0, limit=50):
        search = self.client.search(
            collections=[self.collection],
            bbox=list(bbox),
            datetime=f"{start}T00:00:00Z/{end}T23:59:59Z",
            query={"eo:cloud_cover": {"lte": max_cloud}},
            max_items=limit,
            sortby=[{"field": "properties.datetime", "direction": "asc"}],
        )
        return [_to_scene(it, self.collection) for it in search.items()]

    def get(self, scene_id: str) -> SceneInfo:
        item = self.client.get_collection(self.collection).get_item(scene_id)
        if item is None:
            raise KeyError(f"Scene {scene_id} not found in {self.collection}")
        return _to_scene(item, self.collection)


class EarthSearchLegacyProvider(EarthSearchProvider):
    """Legacy (non-reprocessed) L2A collection. Used to fill gaps in Collection 1 (e.g. 2022).

    Mixed processing baselines are harmonised in ingest: baseline >= 04.00 subtracts the
    1000 DN BOA_ADD_OFFSET, older baselines do not.
    """

    name = "earth-search-legacy"

    def __init__(self):
        super().__init__(collection="sentinel-2-l2a")

    def search(self, bbox, start, end, max_cloud=60.0, limit=50):
        scenes = super().search(bbox, start, end, max_cloud, limit)
        for s in scenes:
            s.provider = self.name
        return scenes

    def get(self, scene_id):
        s = super().get(scene_id)
        s.provider = self.name
        return s


def get_provider(name: str = "earth-search") -> Provider:
    if name == "earth-search":
        return EarthSearchProvider()
    if name == "earth-search-legacy":
        return EarthSearchLegacyProvider()
    if name == "cdse":
        from .cdse import CDSEProvider

        return CDSEProvider()
    raise ValueError(f"Unknown provider {name}")
