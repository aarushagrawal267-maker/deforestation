from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import rasterio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from pyproj import Transformer
from sqlalchemy import select
from sqlalchemy.orm import Session

from forestwatch.labels.classes import CLASS_NAMES
from forestwatch.preprocessing.bands import BAND_NAMES
from forestwatch.preprocessing.masking import QUALITY_NAMES

from ...db.models import AOI, Job, Product, SegmentationRun
from ...db.session import get_db
from ...jobs.queue import enqueue
from ...services import serialize as S
from ...services.tiles import render_image
from ..deps import get_or_404

router = APIRouter(prefix="/products", tags=["observations"])


class IngestIn(BaseModel):
    aoi_id: str
    scene_ids: list[str] = Field(..., min_length=1, max_length=12)
    mode: str = Field("single", pattern="^(single|composite)$")
    provider: str = Field("earth-search", pattern="^(earth-search|earth-search-legacy)$")


@router.get("")
def list_products(aoi_id: str | None = None, db: Session = Depends(get_db)):
    q = select(Product).order_by(Product.acquired)
    if aoi_id:
        q = q.where(Product.aoi_id == aoi_id)
    return [S.product(p) for p in db.scalars(q).all()]


@router.post("/ingest", status_code=202)
def ingest(body: IngestIn, db: Session = Depends(get_db)):
    """Queue a job that reads the AOI window of the selected scenes into an analysis-ready observation."""
    get_or_404(db, AOI, body.aoi_id)
    job = enqueue(db, "ingest", body.model_dump())
    return S.job(job)


@router.get("/{product_id}")
def get_product(product_id: str, db: Session = Depends(get_db)):
    return S.product(get_or_404(db, Product, product_id))


@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id)
    path = Path(p.path)
    try:
        db.delete(p)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(409, "Observation is used by an analysis; delete that first") from e
    shutil.rmtree(path, ignore_errors=True)


def _sample(path: Path, lon: float, lat: float) -> tuple[list[float], tuple[int, int]] | None:
    with rasterio.open(path) as src:
        x, y = Transformer.from_crs(4326, src.crs, always_xy=True).transform(lon, lat)
        row, col = src.index(x, y)
        if not (0 <= row < src.height and 0 <= col < src.width):
            return None
        vals = src.read(window=((row, row + 1), (col, col + 1)))[:, 0, 0]
        return [float(v) for v in vals], (int(row), int(col))


@router.get("/{product_id}/pixel")
def pixel(product_id: str, lon: float, lat: float, segmentation_id: str | None = None, db: Session = Depends(get_db)):
    """Band reflectances, indices and (optionally) U-Net probabilities at a location."""
    p = get_or_404(db, Product, product_id)
    s = _sample(Path(p.path) / "stack.tif", lon, lat)
    if s is None:
        raise HTTPException(404, "Location outside the observation grid")
    vals, (row, col) = s
    qv = _sample(Path(p.path) / "quality.tif", lon, lat)[0][0]
    refl = {b: (None if v == -32768 else v / 10000) for b, v in zip(BAND_NAMES, vals)}

    def nd(a, b):
        if refl[a] is None or refl[b] is None or (refl[a] + refl[b]) == 0:
            return None
        return (refl[a] - refl[b]) / (refl[a] + refl[b])

    out = {
        "lon": lon,
        "lat": lat,
        "row": row,
        "col": col,
        "quality": QUALITY_NAMES.get(int(qv), str(qv)),
        "reflectance": refl,
        "indices": {"NDVI": nd("B8", "B4"), "NBR": nd("B8", "B12"), "NDMI": nd("B8", "B11")},
    }
    if segmentation_id:
        seg = get_or_404(db, SegmentationRun, segmentation_id)
        if seg.path:
            pv = _sample(Path(seg.path) / "probs.tif", lon, lat)
            if pv:
                out["probabilities"] = {
                    n: (None if v == 255 else v / 250) for n, v in zip(CLASS_NAMES, pv[0])
                }
    return out


@router.get("/{product_id}/chip.png")
def chip(
    product_id: str,
    bbox: str = Query(..., description="minlon,minlat,maxlon,maxlat"),
    render: str = "truecolor",
    band: str | None = None,
    size: int = Query(384, ge=64, le=1024),
    db: Session = Depends(get_db),
):
    p = get_or_404(db, Product, product_id)
    b = tuple(float(v) for v in bbox.split(","))
    try:
        png = render_image(Path(p.path) / "stack.tif", render, band, bbox=b, size=size)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return Response(png, media_type="image/png")


@router.get("/{product_id}/histogram")
def histogram(product_id: str, db: Session = Depends(get_db)):
    p = get_or_404(db, Product, product_id)
    with rasterio.open(Path(p.path) / "stack.tif") as src:
        ovr = src.read(out_shape=(src.count, max(1, src.height // 4), max(1, src.width // 4)))
    out = {}
    for b, arr in zip(BAND_NAMES, ovr):
        v = arr[arr != -32768] / 10000
        if v.size == 0:
            continue
        h, edges = np.histogram(v, bins=40, range=(0, 0.6))
        out[b] = {
            "counts": h.tolist(),
            "edges": edges.tolist(),
            "mean": float(v.mean()),
            "p2": float(np.percentile(v, 2)),
            "p98": float(np.percentile(v, 98)),
        }
    return out


@router.get("/{product_id}/jobs")
def product_jobs(product_id: str, db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(50)).all()
    return [S.job(j) for j in jobs if j.params.get("product_id") == product_id]
