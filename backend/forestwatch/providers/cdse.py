"""Copernicus Data Space Ecosystem (official ESA) catalogue provider.

Catalogue search through the CDSE STAC API is open. Downloading CDSE product
assets requires a free CDSE account (credentials read from ``.env``:
``SYLVA_CDSE_USERNAME`` / ``SYLVA_CDSE_PASSWORD``). Sylva's analysis-ready
pipeline uses Earth Search COGs for windowed reads; CDSE is used for official
catalogue cross-checks and provenance. Asset download through CDSE is not yet
verified end-to-end (no credentials were available during development).
"""

from __future__ import annotations

import httpx

from ..settings import get_settings
from .earth_search import EarthSearchProvider

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"


class CDSEProvider(EarthSearchProvider):
    name = "cdse"

    def __init__(self):
        super().__init__(url="https://stac.dataspace.copernicus.eu/v1", collection="sentinel-2-l2a")

    def search(self, bbox, start, end, max_cloud=60.0, limit=50):
        scenes = super().search(bbox, start, end, max_cloud, limit)
        for s in scenes:
            s.provider = "cdse"
        return scenes

    def access_token(self) -> str:
        s = get_settings()
        if not (s.cdse_username and s.cdse_password):
            raise PermissionError(
                "CDSE credentials are not configured. Set SYLVA_CDSE_USERNAME and "
                "SYLVA_CDSE_PASSWORD in .env (free account at dataspace.copernicus.eu)."
            )
        r = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": "cdse-public",
                "username": s.cdse_username,
                "password": s.cdse_password.get_secret_value(),
            },
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["access_token"]
