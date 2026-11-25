from __future__ import annotations

import asyncio
import csv
import io
import json
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from forestwatch.change.compare import CATEGORIES, ChangeParams
from forestwatch.settings import get_settings

from ...db.init import get_setting
from ...db.models import AOI, ChangeRegion, ChangeRun, Experiment, Export, Job, Product, SegmentationRun, short_id
from ...db.session import SessionLocal, get_db
from ...jobs.queue import enqueue
from ...services import serialize as S
from ..deps import get_or_404

router = APIRouter(tags=["analysis"])


def _model_id(db, experiment_id: str | None) -> str:
    eid = experiment_id or get_setting(db, "active_experiment_id")
    if not eid:
        raise HTTPException(409, "No trained model selected. Train one in the Model Laboratory and activate it.")
    exp = get_or_404(db, Experiment, eid)
    if not exp.checkpoint:
        raise HTTPException(409, "Selected experiment has no trained checkpoint")
    if not Path(exp.checkpoint).is_file():
        raise HTTPException(
            409,
            f"The checkpoint file of model '{exp.name}' is missing ({exp.checkpoint}). "
            "Restart the app to reinstall the bundled models, or activate another model in the Model Laboratory.",
        )
    return eid


# ---------------------------------------------------------------- segmentation
class SegmentIn(BaseModel):
    product_id: str
    experiment_id: str | None = None


@router.get("/segmentations")
def list_segmentations(aoi_id: str | None = None, db: Session = Depends(get_db)):
    rows = db.scalars(select(SegmentationRun).order_by(SegmentationRun.created_at.desc())).all()
    return [S.segmentation(r) for r in rows if not aoi_id or (r.product and r.product.aoi_id == aoi_id)]


@router.post("/segmentations", status_code=202)
def create_segmentation(body: SegmentIn, db: Session = Depends(get_db)):
    get_or_404(db, Product, body.product_id)
    run = SegmentationRun(product_id=body.product_id, experiment_id=_model_id(db, body.experiment_id))
    db.add(run)
    db.commit()
    job = enqueue(db, "segment", {"segmentation_id": run.id})
    run.job_id = job.id
    db.commit()
    return S.segmentation(run)


@router.get("/segmentations/{seg_id}")
def get_segmentation(seg_id: str, db: Session = Depends(get_db)):
    return S.segmentation(get_or_404(db, SegmentationRun, seg_id))


# ---------------------------------------------------------------- change detection
class ChangeIn(BaseModel):
    aoi_id: str
    before_id: str
    after_id: str
    extra_ids: list[str] = Field(default_factory=list, description="Later observations used for the persistence check")
    experiment_id: str | None = None
    params: dict = Field(default_factory=dict)


@router.get("/change/categories")
def categories():
    return {"categories": CATEGORIES, "default_params": ChangeParams().to_dict()}


@router.get("/change-runs")
def list_change_runs(aoi_id: str | None = None, db: Session = Depends(get_db)):
    q = select(ChangeRun).order_by(ChangeRun.created_at.desc())
    if aoi_id:
        q = q.where(ChangeRun.aoi_id == aoi_id)
    return [S.change_run(r) for r in db.scalars(q).all()]


@router.post("/change-runs", status_code=202)
def create_change_run(body: ChangeIn, db: Session = Depends(get_db)):
    get_or_404(db, AOI, body.aoi_id)
    ps = [get_or_404(db, Product, pid) for pid in [body.before_id, body.after_id, *body.extra_ids]]
    if any(p.aoi_id != body.aoi_id for p in ps):
        raise HTTPException(422, "All observations must belong to the selected AOI")
    if ps[0].acquired >= ps[1].acquired:
        raise HTTPException(422, "The earlier observation must be acquired before the later observation")
    if any(p.acquired <= ps[1].acquired for p in ps[2:]):
        raise HTTPException(422, "Persistence observations must be later than the 'after' observation")
    params = ChangeParams.from_dict(body.params).to_dict()
    run = ChangeRun(
        aoi_id=body.aoi_id,
        before_id=body.before_id,
        after_id=body.after_id,
        extra_ids=body.extra_ids,
        experiment_id=_model_id(db, body.experiment_id),
        params=params,
    )
    db.add(run)
    db.commit()
    job = enqueue(db, "change", {"change_run_id": run.id})
    run.job_id = job.id
    db.commit()
    return S.change_run(run)


