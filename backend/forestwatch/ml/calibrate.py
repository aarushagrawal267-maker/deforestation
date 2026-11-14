"""Temperature scaling (Guo et al., 2017) fitted on validation regions."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F

from ..labels.classes import IGNORE
from .metrics import expected_calibration_error


@torch.no_grad()
def _collect(model, loader, device, max_pixels: int = 400_000, seed: int = 0):
    model.eval()
    rng = np.random.default_rng(seed)
    logits_all, y_all = [], []
    per_batch = max(1000, max_pixels // max(1, len(loader)))
    for x, y in loader:
        lg = model(x.to(device)).permute(0, 2, 3, 1).reshape(-1, model.config["num_classes"]).cpu()
        yy = y.reshape(-1)
        idx = torch.nonzero(yy != IGNORE).squeeze(1).numpy()
        if len(idx) == 0:
            continue
        idx = rng.choice(idx, size=min(per_batch, len(idx)), replace=False)
        logits_all.append(lg[idx])
        y_all.append(yy[idx])
    return torch.cat(logits_all), torch.cat(y_all)


def fit_temperature(model, loader, device) -> dict:
    logits, y = _collect(model, loader, device)
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(logits / log_t.exp(), y)
        loss.backward()
        return loss

    opt.step(closure)
    t = float(log_t.exp().clamp(0.05, 20))

    def ece_for(temp):
        p = (logits / temp).softmax(1)
        conf, pred = p.max(1)
        return expected_calibration_error(conf.numpy(), (pred == y).numpy())

    ece_b, _ = ece_for(1.0)
    ece_a, bins = ece_for(t)
    return {
        "temperature": t,
        "ece_before": ece_b,
        "ece_after": ece_a,
        "reliability": bins,
        "pixels": int(len(y)),
        "fitted_on": "validation regions",
    }
