from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from forestwatch.settings import get_settings

from ...db.models import AOI, ChangeRun, Evaluation, Product, SegmentationRun
from ...db.session import get_db
from ...services.tiles import render_image
from ..deps import get_or_404
from .aois import reference_path

router = APIRouter(prefix="/tiles", tags=["map tiles"])

DEFAULT_RENDER = {"product": "truecolor", "seg": "prob", "change": "change", "region": "truecolor", "aoiref": "worldcover"}


def resolve(db: Session, source: str, ref: str, render: str) -> Path:
    """Map (source, ref, render) to a local COG path."""
    if source == "product":
        return Path(get_or_404(db, Product, ref).path) / "stack.tif"
    if source == "seg":
        s = get_or_404(db, SegmentationRun, ref)
        if not s.path:
            raise HTTPException(409, "Segmentation not finished")
        return Path(s.path) / {"prob": "probs.tif", "class": "class.tif", "entropy": "entropy.tif"}.get(render, "probs.tif")
    if source == "change":
        r = get_or_404(db, ChangeRun, ref)
        if not r.path:
            raise HTTPException(409, "Change run not finished")
        if render in ("prob_before", "prob_after"):
            return Path(r.path) / ("seg_0" if render == "prob_before" else "seg_1") / "probs.tif"
        return Path(r.path) / ("delta_p_tree.tif" if render == "delta" else "category.tif")
    if source == "region":
        d = get_settings().data_dir / "regions" / ref
        f = {
            "labels": "labels.tif",
            "worldcover": "worldcover.tif",
            "lossyear": "hansen_lossyear.tif",
        }.get(render, "stack.tif")
        if not (d / f).exists():
            raise HTTPException(404, "Region layer not found")
        return d / f
    if source == "evalpred":
        ev_id, region = ref.split(":", 1)
        ev = get_or_404(db, Evaluation, ev_id)
        p = Path(ev.path or "") / f"{region}_pred.tif"
        if not p.exists():
            raise HTTPException(404, "Evaluation prediction not found")
        return p
    if source == "aoiref":
        aoi_id, layer = ref.split(":", 1)
        return reference_path(get_or_404(db, AOI, aoi_id), layer)
    raise HTTPException(404, f"Unknown tile source {source}")


@router.get("/{source}/{ref}/{z}/{x}/{y}.png")
def tile(source: str, ref: str, z: int, x: int, y: int, render: str | None = None, band: str | None = None, db: Session = Depends(get_db)):
    render = render or DEFAULT_RENDER.get(source, "truecolor")
    if source == "change" and render in ("prob_before", "prob_after"):
        path, rr = resolve(db, source, ref, render), "prob"
    elif source == "aoiref":
        path = resolve(db, source, ref, render)
        rr = "lossyear" if ref.endswith("hansen_lossyear") else "worldcover"
    elif source == "evalpred":
        path, rr = resolve(db, source, ref, render), "class"
    else:
        path, rr = resolve(db, source, ref, render), render
    try:
        png = render_image(path, rr, band, tile=(x, y, z))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})