@router.get("/change-runs/{run_id}")
def get_change_run(run_id: str, db: Session = Depends(get_db)):
    return S.change_run(get_or_404(db, ChangeRun, run_id), full=True)


@router.delete("/change-runs/{run_id}", status_code=204)
def delete_change_run(run_id: str, db: Session = Depends(get_db)):
    r = get_or_404(db, ChangeRun, run_id)
    db.delete(r)
    db.commit()


@router.get("/change-runs/{run_id}/regions")
def change_regions_geojson(run_id: str, change_type: str | None = None, db: Session = Depends(get_db)):
    get_or_404(db, ChangeRun, run_id)
    q = select(ChangeRegion).where(ChangeRegion.run_id == run_id)
    if change_type:
        q = q.where(ChangeRegion.change_type == change_type)
    feats = [
        {
            "type": "Feature",
            "id": g.id,
            "geometry": g.geometry,
            "properties": {**g.properties, "review_status": g.review_status},
        }
        for g in db.scalars(q).all()
    ]
    return {"type": "FeatureCollection", "features": feats}


@router.get("/regions")
def list_regions(
    run_id: str | None = None,
    change_type: str | None = None,
    evidence_level: str | None = None,
    min_area_ha: float = 0,
    sort: str = Query("area_desc", pattern="^(area_desc|area_asc|id)$"),
    limit: int = Query(500, le=5000),
    db: Session = Depends(get_db),
):
    q = select(ChangeRegion).where(ChangeRegion.area_ha >= min_area_ha)
    if run_id:
        q = q.where(ChangeRegion.run_id == run_id)
    if change_type:
        q = q.where(ChangeRegion.change_type == change_type)
    if evidence_level:
        q = q.where(ChangeRegion.evidence_level == evidence_level)
    order = {
        "area_desc": ChangeRegion.area_ha.desc(),
        "area_asc": ChangeRegion.area_ha.asc(),
        "id": ChangeRegion.id,
    }[sort]
    return [S.region(g, with_geometry=False) for g in db.scalars(q.order_by(order).limit(limit)).all()]


@router.get("/regions/{region_id}")
def get_region(region_id: str, db: Session = Depends(get_db)):
    g = get_or_404(db, ChangeRegion, region_id)
    run = g.run
    d = S.region(g)
    d["run"] = S.change_run(run)
    d["run_summary"] = {
        k: (run.summary or {}).get(k)
        for k in ("hansen_reference", "worldcover_reference", "coregistration", "calibrated", "checkpoint_sha256", "params", "area_note")
    }
    d["before"] = S.product(run.before)
    d["after"] = S.product(run.after)
    return d


class ReviewIn(BaseModel):
    review_status: str = Field(..., pattern="^(unreviewed|likely_loss|likely_false_positive|uncertain)$")
    analyst_notes: str = ""


@router.put("/regions/{region_id}/review")
def review_region(region_id: str, body: ReviewIn, db: Session = Depends(get_db)):
    g = get_or_404(db, ChangeRegion, region_id)
    g.review_status, g.analyst_notes = body.review_status, body.analyst_notes
    db.commit()
    return S.region(g, with_geometry=False)


