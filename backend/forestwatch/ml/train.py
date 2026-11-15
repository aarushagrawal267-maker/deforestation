"""U-Net training loop with region-held-out validation, checkpoints and calibration.

Every number reported (losses, metrics) is computed from the actual run.
"""

from __future__ import annotations

import json
import math
import random
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from ..labels.classes import CLASS_NAMES, IGNORE, NUM_CLASSES
from ..preprocessing.bands import BAND_NAMES
from .calibrate import fit_temperature
from .dataset import GridTileDataset, RandomCropDataset, class_weights, compute_norm_stats, load_region
from .device import get_device
from .infer import file_sha256
from .losses import SegLoss
from .metrics import confusion, metrics_from_confusion
from .unet import UNet, count_parameters


@dataclass
class TrainConfig:
    name: str = "unet-experiment"
    train_regions: list[str] = field(default_factory=list)
    val_regions: list[str] = field(default_factory=list)
    test_regions: list[str] = field(default_factory=list)
    bands: list[str] = field(default_factory=lambda: list(BAND_NAMES))
    base: int = 32
    depth: int = 4
    dropout: float = 0.2
    up_mode: str = "bilinear"
    epochs: int = 20
    batch_size: int = 8
    samples_per_epoch: int = 400
    crop: int = 256
    lr: float = 1e-3
    weight_decay: float = 1e-4
    warmup_epochs: int = 1
    loss: str = "ce_dice"
    dice_weight: float = 0.5
    class_weight_power: float = 0.5
    rare_crop_fraction: float = 0.0
    augment: bool = True
    early_stopping_patience: int = 8
    seed: int = 42
    num_workers: int = 0
    device: str = "auto"

    @classmethod
    def from_dict(cls, d: dict) -> TrainConfig:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class Callbacks:
    def on_log(self, msg: str) -> None: ...
    def on_epoch(self, record: dict) -> None: ...
    def on_progress(self, fraction: float, msg: str) -> None: ...
    def should_stop(self) -> bool:
        return False


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def lr_lambda(epoch_float: float, warmup: int, total: int) -> float:
    if epoch_float < warmup:
        return max(0.05, epoch_float / max(1e-8, warmup))
    progress = (epoch_float - warmup) / max(1e-8, total - warmup)
    return 0.02 + 0.98 * 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))


@torch.no_grad()
def evaluate_tiles(model, loader, device) -> tuple[float, dict]:
    model.eval()
    cm = np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64)
    losses = []
    loss_fn = SegLoss("ce")
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        logits = model(x)
        if (y != IGNORE).any():
            losses.append(float(loss_fn(logits, y)))
        cm += confusion(logits.argmax(1).cpu().numpy(), y.cpu().numpy(), NUM_CLASSES)
    return (float(np.mean(losses)) if losses else float("nan")), metrics_from_confusion(cm, CLASS_NAMES)


