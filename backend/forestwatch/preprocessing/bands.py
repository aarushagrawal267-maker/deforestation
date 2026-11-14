"""Sentinel-2 MSI band definitions used by Sylva."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    name: str  # ESA band id
    asset: str  # Earth Search asset key
    common: str
    wavelength_nm: int
    native_res_m: int


BANDS: list[Band] = [
    Band("B2", "blue", "Blue", 490, 10),
    Band("B3", "green", "Green", 560, 10),
    Band("B4", "red", "Red", 665, 10),
    Band("B5", "rededge1", "Red edge 1", 705, 20),
    Band("B6", "rededge2", "Red edge 2", 740, 20),
    Band("B7", "rededge3", "Red edge 3", 783, 20),
    Band("B8", "nir", "NIR (broad)", 842, 10),
    Band("B8A", "nir08", "NIR (narrow)", 865, 20),
    Band("B11", "swir16", "SWIR 1", 1610, 20),
    Band("B12", "swir22", "SWIR 2", 2190, 20),
]

BAND_NAMES = [b.name for b in BANDS]
BY_NAME = {b.name: b for b in BANDS}


def band_index(name: str, names: list[str] | None = None) -> int:
    return (names or BAND_NAMES).index(name)


def describe_bands() -> list[dict]:
    return [
        {
            "name": b.name,
            "common": b.common,
            "wavelength_nm": b.wavelength_nm,
            "native_res_m": b.native_res_m,
            "note": "native 10 m"
            if b.native_res_m == 10
            else "native 20 m, bilinearly resampled to the 10 m grid (no new 10 m information)",
        }
        for b in BANDS
    ]