# ---------------------------------------------------------------- history
@router.get("/history")
def history(db: Session = Depends(get_db)):
    items = []
    for p in db.scalars(select(Product)).all():
        items.append({"type": "observation", "id": p.id, "at": S.iso(p.created_at), "aoi_id": p.aoi_id, "detail": S.product(p)})
    for r in db.scalars(select(ChangeRun)).all():
        items.append({"type": "change_run", "id": r.id, "at": S.iso(r.created_at), "aoi_id": r.aoi_id, "detail": S.change_run(r)})
    for s in db.scalars(select(SegmentationRun)).all():
        items.append({"type": "segmentation", "id": s.id, "at": S.iso(s.created_at), "aoi_id": s.product.aoi_id if s.product else None, "detail": S.segmentation(s)})
    for e in db.scalars(select(Experiment)).all():
        items.append({"type": "experiment", "id": e.id, "at": S.iso(e.created_at), "aoi_id": None, "detail": S.experiment(e)})
    for x in db.scalars(select(Export)).all():
        items.append({"type": "export", "id": x.id, "at": S.iso(x.created_at), "aoi_id": None, "detail": S.export(x)})
    items.sort(key=lambda i: i["at"] or "", reverse=True)
    return items


# ---------------------------------------------------------------- exports
class ExportIn(BaseModel):
    source_type: str = Field(..., pattern="^(change_run|segmentation|region|observation)$")
    source_id: str
    format: str = Field(..., pattern="^(geojson|gpkg|csv|geotiff|bundle)$")


def _provenance(db, source_type: str, obj) -> dict:
    base = {
        "generator": "Sylva forest change platform (independent educational/research implementation)",
        "disclaimer": "Potential forest-cover change derived from Sentinel-2 imagery and a U-Net model. "
        "Not verified deforestation; satellite data alone cannot establish the cause of change.",
        "attribution": [
            "Contains modified Copernicus Sentinel data",
            "ESA WorldCover (CC BY 4.0)",
            "Hansen/UMD/Google/USGS/NASA Global Forest Change (CC BY 4.0)",
        ],
    }
    if source_type == "change_run":
        base["change_run"] = S.change_run(obj, full=True)
        base["before"] = S.product(obj.before)
        base["after"] = S.product(obj.after)
        exp = db.get(Experiment, obj.experiment_id)
        base["model"] = S.experiment(exp)
    elif source_type == "segmentation":
        base["segmentation"] = S.segmentation(obj)
        base["observation"] = S.product(obj.product)
        base["model"] = S.experiment(db.get(Experiment, obj.experiment_id))
    elif source_type == "observation":
        base["observation"] = S.product(obj)
    elif source_type == "region":
        base["region"] = S.region(obj, with_geometry=False)
    return base


def _regions_fc(db, run_id: str) -> dict:
    return change_regions_geojson(run_id, None, db)


