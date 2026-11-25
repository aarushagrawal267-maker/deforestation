"""Tiled U-Net inference with overlap blending; preserves the input grid exactly."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import torch

from .dataset import normalize
from .device import get_device
from .unet import UNet

REQUIRED_CKPT_KEYS = ("state_dict", "model_config", "bands", "norm_stats")


class CheckpointError(ValueError):
    """The model checkpoint is missing, unreadable or not a Sylva U-Net checkpoint."""


def load_checkpoint(path: Path, device: torch.device | None = None) -> tuple[UNet, dict]:
    path = Path(path)
    if not path.is_file():
        raise CheckpointError(
            f"Model checkpoint not found: {path}. Restart the app to reinstall the bundled models, "
            "or train/activate another model in the Model Laboratory."
        )
    device = device or get_device()
    try:
        ckpt = torch.load(path, map_location=device, weights_only=False)
    except Exception as e:
        raise CheckpointError(f"Model checkpoint {path} could not be read (corrupt or incomplete file): {e}") from e
    missing = [k for k in REQUIRED_CKPT_KEYS if not isinstance(ckpt, dict) or k not in ckpt]
    if missing:
        raise CheckpointError(f"{path} is not a Sylva U-Net checkpoint (missing {', '.join(missing)})")
    model = UNet(**ckpt["model_config"]).to(device)
    try:
        model.load_state_dict(ckpt["state_dict"])
    except RuntimeError as e:
        raise CheckpointError(f"Weights in {path} do not match its model_config: {e}") from e
    model.eval()
    return model, ckpt


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _window(tile: int) -> np.ndarray:
    w = np.hanning(tile + 2)[1:-1]
    w = np.outer(w, w).astype(np.float32)
    return np.maximum(w, 1e-3)


@torch.no_grad()
def predict_probs(
    model: UNet,
    refl: np.ndarray,
    stats: dict,
    temperature: float = 1.0,
    tile: int = 256,
    overlap: int = 64,
    batch_size: int = 8,
    progress=None,
) -> np.ndarray:
    """Return class probabilities (K,H,W) float32. Pixels invalid in the input get NaN."""
    device = next(model.parameters()).device
    x = normalize(refl, stats)
    C, H, W = x.shape
    K = model.config["num_classes"]
    pad_h, pad_w = max(0, tile - H), max(0, tile - W)
    if pad_h or pad_w:
        x = np.pad(x, ((0, 0), (0, pad_h), (0, pad_w)), mode="reflect")
    Hp, Wp = x.shape[1:]
    stride = tile - overlap
    ys = list(range(0, Hp - tile + 1, stride))
    xs = list(range(0, Wp - tile + 1, stride))
    if ys[-1] != Hp - tile:
        ys.append(Hp - tile)
    if xs[-1] != Wp - tile:
        xs.append(Wp - tile)
    coords = [(y, x_) for y in ys for x_ in xs]
    acc = np.zeros((K, Hp, Wp), np.float32)
    wsum = np.zeros((Hp, Wp), np.float32)
    win = _window(tile)
    for i in range(0, len(coords), batch_size):
        batch = coords[i : i + batch_size]
        xb = torch.from_numpy(np.stack([x[:, y : y + tile, x_ : x_ + tile] for y, x_ in batch])).to(device)
        probs = (model(xb) / temperature).softmax(1).float().cpu().numpy()
        for (y, x_), p in zip(batch, probs):
            acc[:, y : y + tile, x_ : x_ + tile] += p * win
            wsum[y : y + tile, x_ : x_ + tile] += win
        if progress:
            progress(min(1.0, (i + len(batch)) / len(coords)), f"tiles {i + len(batch)}/{len(coords)}")
    probs = (acc / wsum)[:, :H, :W]
    invalid = ~np.isfinite(refl).all(axis=0)
    probs[:, invalid] = np.nan
    return probs


def entropy(probs: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        e = -(probs * np.log(np.clip(probs, 1e-8, 1))).sum(axis=0) / np.log(probs.shape[0])
    return e.astype(np.float32)
