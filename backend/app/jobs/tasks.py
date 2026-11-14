"""Job implementations. Each function receives (params, ctx) and returns a JSON-able result."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from forestwatch.change.compare import ChangeParams
from forestwatch.geo.grid import Grid
from forestwatch.ml.train import Callbacks, TrainConfig, train
from forestwatch.pipeline import detect_change, segment_product
from forestwatch.preprocessing.ingest import composite, group_by_acquisition, ingest_scene
from forestwatch.providers.earth_search import get_provider
from forestwatch.settings import get_settings

from ..db.models import (
    AOI,
    ChangeRegion,
    ChangeRun,
    EpochMetric,
    Evaluation,
    Experiment,
    Product,
    SegmentationRun,
    short_id,
)
from ..db.session import SessionLocal
from .queue import Cancelled, JobContext


def _register_product(db, aoi_id: str, product_id: str, out: Path, meta: dict, provider: str) -> Product:
    acquired = sorted(meta["acquired"])
    p = Product(
        id=product_id,
        aoi_id=aoi_id,
        kind=meta["kind"],
        scene_ids=meta["scene_ids"],
        acquired=datetime.fromisoformat(acquired[0]),
        acquired_list=acquired,
        provider=provider,
        collection=meta["collection"],
        platform=meta.get("platform"),
        scene_cloud_cover=meta.get("scene_cloud_cover"),
        valid_fraction=meta["valid_fraction"],
        quality_summary=meta["quality_summary"],
        path=str(out),
        meta={k: v for k, v in meta.items() if k not in ("source_assets",)},
    )
    db.add(p)
    db.commit()
    return p


def task_ingest(params: dict, ctx: JobContext) -> dict:
    """params: aoi_id, scene_ids, mode ('single' = same-day mosaic | 'composite')"""
    s = get_settings()
    with SessionLocal() as db:
        aoi = db.get(AOI, params["aoi_id"])
        grid = Grid.from_dict(aoi.grid)
    provider = get_provider(params.get("provider", "earth-search"))
    scenes = []
    for i, sid in enumerate(params["scene_ids"]):
        scenes.append(provider.get(sid))
        ctx.progress(0.05 * (i + 1) / len(params["scene_ids"]), f"resolved {sid}")
    groups = group_by_acquisition(scenes)
    if params.get("mode", "single") == "single" and len(groups) > 1:
        raise ValueError("'single' mode needs scenes from one acquisition day; use 'composite' for several dates")
    product_id = short_id("obs_")
    out = s.path("products", params["aoi_id"], product_id)
    if len(groups) == 1:
        ctx.log(f"Reading {len(groups[0])} tile(s) of {groups[0][0].datetime.date()} onto the AOI grid")
        meta = ingest_scene(groups[0], grid, out, progress=lambda f, m: ctx.progress(0.05 + 0.9 * f, m))
    else:
        dirs = []
        for gi, g in enumerate(groups):
            if ctx.cancelled():
                raise Cancelled()
            d = out / "parts" / g[0].id
            ctx.log(f"Composite part {gi + 1}/{len(groups)}: {g[0].datetime.date()}")
            ingest_scene(g, grid, d, progress=lambda f, m, gi=gi: ctx.progress(0.05 + 0.8 * (gi + f) / len(groups), m))
            dirs.append(d)
        meta = composite(dirs, out)
    with SessionLocal() as db:
        p = _register_product(db, params["aoi_id"], product_id, out, meta, provider.name)
    ctx.log(f"Observation {product_id}: {meta['valid_fraction']:.1%} of AOI pixels valid")
    return {"product_id": p.id, "valid_fraction": meta["valid_fraction"]}


class _TrainCallbacks(Callbacks):
    def __init__(self, ctx: JobContext, experiment_id: str):
        self.ctx = ctx
        self.experiment_id = experiment_id

    def on_log(self, msg):
        self.ctx.log(msg)

    def on_progress(self, fraction, msg):
        self.ctx.progress(fraction, msg)

    def on_epoch(self, rec):
        with SessionLocal() as db:
            db.add(
                EpochMetric(
                    experiment_id=self.experiment_id,
                    epoch=rec["epoch"],
                    train_loss=rec["train_loss"],
                    val_loss=rec["val_loss"],
                    val_miou=rec["val_miou"],
                    val_accuracy=rec["val_accuracy"],
                    val_per_class_iou=rec["val_per_class_iou"],
                    lr=rec["lr"],
                    seconds=rec["seconds"],
                )
            )
            db.commit()

    def should_stop(self):
        return self.ctx.cancelled()


def task_train(params: dict, ctx: JobContext) -> dict:
    s = get_settings()
    with SessionLocal() as db:
        exp = db.get(Experiment, params["experiment_id"])
        exp.status = "running"
        exp.started_at = datetime.now(UTC)
        db.query(EpochMetric).filter(EpochMetric.experiment_id == exp.id).delete()
        db.commit()
        cfg = TrainConfig.from_dict({**exp.config, "name": exp.name})
    out = s.path("models", params["experiment_id"])
    res = train(cfg, s.path("regions"), out, _TrainCallbacks(ctx, params["experiment_id"]))
    with SessionLocal() as db:
        exp = db.get(Experiment, params["experiment_id"])
        exp.status = res["status"]
        exp.finished_at = datetime.now(UTC)
        exp.result = {k: v for k, v in res.items() if k != "history"}
        exp.best_val_miou = res.get("best_val_miou")
        exp.best_epoch = res.get("best_epoch")
        exp.n_params = res.get("n_params")
        exp.device = res.get("device")
        exp.checkpoint = res.get("checkpoint")
        exp.checkpoint_sha256 = res.get("checkpoint_sha256")
        db.commit()
    if res["status"] == "cancelled":
        raise Cancelled()
    return {k: v for k, v in res.items() if k != "history"}


def task_evaluate(params: dict, ctx: JobContext) -> dict:
    from forestwatch.ml.evaluate import evaluate_checkpoint

    s = get_settings()
    with SessionLocal() as db:
        ev = db.get(Evaluation, params["evaluation_id"])
        exp = db.get(Experiment, ev.experiment_id)
        ckpt, regions = Path(exp.checkpoint), ev.regions
        ev.status = "running"
        db.commit()
    out = s.path("evaluations", params["evaluation_id"])
    ctx.log(f"Evaluating on held-out regions: {', '.join(regions)}")
    res = evaluate_checkpoint(ckpt, s.path("regions"), regions, out, progress=ctx.progress)
    with SessionLocal() as db:
        ev = db.get(Evaluation, params["evaluation_id"])
        ev.result, ev.path, ev.status = res, str(out), "succeeded"
        db.commit()
    m = res["overall_reference_agreement"]
    return {"mean_iou": m["mean_iou"], "overall_accuracy": m["overall_accuracy"]}


def task_segment(params: dict, ctx: JobContext) -> dict:
    s = get_settings()
    with SessionLocal() as db:
        run = db.get(SegmentationRun, params["segmentation_id"])
        product_path = Path(run.product.path)
        ckpt = Path(db.get(Experiment, run.experiment_id).checkpoint)
        run.status = "running"
        db.commit()
    out = s.path("segmentations", params["segmentation_id"])
    meta = segment_product(product_path, ckpt, out, progress=ctx.progress)
    with SessionLocal() as db:
        run = db.get(SegmentationRun, params["segmentation_id"])
        run.status, run.path, run.summary = "succeeded", str(out), meta["summary"]
        db.commit()
    return meta["summary"]


def task_change(params: dict, ctx: JobContext) -> dict:
    s = get_settings()
    with SessionLocal() as db:
        run = db.get(ChangeRun, params["change_run_id"])
        paths = [Path(run.before.path), Path(run.after.path)] + [
            Path(db.get(Product, pid).path) for pid in (run.extra_ids or [])
        ]
        ckpt = Path(db.get(Experiment, run.experiment_id).checkpoint)
        cparams = ChangeParams.from_dict(run.params)
        run.status = "running"
        db.commit()
    out = s.path("changes", params["change_run_id"])
    code = params["change_run_id"].replace("chg_", "").upper()[:6]
    summary = detect_change(paths, ckpt, out, cparams, run_id=f"CHG-{code}", progress=ctx.progress, log=ctx.log)
    fc = json.loads((out / "regions.geojson").read_text())
    with SessionLocal() as db:
        run = db.get(ChangeRun, params["change_run_id"])
        for f in fc["features"]:
            p = f["properties"]
            db.add(
                ChangeRegion(
                    id=p["id"],
                    run_id=run.id,
                    change_type=p["change_type"],
                    evidence_level=p["evidence_level"],
                    area_ha=p["area_ha"],
                    area_uncertainty_ha=p["area_uncertainty_ha"],
                    centroid_lon=p["centroid_lon"],
                    centroid_lat=p["centroid_lat"],
                    properties=p,
                    geometry=f["geometry"],
                )
            )
        run.status, run.path, run.summary = "succeeded", str(out), summary
        run.finished_at = datetime.now(UTC)
        db.commit()
    ctx.log(f"{summary['n_loss_regions']} potential-loss regions, {summary['potential_loss_ha']:.1f} ha")
    return {k: summary[k] for k in ("n_loss_regions", "n_gain_regions", "potential_loss_ha", "potential_gain_ha")}


def task_build_regions(params: dict, ctx: JobContext) -> dict:
    from forestwatch.regions import build_region, load_region_config

    cfg = load_region_config()
    names = params.get("regions") or [r["name"] for r in cfg["regions"]]
    out = get_settings().path("regions")
    done, failed = [], {}
    for i, spec in enumerate([r for r in cfg["regions"] if r["name"] in names]):
        if ctx.cancelled():
            raise Cancelled()
        try:
            build_region(spec, cfg["size_deg"], cfg["label_year"], out, log=ctx.log)
            shutil.rmtree(out / spec["name"] / "work", ignore_errors=True)
            done.append(spec["name"])
        except Exception as e:
            failed[spec["name"]] = str(e)
            ctx.log(f"[{spec['name']}] failed: {e}")
        ctx.progress((i + 1) / len(names), f"{spec['name']} done")
    return {"built": done, "failed": failed}


TASKS = {
    "ingest": task_ingest,
    "train": task_train,
    "evaluate": task_evaluate,
    "segment": task_segment,
    "change": task_change,
    "build_regions": task_build_regions,
}

_STATUS_TARGETS = {
    "train": (Experiment, "experiment_id"),
    "evaluate": (Evaluation, "evaluation_id"),
    "segment": (SegmentationRun, "segmentation_id"),
    "change": (ChangeRun, "change_run_id"),
}


def on_task_failed(type_: str, params: dict, status: str, error: str | None = None) -> None:
    if type_ not in _STATUS_TARGETS:
        return
    model, key = _STATUS_TARGETS[type_]
    with SessionLocal() as db:
        obj = db.get(model, params.get(key))
        if obj is not None:
            obj.status = status
            db.commit()
