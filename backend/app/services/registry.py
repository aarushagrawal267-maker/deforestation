"""Register models trained with the CLI (``python -m forestwatch.cli train``) in the database.

Only real training outputs are imported: the experiment record and epoch metrics are read
from the run's ``result.json`` and the checkpoint written by the training loop.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime
from pathlib import Path

import torch
from sqlalchemy import select

from forestwatch.ml.infer import file_sha256, load_checkpoint
from forestwatch.settings import REPO_ROOT, get_settings

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
        sha = file_sha256(ckpt_path)
        if db.scalars(select(Experiment).where(Experiment.checkpoint_sha256 == sha)).first():
            return None  # same weights already registered (e.g. the bundled copy of a locally trained model)
        res = json.loads(res_path.read_text())
        _, ckpt = load_checkpoint(ckpt_path, torch.device("cpu"))  # validates the file before registering it
        cfg = ckpt.get("train_config", {})
        exp = Experiment(
            name=cfg.get("name", d.name),
            config=cfg,
            status=res["status"],
            checkpoint=str(ckpt_path),
            checkpoint_sha256=sha,
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
        return exp.id


BUNDLED_MODELS = REPO_ROOT / "models"
log = logging.getLogger("sylva.registry")


def install_bundled_models(root: Path) -> None:
    """Copy models shipped in the repository (``models/<name>``) into the data directory once,
    so a fresh install can analyse imagery without retraining. They are this project's own
    trained U-Nets (see docs/model-card.md), not external models."""
    if not BUNDLED_MODELS.exists():
        return
    for src in BUNDLED_MODELS.iterdir():
        dst = root / src.name
        if src.is_dir() and (src / "best.pt").exists() and not dst.exists():
            dst.mkdir(parents=True)
            for f in ("best.pt", "result.json"):
                shutil.copy2(src / f, dst / f)


def import_cli_models() -> list[str]:
    root = get_settings().data_dir / "models"
    install_bundled_models(root)
    if not root.exists():
        return []
    _repair_moved_checkpoints(root)
    with SessionLocal() as db:
        known_dirs = {Path(e.checkpoint).parent.name for e in db.scalars(select(Experiment)).all() if e.checkpoint}
    out = []
    for d in sorted(root.iterdir()):
        if d.is_dir() and not d.name.startswith("exp_") and d.name not in known_dirs and (d / "result.json").exists():
            try:
                eid = import_model_dir(d)
            except Exception as e:  # one broken model folder must not stop the app from starting
                log.warning("Skipping model folder %s: it could not be imported (%s)", d, e)
                continue
            if eid:
                out.append(eid)
    _ensure_active_model(root, out)
    return out


def _repair_moved_checkpoints(root: Path) -> None:
    """Checkpoint paths are stored as absolute paths. When the project folder is moved or renamed,
    point them at the same model folder under the current data directory (same weights only)."""
    with SessionLocal() as db:
        changed = False
        for exp in db.scalars(select(Experiment).where(Experiment.checkpoint.is_not(None))).all():
            old = Path(exp.checkpoint)
            if old.is_file():
                continue
            new = root / old.parent.name / old.name
            if new.is_file() and (not exp.checkpoint_sha256 or file_sha256(new) == exp.checkpoint_sha256):
                log.info("Model %s moved: %s -> %s", exp.name, old, new)
                exp.checkpoint = str(new)
                changed = True
        if changed:
            db.commit()


def _ensure_active_model(root: Path, imported: list[str]) -> None:
    """If no model is active yet, activate the one named in models/DEFAULT (else the first imported)."""
    with SessionLocal() as db:
        if get_setting(db, "active_experiment_id"):
            return
        default = BUNDLED_MODELS / "DEFAULT"
        if default.exists():
            ck = str(root / default.read_text().strip() / "best.pt")
            exp = db.scalars(select(Experiment).where(Experiment.checkpoint == ck)).first()
            if exp:
                set_setting(db, "active_experiment_id", exp.id)
                return
        if imported:
            set_setting(db, "active_experiment_id", imported[0])
