from __future__ import annotations

import shutil

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shapely.geometry import shape
from sqlalchemy import select
from sqlalchemy.orm import Session

from forestwatch.geo.grid import Grid, bbox_geojson, geodesic_area_km2
from forestwatch.geo.raster_io import write_cog
from forestwatch.labels.reference import hansen_on_grid, worldcover_on_grid
from forestwatch.settings import get_settings

from ...db.models import AOI
from ...db.session import get_db
from ...services import serialize as S
from ..deps import get_or_404

router = APIRouter(prefix="/aois", tags=["areas of interest"])


class AOIIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    bbox: list[float] | None = Field(None, description="[minlon, minlat, maxlon, maxlat]")
    geometry: dict | None = Field(None, description="GeoJSON Polygon in EPSG:4326 (its bounding box defines the grid)")


@router.get("")
def list_aois(db: Session = Depends(get_db)):
    return [S.aoi(a) for a in db.scalars(select(AOI).order_by(AOI.created_at)).all()]


@router.post("", status_code=201)
def create_aoi(body: AOIIn, db: Session = Depends(get_db)):
    if body.geometry:
        g = shape(body.geometry)
        if g.is_empty or not g.is_valid:
            raise HTTPException(422, "Invalid geometry")
        bbox = list(g.bounds)
        geom = body.geometry
    elif body.bbox and len(body.bbox) == 4:
        bbox = body.bbox
        geom = bbox_geojson(tuple(bbox))
    else:
        raise HTTPException(422, "Provide bbox or geometry")
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -85 <= bbox[1] < bbox[3] <= 85):
        raise HTTPException(422, "bbox out of range or inverted")
    area = geodesic_area_km2(bbox_geojson(tuple(bbox)))
    limit = get_settings().max_aoi_km2
    if area > limit:
        raise HTTPException(422, f"AOI bounding box is {area:.0f} km2; the limit is {limit:.0f} km2 (SYLVA_MAX_AOI_KM2)")
    if area < 0.5:
        raise HTTPException(422, "AOI is too small (< 0.5 km2)")
    aoi = AOI(
        name=body.name,
        description=body.description,
        bbox=bbox,
        geometry=geom,
        grid=Grid.from_bbox_lonlat(tuple(bbox)).to_dict(),
        area_km2=area,
    )
    db.add(aoi)
    db.commit()
    return S.aoi(aoi)


@router.get("/{aoi_id}")
def get_aoi(aoi_id: str, db: Session = Depends(get_db)):
    return S.aoi(get_or_404(db, AOI, aoi_id))


@router.delete("/{aoi_id}", status_code=204)
def delete_aoi(aoi_id: str, db: Session = Depends(get_db)):
    aoi = get_or_404(db, AOI, aoi_id)
    db.delete(aoi)
    db.commit()
    shutil.rmtree(get_settings().data_dir / "products" / aoi_id, ignore_errors=True)


REFERENCE_LAYERS = {
    "worldcover2021": ("ESA WorldCover 2021 v200", lambda g: worldcover_on_grid(g, 2021), 0),
    "worldcover2020": ("ESA WorldCover 2020 v100", lambda g: worldcover_on_grid(g, 2020), 0),
    "hansen_lossyear": ("Hansen GFC-2025-v1.13 loss year", lambda g: hansen_on_grid(g, "lossyear"), None),
}


def reference_path(aoi: AOI, layer: str):
    if layer not in REFERENCE_LAYERS:
        raise HTTPException(404, f"Unknown reference layer {layer}")
    p = get_settings().path("reference", aoi.id) / f"{layer}.tif"
    if not p.exists():
        _, fn, nodata = REFERENCE_LAYERS[layer]
        grid = Grid.from_dict(aoi.grid)
        write_cog(p, fn(grid), grid, nodata=nodata, resampling_overview="nearest")
    return p


@router.post("/{aoi_id}/reference/{layer}")
def prepare_reference(aoi_id: str, layer: str, db: Session = Depends(get_db)):
    """Fetch and cache a reference layer (WorldCover / Hansen) on the AOI grid."""
    aoi = get_or_404(db, AOI, aoi_id)
    try:
        reference_path(aoi, layer)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Could not fetch reference data: {e}") from e
    return {"layer": layer, "name": REFERENCE_LAYERS[layer][0], "tiles": f"/api/tiles/aoiref/{aoi_id}:{layer}/{{z}}/{{x}}/{{y}}.png"}
