"""Convert ORM rows to API dictionaries."""

from __future__ import annotations

from ..db.models import AOI, ChangeRegion, ChangeRun, Evaluation, Experiment, Export, Job, Product, SegmentationRun


def iso(d):
    return d.isoformat() if d else None


def aoi(a: AOI) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "bbox": a.bbox,
        "geometry": a.geometry,
        "grid": a.grid,
        "area_km2": a.area_km2,
        "created_at": iso(a.created_at),
    }


def product(p: Product) -> dict:
    return {
        "id": p.id,
        "aoi_id": p.aoi_id,
        "kind": p.kind,
        "scene_ids": p.scene_ids,
        "acquired": iso(p.acquired),
        "acquired_list": p.acquired_list,
        "provider": p.provider,
        "collection": p.collection,
        "platform": p.platform,
        "scene_cloud_cover": p.scene_cloud_cover,
        "valid_fraction": p.valid_fraction,
        "quality_summary": p.quality_summary,
        "processing": p.meta.get("processing", []),
        "processing_baselines": p.meta.get("processing_baselines", []),
        "attribution": p.meta.get("attribution"),
        "mgrs_tile": p.meta.get("mgrs_tile"),
        "created_at": iso(p.created_at),
    }


def experiment(e: Experiment, with_epochs: bool = False) -> dict:
    d = {
        "id": e.id,
        "name": e.name,
        "config": e.config,
        "status": e.status,
        "job_id": e.job_id,
        "checkpoint": e.checkpoint,
        "checkpoint_sha256": e.checkpoint_sha256,
        "best_val_miou": e.best_val_miou,
        "best_epoch": e.best_epoch,
        "n_params": e.n_params,
        "device": e.device,
        "result": e.result,
        "notes": e.notes,
        "created_at": iso(e.created_at),
        "started_at": iso(e.started_at),
        "finished_at": iso(e.finished_at),
        "calibrated": bool(e.result and e.result.get("calibration")),
    }
    if with_epochs:
        d["epochs"] = [
            {
                "epoch": m.epoch,
                "train_loss": m.train_loss,
                "val_loss": m.val_loss,
                "val_miou": m.val_miou,
                "val_accuracy": m.val_accuracy,
                "val_per_class_iou": m.val_per_class_iou,
                "lr": m.lr,
                "seconds": m.seconds,
            }
            for m in e.epochs
        ]
    return d


def evaluation(ev: Evaluation, full: bool = True) -> dict:
    d = {
        "id": ev.id,
        "experiment_id": ev.experiment_id,
        "regions": ev.regions,
        "status": ev.status,
        "job_id": ev.job_id,
        "created_at": iso(ev.created_at),
    }
    if ev.result:
        if full:
            d["result"] = ev.result
        else:
            m = ev.result["overall_reference_agreement"]
            d["summary"] = {
                "mean_iou": m["mean_iou"],
                "overall_accuracy": m["overall_accuracy"],
                "hansen_f1": ev.result["overall_hansen_tree_agreement"]["f1"],
            }
    return d


def segmentation(s: SegmentationRun) -> dict:
    return {
        "id": s.id,
        "product_id": s.product_id,
        "experiment_id": s.experiment_id,
        "status": s.status,
        "job_id": s.job_id,
        "summary": s.summary,
        "acquired": iso(s.product.acquired) if s.product else None,
        "aoi_id": s.product.aoi_id if s.product else None,
        "created_at": iso(s.created_at),
    }


def change_run(r: ChangeRun, full: bool = False) -> dict:
    d = {
        "id": r.id,
        "aoi_id": r.aoi_id,
        "aoi_name": r.aoi.name if r.aoi else None,
        "before_id": r.before_id,
        "after_id": r.after_id,
        "before_acquired": iso(r.before.acquired) if r.before else None,
        "after_acquired": iso(r.after.acquired) if r.after else None,
        "extra_ids": r.extra_ids,
        "experiment_id": r.experiment_id,
        "params": r.params,
        "status": r.status,
        "job_id": r.job_id,
        "created_at": iso(r.created_at),
        "finished_at": iso(r.finished_at),
    }
    s = r.summary or {}
    d["headline"] = {
        k: s.get(k)
        for k in (
            "potential_loss_ha",
            "potential_loss_uncertainty_ha",
            "potential_gain_ha",
            "n_loss_regions",
            "n_gain_regions",
            "valid_fraction_both_dates",
            "tree_cover_before_ha",
            "tree_cover_after_ha",
            "evidence_counts",
        )
    }
    if full:
        d["summary"] = s
    return d


def region(g: ChangeRegion, with_geometry: bool = True) -> dict:
    d = {
        "id": g.id,
        "run_id": g.run_id,
        "change_type": g.change_type,
        "evidence_level": g.evidence_level,
        "area_ha": g.area_ha,
        "area_uncertainty_ha": g.area_uncertainty_ha,
        "centroid_lon": g.centroid_lon,
        "centroid_lat": g.centroid_lat,
        "properties": g.properties,
        "review_status": g.review_status,
        "analyst_notes": g.analyst_notes,
    }
    if with_geometry:
        d["geometry"] = g.geometry
    return d


def export(x: Export) -> dict:
    return {
        "id": x.id,
        "source_type": x.source_type,
        "source_id": x.source_id,
        "format": x.format,
        "size_bytes": x.size_bytes,
        "created_at": iso(x.created_at),
        "download_url": f"/api/exports/{x.id}/download",
    }


def job(j: Job, with_log: bool = False) -> dict:
    d = {
        "id": j.id,
        "type": j.type,
        "params": j.params,
        "status": j.status,
        "progress": j.progress,
        "message": j.message,
        "result": j.result,
        "error": j.error,
        "created_at": iso(j.created_at),
        "started_at": iso(j.started_at),
        "finished_at": iso(j.finished_at),
    }
    if with_log:
        d["log"] = j.log
    return d