def train(cfg: TrainConfig, regions_dir: Path, out_dir: Path, cb: Callbacks | None = None) -> dict:
    cb = cb or Callbacks()
    set_seed(cfg.seed)
    device = get_device(cfg.device)
    out_dir.mkdir(parents=True, exist_ok=True)
    overlap = set(cfg.train_regions) & (set(cfg.val_regions) | set(cfg.test_regions))
    if overlap:
        raise ValueError(f"Regions in both train and val/test (spatial leakage): {sorted(overlap)}")
    if not cfg.train_regions or not cfg.val_regions:
        raise ValueError("At least one training and one validation region are required")

    cb.on_log(f"Loading regions on {device}...")
    train_r = [load_region(regions_dir / n, cfg.bands) for n in cfg.train_regions]
    val_r = [load_region(regions_dir / n, cfg.bands) for n in cfg.val_regions]
    stats = compute_norm_stats(train_r, seed=cfg.seed)
    weights = class_weights(train_r, power=cfg.class_weight_power)
    cb.on_log(f"Class weights: {np.round(weights, 3).tolist()}")

    train_ds = RandomCropDataset(
        train_r, stats, cfg.crop, cfg.samples_per_epoch, augment_data=cfg.augment, seed=cfg.seed,
        rare_crop_fraction=cfg.rare_crop_fraction,
    )
    val_ds = GridTileDataset(val_r, stats, tile=cfg.crop)
    if len(val_ds) == 0:
        raise ValueError("Validation regions produced no tiles with labelled pixels")
    train_dl = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=False, num_workers=cfg.num_workers, drop_last=True)
    val_dl = DataLoader(val_ds, batch_size=cfg.batch_size, num_workers=0)

    model = UNet(len(cfg.bands), NUM_CLASSES, cfg.base, cfg.depth, cfg.dropout, cfg.up_mode).to(device)
    n_params = count_parameters(model)
    cb.on_log(f"U-Net: {n_params:,} trainable parameters, randomly initialised")
    loss_fn = SegLoss(cfg.loss, torch.tensor(weights, device=device), cfg.dice_weight).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps_per_epoch = len(train_dl)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda step: lr_lambda(step / max(1, steps_per_epoch), cfg.warmup_epochs, cfg.epochs)
    )
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    manifest = {
        r.name: {"scene_ids": r.meta.get("scene_ids"), "label_source": r.meta.get("label_source")}
        for r in train_r + val_r
    }
    history: list[dict] = []
    best_miou, best_epoch, stale = -1.0, -1, 0
    t_start = time.time()
    stopped = None

    def make_ckpt(epoch: int, temperature: float = 1.0, extra: dict | None = None) -> dict:
        return {
            "state_dict": model.state_dict(),
            "model_config": model.config,
            "bands": cfg.bands,
            "norm_stats": stats,
            "class_names": CLASS_NAMES,
            "temperature": temperature,
            "train_config": asdict(cfg),
            "epoch": epoch,
            "history": history,
            "data_manifest": manifest,
            "n_params": n_params,
            "created_at": datetime.now(UTC).isoformat(),
            "framework": f"torch {torch.__version__}",
            **(extra or {}),
        }

    for epoch in range(1, cfg.epochs + 1):
        model.train()
        train_ds.set_epoch(epoch)
        t0 = time.time()
        losses = []
        for step, (x, y) in enumerate(train_dl):
            if cb.should_stop():
                stopped = "cancelled"
                break
            x, y = x.to(device), y.to(device)
            opt.zero_grad(set_to_none=True)
            with torch.autocast(device.type, enabled=use_amp):
                loss = loss_fn(model(x), y)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            losses.append(loss.item())
            cb.on_progress(
                ((epoch - 1) + (step + 1) / steps_per_epoch) / cfg.epochs,
                f"epoch {epoch}/{cfg.epochs} step {step + 1}/{steps_per_epoch} loss {np.mean(losses):.4f}",
            )
        if stopped:
            break
        val_loss, vm = evaluate_tiles(model, val_dl, device)
        rec = {
            "epoch": epoch,
            "train_loss": float(np.mean(losses)),
            "val_loss": val_loss,
            "val_miou": vm["mean_iou"],
            "val_accuracy": vm["overall_accuracy"],
            "val_per_class_iou": [c["iou"] for c in vm["per_class"]],
            "lr": opt.param_groups[0]["lr"],
            "seconds": time.time() - t0,
        }
        history.append(rec)
        cb.on_epoch(rec)
        cb.on_log(
            f"epoch {epoch}: train_loss={rec['train_loss']:.4f} val_loss={val_loss:.4f} "
            f"val_mIoU={vm['mean_iou']:.4f} ({rec['seconds']:.0f}s)"
        )
        torch.save(make_ckpt(epoch), out_dir / "last.pt")
        if vm["mean_iou"] is not None and vm["mean_iou"] > best_miou:
            best_miou, best_epoch, stale = vm["mean_iou"], epoch, 0
            torch.save(make_ckpt(epoch), out_dir / "best.pt")
        else:
            stale += 1
            if stale >= cfg.early_stopping_patience:
                stopped = "early_stopping"
                cb.on_log(f"Early stopping at epoch {epoch} (best epoch {best_epoch})")
                break

    result = {
        "status": "cancelled" if stopped == "cancelled" else "completed",
        "stop_reason": stopped,
        "best_epoch": best_epoch,
        "best_val_miou": best_miou if best_epoch > 0 else None,
        "epochs_run": len(history),
        "seconds": time.time() - t_start,
        "n_params": n_params,
        "device": str(device),
        "history": history,
    }
    if best_epoch > 0:
        ckpt = torch.load(out_dir / "best.pt", map_location=device, weights_only=False)
        model.load_state_dict(ckpt["state_dict"])
        cb.on_log("Fitting temperature scaling on validation regions...")
        cal = fit_temperature(model, val_dl, device)
        ckpt["temperature"] = cal["temperature"]
        ckpt["calibration"] = cal
        torch.save(ckpt, out_dir / "best.pt")
        result["calibration"] = cal
        result["checkpoint"] = str(out_dir / "best.pt")
        result["checkpoint_sha256"] = file_sha256(out_dir / "best.pt")
        cb.on_log(f"Temperature={cal['temperature']:.3f}, ECE {cal['ece_before']:.4f} -> {cal['ece_after']:.4f}")
    (out_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result