@router.post("/exports", status_code=201)
def create_export(body: ExportIn, db: Session = Depends(get_db)):
    s = get_settings()
    out_dir = s.path("exports")
    eid = short_id("export_")
    files: dict[str, bytes | Path] = {}
    if body.source_type == "change_run":
        obj = get_or_404(db, ChangeRun, body.source_id)
        if obj.status != "succeeded":
            raise HTTPException(409, "Change run not finished")
        fc = _regions_fc(db, obj.id)
        if body.format in ("geojson", "bundle"):
            files["regions.geojson"] = json.dumps(fc).encode()
        if body.format in ("gpkg", "bundle"):
            import geopandas as gpd

            gdf = gpd.GeoDataFrame.from_features(fc["features"], crs="EPSG:4326")
            for c in gdf.columns:
                if gdf[c].dtype == object and c != "geometry":
                    gdf[c] = gdf[c].astype(str)
            tmp = out_dir / f"{eid}.gpkg"
            if len(gdf):
                gdf.to_file(tmp, driver="GPKG", layer="potential_change")
                files["regions.gpkg"] = tmp
        if body.format in ("csv", "bundle"):
            buf = io.StringIO()
            keys = ["id", "change_type", "evidence_level", "area_ha", "area_uncertainty_ha", "centroid_lon", "centroid_lat",
                    "p_tree_before", "p_tree_after", "delta_p_tree", "delta_ndvi", "delta_nbr", "delta_ndmi",
                    "hansen_loss_fraction", "date_before", "date_after", "review_status"]
            w = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            for f in fc["features"]:
                w.writerow(f["properties"])
            files["regions.csv"] = buf.getvalue().encode()
        if body.format in ("geotiff", "bundle"):
            files["change_category.tif"] = Path(obj.path) / "category.tif"
            files["delta_p_tree_x100.tif"] = Path(obj.path) / "delta_p_tree.tif"
            files["forest_probability_before.tif"] = Path(obj.path) / "seg_0" / "probs.tif"
            files["forest_probability_after.tif"] = Path(obj.path) / "seg_1" / "probs.tif"
    elif body.source_type == "segmentation":
        obj = get_or_404(db, SegmentationRun, body.source_id)
        if obj.status != "succeeded":
            raise HTTPException(409, "Segmentation not finished")
        if body.format not in ("geotiff", "bundle"):
            raise HTTPException(422, "Segmentations export as geotiff or bundle")
        files["class_probabilities_x250.tif"] = Path(obj.path) / "probs.tif"
        files["class_map.tif"] = Path(obj.path) / "class.tif"
        files["entropy_x250.tif"] = Path(obj.path) / "entropy.tif"
    elif body.source_type == "observation":
        obj = get_or_404(db, Product, body.source_id)
        files["reflectance_x10000.tif"] = Path(obj.path) / "stack.tif"
        files["quality.tif"] = Path(obj.path) / "quality.tif"
    else:
        obj = get_or_404(db, ChangeRegion, body.source_id)
        files["region.geojson"] = json.dumps(
            {"type": "Feature", "id": obj.id, "geometry": obj.geometry, "properties": obj.properties}
        ).encode()
    if not files:
        raise HTTPException(422, "Nothing to export for this format")
    files["provenance.json"] = json.dumps(_provenance(db, body.source_type, obj), indent=2, default=str).encode()
    path = out_dir / f"{eid}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            if isinstance(content, Path):
                z.write(content, name)
            else:
                z.writestr(name, content)
    (out_dir / f"{eid}.gpkg").unlink(missing_ok=True)
    x = Export(id=eid, source_type=body.source_type, source_id=body.source_id, format=body.format, path=str(path), size_bytes=path.stat().st_size)
    db.add(x)
    db.commit()
    return S.export(x)


@router.get("/exports")
def list_exports(db: Session = Depends(get_db)):
    return [S.export(x) for x in db.scalars(select(Export).order_by(Export.created_at.desc())).all()]


@router.get("/exports/{export_id}/download")
def download_export(export_id: str, db: Session = Depends(get_db)):
    x = get_or_404(db, Export, export_id)
    return FileResponse(x.path, filename=f"sylva_{x.source_type}_{x.source_id}_{x.format}.zip", media_type="application/zip")


# ---------------------------------------------------------------- jobs
@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    q = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status:
        q = q.where(Job.status == status)
    return [S.job(j) for j in db.scalars(q).all()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return S.job(get_or_404(db, Job, job_id), with_log=True)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    j = get_or_404(db, Job, job_id)
    if j.status in ("queued", "running"):
        j.cancel_requested = True
        if j.status == "queued":
            j.status = "cancelled"
        db.commit()
    return S.job(j)


@router.get("/jobs/{job_id}/events")
async def job_events(job_id: str):
    """Server-Sent Events stream of job progress (from the worker's real updates)."""

    async def gen():
        last = None
        while True:
            with SessionLocal() as db:
                j = db.get(Job, job_id)
                if j is None:
                    yield "event: error\ndata: {\"error\": \"not found\"}\n\n"
                    return
                d = S.job(j)
            payload = json.dumps(d)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if d["status"] in ("succeeded", "failed", "cancelled"):
                return
            await asyncio.sleep(1)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
