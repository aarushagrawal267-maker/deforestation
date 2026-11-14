"""Register models trained with the CLI (``python -m forestwatch.cli train``) in the database.

Only real training outputs are imported: the experiment record and epoch metrics are read
from the run's ``result.json`` and the checkpoint written by the training loop.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import torch
from sqlalchemy import select

from forestwatch.ml.infer import file_sha256
from forestwatch.settings import get_settings

from ..db.init import get_setting, set_setting
from ..db.models import EpochMetric, Experiment
from ..db.session import SessionLocal


def import_model_dir(d: Path) -> str | None:
    res_path, ckpt_path = d / "result.json", d / "best.pt"
    if not (res_path.exists() and ckpt_path.exists()):
        return None
    with SessionLocal() as db:
        if db.scalars(select(Experiment).where(Experiment.checkpoint == str(ckpt_path))).first():
            return None
        res = json.loads(res_path.read_text())
        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        cfg = ckpt["train_config"]
        exp = Experiment(
            name=cfg.get("name", d.name),
            config=cfg,
            status=res["status"],
            checkpoint=str(ckpt_path),
            checkpoint_sha256=file_sha256(ckpt_path),
            best_val_miou=res.get("best_val_miou"),
            best_epoch=res.get("best_epoch"),
            n_params=res.get("n_params"),
            device=res.get("device"),
            result={k: v for k, v in res.items() if k != "history"},
            notes="Trained with the command-line interface; imported from " + str(d),
            started_at=datetime.fromtimestamp(res_path.stat().st_mtime - res.get("seconds", 0)),
            finished_at=datetime.fromtimestamp(res_path.stat().st_mtime),
        )
        db.add(exp)
        db.flush()
        for rec in res.get("history", []):
            db.add(EpochMetric(experiment_id=exp.id, **{k: rec[k] for k in (
                "epoch", "train_loss", "val_loss", "val_miou", "val_accuracy", "val_per_class_iou", "lr", "seconds")}))
        db.commit()
        if not get_setting(db, "active_experiment_id"):
            set_setting(db, "active_experiment_id", exp.id)
        return exp.id


def import_cli_models() -> list[str]:
    root = get_settings().data_dir / "models"
    if not root.exists():
        return []
    with SessionLocal() as db:
        known_dirs = {Path(e.checkpoint).parent.name for e in db.scalars(select(Experiment)).all() if e.checkpoint}
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith("exp_") and d.name not in known_dirs:
            eid = import_model_dir(d)
            if eid:
                out.append(eid)
    return out
