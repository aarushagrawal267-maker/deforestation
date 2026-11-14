from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from forestwatch.ml.train import TrainConfig
from forestwatch.preprocessing.bands import BAND_NAMES
from forestwatch.regions import region_split
from forestwatch.settings import get_settings

from ...db.init import get_setting, set_setting
from ...db.models import Evaluation, Experiment, Job
from ...db.session import get_db
from ...jobs.queue import enqueue
from ...services import serialize as S
from ..deps import get_or_404

router = APIRouter(tags=["model laboratory"])


class ExperimentIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    notes: str = ""
    train_regions: list[str] | None = None
    val_regions: list[str] | None = None
    test_regions: list[str] | None = None
    bands: list[str] = Field(default_factory=lambda: list(BAND_NAMES))
    base: int = Field(32, ge=8, le=64)
    depth: int = Field(4, ge=2, le=5)
    dropout: float = Field(0.2, ge=0, le=0.6)
    up_mode: str = Field("bilinear", pattern="^(bilinear|transpose)$")
    epochs: int = Field(20, ge=1, le=200)
    batch_size: int = Field(8, ge=1, le=64)
    samples_per_epoch: int = Field(400, ge=16, le=20000)
    crop: int = Field(256, ge=64, le=512)
    lr: float = Field(1e-3, gt=0, le=0.1)
    weight_decay: float = Field(1e-4, ge=0, le=0.1)
    loss: str = Field("ce_dice", pattern="^(ce|dice|ce_dice)$")
    dice_weight: float = Field(0.5, ge=0, le=5)
    augment: bool = True
    early_stopping_patience: int = Field(8, ge=1, le=100)
    seed: int = 42
    start: bool = True


@router.get("/experiments")
def list_experiments(db: Session = Depends(get_db)):
    return [S.experiment(e) for e in db.scalars(select(Experiment).order_by(Experiment.created_at.desc())).all()]


@router.post("/experiments", status_code=201)
def create_experiment(body: ExperimentIn, db: Session = Depends(get_db)):
    split = region_split(get_settings().path("regions"))
    cfg = body.model_dump(exclude={"name", "notes", "start"})
    cfg["train_regions"] = body.train_regions or split["train"]
    cfg["val_regions"] = body.val_regions or split["val"]
    cfg["test_regions"] = body.test_regions or split["test"]
    bad = [b for b in body.bands if b not in BAND_NAMES]
    if bad or not body.bands:
        raise HTTPException(422, f"Unknown bands {bad}")
    leak = set(cfg["train_regions"]) & (set(cfg["val_regions"]) | set(cfg["test_regions"]))
    if leak:
        raise HTTPException(422, f"Regions cannot be in both training and validation/test: {sorted(leak)}")
    if not cfg["train_regions"] or not cfg["val_regions"]:
        raise HTTPException(422, "Build training regions first (Dataset Explorer) - none are available")
    TrainConfig.from_dict(cfg)
    exp = Experiment(name=body.name, notes=body.notes, config=cfg)
    db.add(exp)
    db.commit()
    if body.start:
        job = enqueue(db, "train", {"experiment_id": exp.id})
        exp.job_id, exp.status = job.id, "queued"
        db.commit()
    return S.experiment(exp)


@router.get("/experiments/{exp_id}")
def get_experiment(exp_id: str, db: Session = Depends(get_db)):
    return S.experiment(get_or_404(db, Experiment, exp_id), with_epochs=True)


@router.post("/experiments/{exp_id}/train", status_code=202)
def start_training(exp_id: str, db: Session = Depends(get_db)):
    exp = get_or_404(db, Experiment, exp_id)
    if exp.status in ("queued", "running"):
        raise HTTPException(409, "Experiment already queued or running")
    job = enqueue(db, "train", {"experiment_id": exp.id})
    exp.job_id, exp.status = job.id, "queued"
    db.commit()
    return S.job(job)


@router.post("/experiments/{exp_id}/cancel")
def cancel_training(exp_id: str, db: Session = Depends(get_db)):
    exp = get_or_404(db, Experiment, exp_id)
    if exp.job_id:
        job = db.get(Job, exp.job_id)
        if job and job.status in ("queued", "running"):
            job.cancel_requested = True
            if job.status == "queued":
                job.status = "cancelled"
                exp.status = "cancelled"
            db.commit()
    return S.experiment(exp)


@router.post("/experiments/{exp_id}/activate")
def activate(exp_id: str, db: Session = Depends(get_db)):
    exp = get_or_404(db, Experiment, exp_id)
    if not exp.checkpoint:
        raise HTTPException(409, "Experiment has no trained checkpoint")
    set_setting(db, "active_experiment_id", exp.id)
    return {"active_experiment_id": exp.id}


@router.delete("/experiments/{exp_id}", status_code=204)
def delete_experiment(exp_id: str, db: Session = Depends(get_db)):
    exp = get_or_404(db, Experiment, exp_id)
    if exp.status in ("queued", "running"):
        raise HTTPException(409, "Cancel the experiment first")
    if get_setting(db, "active_experiment_id") == exp_id:
        raise HTTPException(409, "This is the active model; activate another first")
    try:
        db.delete(exp)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(409, "Experiment is referenced by analyses") from e


class EvaluationIn(BaseModel):
    experiment_id: str
    regions: list[str] | None = None


@router.get("/evaluations")
def list_evaluations(experiment_id: str | None = None, db: Session = Depends(get_db)):
    q = select(Evaluation).order_by(Evaluation.created_at.desc())
    if experiment_id:
        q = q.where(Evaluation.experiment_id == experiment_id)
    return [S.evaluation(e, full=False) for e in db.scalars(q).all()]


@router.post("/evaluations", status_code=202)
def create_evaluation(body: EvaluationIn, db: Session = Depends(get_db)):
    exp = get_or_404(db, Experiment, body.experiment_id)
    if not exp.checkpoint:
        raise HTTPException(409, "Experiment has no trained checkpoint")
    regions = body.regions or exp.config.get("test_regions") or []
    if not regions:
        raise HTTPException(422, "No test regions")
    leak = set(regions) & set(exp.config.get("train_regions", []))
    if leak:
        raise HTTPException(422, f"Cannot evaluate on training regions: {sorted(leak)}")
    ev = Evaluation(experiment_id=exp.id, regions=regions)
    db.add(ev)
    db.commit()
    job = enqueue(db, "evaluate", {"evaluation_id": ev.id})
    ev.job_id = job.id
    db.commit()
    return S.evaluation(ev)


@router.get("/evaluations/{eval_id}")
def get_evaluation(eval_id: str, db: Session = Depends(get_db)):
    return S.evaluation(get_or_404(db, Evaluation, eval_id))
