from __future__ import annotations

import torch

from ..settings import get_settings


def get_device(pref: str | None = None) -> torch.device:
    pref = (pref or get_settings().device or "auto").lower()
    if pref == "cuda" or (pref == "auto" and torch.cuda.is_available()):
        if torch.cuda.is_available():
            return torch.device("cuda")
    return torch.device("cpu")


def device_info() -> dict:
    d = get_device()
    return {
        "device": str(d),
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "torch_version": torch.__version__,
        "threads": torch.get_num_threads(),
    }
