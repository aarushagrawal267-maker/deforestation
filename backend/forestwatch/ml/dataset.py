"""Training data: per-region analysis-ready stacks + fused labels, tiled for the U-Net."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from ..geo.raster_io import read_stack
from ..labels.classes import IGNORE, NUM_CLASSES
from ..preprocessing.bands import BAND_NAMES
from ..preprocessing.ingest import load_product


@dataclass
class RegionData:
    name: str
    refl: np.ndarray  # (C,H,W) float32, NaN = invalid
    labels: np.ndarray  # (H,W) uint8 with IGNORE
    meta: dict


def load_region(region_dir: Path, bands: list[str] = BAND_NAMES) -> RegionData:
    refl, _q, _g, meta = load_product(region_dir)
    idx = [meta["bands"].index(b) for b in bands]
    labels, _, _ = read_stack(region_dir / "labels.tif")
    rmeta = json.loads((region_dir / "region.json").read_text()) if (region_dir / "region.json").exists() else {}
    return RegionData(region_dir.name, refl[idx], labels[0], {**meta, **rmeta})


def compute_norm_stats(regions: list[RegionData], max_samples: int = 2_000_000, seed: int = 0) -> dict:
    """Per-band mean/std from valid pixels of training regions only (no val/test leakage)."""
    rng = np.random.default_rng(seed)
    samples = []
    per_region = max_samples // max(1, len(regions))
    for r in regions:
        flat = r.refl.reshape(r.refl.shape[0], -1)
        valid = np.isfinite(flat).all(axis=0)
        ids = np.flatnonzero(valid)
        if len(ids) == 0:
            continue
        ids = rng.choice(ids, size=min(per_region, len(ids)), replace=False)
        samples.append(flat[:, ids])
    s = np.concatenate(samples, axis=1)
    return {"mean": s.mean(axis=1).tolist(), "std": (s.std(axis=1) + 1e-6).tolist()}


def normalize(refl: np.ndarray, stats: dict) -> np.ndarray:
    mean = np.asarray(stats["mean"], np.float32)[:, None, None]
    std = np.asarray(stats["std"], np.float32)[:, None, None]
    x = (refl - mean) / std
    return np.nan_to_num(x, nan=0.0).astype(np.float32)


def class_weights(regions: list[RegionData], max_weight: float = 10.0, power: float = 0.5) -> np.ndarray:
    """Inverse-frequency class weights, ``freq ** -power`` normalised to mean 1 (0.5 = inverse sqrt)."""
    counts = np.zeros(NUM_CLASSES, np.float64)
    for r in regions:
        counts += np.bincount(r.labels[r.labels != IGNORE].ravel(), minlength=NUM_CLASSES)[:NUM_CLASSES]
    freq = counts / max(1, counts.sum())
    w = np.where(counts > 0, np.maximum(freq, 1e-8) ** -power, 0.0)
    w = w / w[counts > 0].mean()
    return np.clip(w, 0, max_weight).astype(np.float32)


def augment(x: np.ndarray, y: np.ndarray, rng: np.random.Generator, gain_jitter: float = 0.05, noise: float = 0.03):
    """Geometric (flips, 90 degree rotations) + mild per-band gain/offset jitter and noise.

    No hue/colour transforms: spectral relationships between bands carry the signal.
    """
    k = int(rng.integers(4))
    x, y = np.rot90(x, k, axes=(1, 2)), np.rot90(y, k)
    if rng.random() < 0.5:
        x, y = x[:, :, ::-1], y[:, ::-1]
    if gain_jitter > 0:
        g = rng.normal(1.0, gain_jitter, size=(x.shape[0], 1, 1)).astype(np.float32)
        o = rng.normal(0.0, gain_jitter, size=(x.shape[0], 1, 1)).astype(np.float32)
        x = x * g + o
    if noise > 0:
        x = x + rng.normal(0, noise, size=x.shape).astype(np.float32)
    return np.ascontiguousarray(x, dtype=np.float32), np.ascontiguousarray(y)


class RandomCropDataset(Dataset):
    """Random crops from training regions, skipping crops with too few labelled pixels."""

    def __init__(
        self,
        regions: list[RegionData],
        stats: dict,
        crop: int = 256,
        samples_per_epoch: int = 400,
        min_labelled: float = 0.3,
        augment_data: bool = True,
        seed: int = 0,
        rare_crop_fraction: float = 0.0,
        rare_class_max_freq: float = 0.05,
    ):
        self.x = [normalize(r.refl, stats) for r in regions]
        self.y = [r.labels for r in regions]
        self.crop = crop
        self.n = samples_per_epoch
        self.min_labelled = min_labelled
        self.aug = augment_data
        self.seed = seed
        self.epoch = 0
        sizes = np.array([y.size for y in self.y], np.float64)
        self.p = sizes / sizes.sum()
        # Rare-class sampling: a fraction of crops is centred on a pixel of a rare class
        # (real labelled examples), instead of only up-weighting those few pixels in the loss.
        self.rare_crop_fraction = rare_crop_fraction
        counts = sum(np.bincount(y[y != IGNORE].ravel(), minlength=NUM_CLASSES)[:NUM_CLASSES] for y in self.y)
        freq = counts / max(1, counts.sum())
        self.rare_classes = [c for c in range(NUM_CLASSES) if 0 < freq[c] < rare_class_max_freq]
        self.rare_pix = {}
        for c in self.rare_classes:
            locs = [(ri, np.flatnonzero(y.ravel() == c)) for ri, y in enumerate(self.y)]
            self.rare_pix[c] = [(ri, ix) for ri, ix in locs if ix.size]

    def set_epoch(self, e: int):
        self.epoch = e

    def __len__(self):
        return self.n

    def __getitem__(self, i):
        rng = np.random.default_rng((self.seed, self.epoch, i))
        if self.rare_classes and rng.random() < self.rare_crop_fraction:
            c = self.rare_classes[int(rng.integers(len(self.rare_classes)))]
            ri, ix = self.rare_pix[c][int(rng.integers(len(self.rare_pix[c])))]
            H, W = self.y[ri].shape
            cs = min(self.crop, H, W)
            cy, cx = divmod(int(ix[int(rng.integers(ix.size))]), W)
            yy = int(np.clip(cy - cs // 2 + rng.integers(-cs // 4, cs // 4 + 1), 0, H - cs))
            xx = int(np.clip(cx - cs // 2 + rng.integers(-cs // 4, cs // 4 + 1), 0, W - cs))
            x, y = self.x[ri][:, yy : yy + cs, xx : xx + cs], self.y[ri][yy : yy + cs, xx : xx + cs]
            if self.aug:
                x, y = augment(x, y, rng)
            return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(np.ascontiguousarray(y).astype(np.int64))
        for _ in range(20):
            r = int(rng.choice(len(self.x), p=self.p))
            H, W = self.y[r].shape
            c = min(self.crop, H, W)
            yy, xx = int(rng.integers(0, H - c + 1)), int(rng.integers(0, W - c + 1))
            y = self.y[r][yy : yy + c, xx : xx + c]
            if (y != IGNORE).mean() >= self.min_labelled:
                break
        x = self.x[r][:, yy : yy + c, xx : xx + c]
        if self.aug:
            x, y = augment(x, y, rng)
        return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(np.ascontiguousarray(y).astype(np.int64))


class GridTileDataset(Dataset):
    """Deterministic non-overlapping tiles covering evaluation regions."""

    def __init__(self, regions: list[RegionData], stats: dict, tile: int = 256, min_labelled: float = 0.05):
        self.items = []
        for r in regions:
            x = normalize(r.refl, stats)
            H, W = r.labels.shape
            for yy in range(0, max(1, H - tile + 1), tile):
                for xx in range(0, max(1, W - tile + 1), tile):
                    y = r.labels[yy : yy + tile, xx : xx + tile]
                    if (y != IGNORE).mean() >= min_labelled:
                        self.items.append((r.name, x[:, yy : yy + tile, xx : xx + tile], y))

    def __len__(self):
        return len(self.items)

    def __getitem__(self, i):
        _, x, y = self.items[i]
        return torch.from_numpy(np.ascontiguousarray(x)), torch.from_numpy(y.astype(np.int64))
