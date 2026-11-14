"""Segmentation losses that respect the IGNORE label."""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn

from ..labels.classes import IGNORE


def soft_dice_loss(logits: torch.Tensor, target: torch.Tensor, ignore_index: int = IGNORE, eps: float = 1.0):
    """Multi-class soft Dice loss averaged over classes present in the batch."""
    num_classes = logits.shape[1]
    valid = target != ignore_index
    probs = logits.softmax(dim=1) * valid.unsqueeze(1)
    t = torch.where(valid, target, torch.zeros_like(target))
    onehot = F.one_hot(t, num_classes).permute(0, 3, 1, 2).float() * valid.unsqueeze(1)
    dims = (0, 2, 3)
    inter = (probs * onehot).sum(dims)
    denom = probs.sum(dims) + onehot.sum(dims)
    dice = (2 * inter + eps) / (denom + eps)
    present = onehot.sum(dims) > 0
    if present.sum() == 0:
        return logits.sum() * 0
    return 1 - dice[present].mean()


class SegLoss(nn.Module):
    def __init__(self, kind: str = "ce_dice", class_weights: torch.Tensor | None = None, dice_weight: float = 0.5):
        super().__init__()
        self.kind = kind
        self.dice_weight = dice_weight
        self.register_buffer("w", class_weights if class_weights is not None else None)

    def forward(self, logits, target):
        if (target != IGNORE).sum() == 0:
            return logits.sum() * 0
        ce = F.cross_entropy(logits, target, weight=self.w, ignore_index=IGNORE)
        if self.kind == "ce":
            return ce
        dice = soft_dice_loss(logits, target)
        if self.kind == "dice":
            return dice
        return ce + self.dice_weight * dice
