from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from forestwatch.preprocessing.bands import describe_bands
from forestwatch.providers.earth_search import get_provider
from forestwatch.settings import get_settings

from ...db.models import AOI
from ...db.session import get_db
from ..deps import get_or_404

router = APIRouter(prefix="/catalog", tags=["catalog"])


class SearchIn(BaseModel):
    aoi_id: str
    start: date
    end: date
    max_cloud: float = Field(60, ge=0, le=100)
    provider: str = "earth-search"
    limit: int = Field(100, ge=1, le=500)


@router.get("/providers")
def providers():
    s = get_settings()
    return [
        {
            "id": "earth-search",
            "name": "Earth Search (Element 84, AWS Open Data)",
            "collection": s.stac_collection,
            "auth": "none",
            "role": "primary: windowed COG reads",
            "available": True,
        },
        {
            "id": "earth-search-legacy",
            "name": "Earth Search legacy L2A (sentinel-2-l2a)",
            "collection": "sentinel-2-l2a",
            "auth": "none",
            "role": "gap filler where Collection 1 is incomplete (e.g. 2022); baselines harmonised",
            "available": True,
        },
        {
            "id": "cdse",
            "name": "Copernicus Data Space Ecosystem (ESA)",
            "collection": "sentinel-2-l2a",
            "auth": "free account for downloads (catalogue search is open)",
            "role": "official catalogue cross-check",
            "available": True,
            "credentials_configured": bool(s.cdse_username and s.cdse_password),
        },
    ]


@router.get("/bands")
def bands():
    return describe_bands()


@router.post("/search")
def search(body: SearchIn, db: Session = Depends(get_db)):
    """Search available Sentinel-2 L2A acquisitions intersecting the AOI (not a live feed)."""
    aoi = get_or_404(db, AOI, body.aoi_id)
    if body.end < body.start:
        raise HTTPException(422, "end must be after start")
    try:
        scenes = get_provider(body.provider).search(
            tuple(aoi.bbox), body.start.isoformat(), body.end.isoformat(), body.max_cloud, body.limit
        )
    except Exception as e:
        raise HTTPException(502, f"Catalogue search failed: {e}") from e
    return [
        {
            "id": s.id,
            "provider": s.provider,
            "datetime": s.datetime.isoformat(),
            "date": s.datetime.date().isoformat(),
            "platform": s.platform,
            "cloud_cover": s.cloud_cover,
            "mgrs_tile": s.mgrs_tile,
            "processing_baseline": s.processing_baseline,
            "thumbnail": s.thumbnail,
            "bbox": s.bbox,
            "geometry": s.geometry,
            "properties": s.properties,
        }
        for s in scenes
    ]
