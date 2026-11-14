from __future__ import annotations

import shutil

import rasterio
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from forestwatch.ml.device import device_info
from forestwatch.settings import get_settings

from ...db.init import get_setting, set_setting
from ...db.models import AOI, ChangeRun, Evaluation, Experiment, Job, Product
from ...db.session import get_db
from ...services import serialize as S

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/system")
def system(db: Session = Depends(get_db)):
    s = get_settings()
    du = shutil.disk_usage(s.data_dir)
    jobs_running = db.scalar(select(func.count()).select_from(Job).where(Job.status == "running"))
    return {
        **device_info(),
        "gdal_version": rasterio.__gdal_version__,
        "rasterio_version": rasterio.__version__,
        "data_dir": str(s.data_dir),
        "disk_free_gb": du.free / 1e9,
        "stac_url": s.stac_url,
        "stac_collection": s.stac_collection,
        "cdse_configured": bool(s.cdse_username and s.cdse_password),
        "jobs_running": jobs_running,
        "max_aoi_km2": s.max_aoi_km2,
    }


class SettingsIn(BaseModel):
    active_aoi_id: str | None = None
    active_experiment_id: str | None = None


@router.get("/settings")
def get_settings_api(db: Session = Depends(get_db)):
    return {
        "active_aoi_id": get_setting(db, "active_aoi_id"),
        "active_experiment_id": get_setting(db, "active_experiment_id"),
    }


@router.put("/settings")
def put_settings(body: SettingsIn, db: Session = Depends(get_db)):
    if body.active_aoi_id is not None:
        set_setting(db, "active_aoi_id", body.active_aoi_id)
    if body.active_experiment_id is not None:
        set_setting(db, "active_experiment_id", body.active_experiment_id)
    return get_settings_api(db)


@router.get("/overview")
def overview(aoi_id: str | None = None, db: Session = Depends(get_db)):
    """Dashboard figures for an AOI - every value comes from stored analysis results."""
    aoi_id = aoi_id or get_setting(db, "active_aoi_id")
    aoi = db.get(AOI, aoi_id) if aoi_id else None
    products = (
        db.scalars(select(Product).where(Product.aoi_id == aoi_id).order_by(Product.acquired.desc())).all() if aoi else []
    )
    runs = (
        db.scalars(
            select(ChangeRun).where(ChangeRun.aoi_id == aoi_id).order_by(ChangeRun.created_at.desc()).limit(8)
        ).all()
        if aoi
        else []
    )
    latest_ok = next((r for r in runs if r.status == "succeeded"), None)
    exp_id = get_setting(db, "active_experiment_id")
    exp = db.get(Experiment, exp_id) if exp_id else None
    ev = (
        db.scalars(
            select(Evaluation)
            .where(Evaluation.experiment_id == exp_id, Evaluation.status == "succeeded")
            .order_by(Evaluation.created_at.desc())
        ).first()
        if exp
        else None
    )
    return {
        "aoi": S.aoi(aoi) if aoi else None,
        "observations": [S.product(p) for p in products[:12]],
        "n_observations": len(products),
        "latest_change": S.change_run(latest_ok, full=True) if latest_ok else None,
        "recent_runs": [S.change_run(r) for r in runs],
        "model": S.experiment(exp) if exp else None,
        "model_evaluation": S.evaluation(ev, full=False) if ev else None,
    }


DOC_ORDER = [
    ("overview", "Project overview"),
    ("methodology", "Methodology"),
    ("sentinel2", "Sentinel-2 & multispectral imagery"),
    ("unet", "U-Net model"),
    ("change-detection", "Change detection"),
    ("datasets", "Datasets & provenance"),
    ("model-card", "Model card"),
    ("limitations", "Limitations"),
    ("reproducibility", "Reproducibility"),
    ("references", "References"),
]


@router.get("/docs")
def list_docs():
    from forestwatch.settings import REPO_ROOT

    d = REPO_ROOT / "docs"
    return [{"slug": s, "title": t} for s, t in DOC_ORDER if (d / f"{s}.md").exists()]


@router.get("/docs/{slug}")
def get_doc(slug: str):
    from fastapi import HTTPException

    from forestwatch.settings import REPO_ROOT

    if slug not in dict(DOC_ORDER):
        raise HTTPException(404, "Unknown document")
    p = REPO_ROOT / "docs" / f"{slug}.md"
    if not p.exists():
        raise HTTPException(404, "Document not found")
    return {"slug": slug, "markdown": p.read_text(encoding="utf-8")}
