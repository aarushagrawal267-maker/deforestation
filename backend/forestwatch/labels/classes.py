"""Sylva segmentation classes and mappings from reference products."""

from __future__ import annotations

import numpy as np

IGNORE = 255

CLASSES = [
    {"id": 0, "key": "tree", "name": "Tree cover", "color": "#2f8f5b"},
    {"id": 1, "key": "other_veg", "name": "Other vegetation", "color": "#b5c96a"},
    {"id": 2, "key": "bare", "name": "Bare / sparse", "color": "#c9a27a"},
    {"id": 3, "key": "water", "name": "Water", "color": "#3a7bd5"},
    {"id": 4, "key": "built", "name": "Built-up", "color": "#d1495b"},
]
NUM_CLASSES = len(CLASSES)
CLASS_NAMES = [c["name"] for c in CLASSES]
TREE = 0

# ESA WorldCover class codes -> Sylva classes
WORLDCOVER_MAP = {
    10: 0,  # Tree cover
    95: 0,  # Mangroves (trees)
    20: 1,  # Shrubland
    30: 1,  # Grassland
    40: 1,  # Cropland
    90: 1,  # Herbaceous wetland
    60: 2,  # Bare / sparse vegetation
    80: 3,  # Permanent water bodies
    50: 4,  # Built-up
    70: IGNORE,  # Snow and ice (out of initial scope)
    100: IGNORE,  # Moss and lichen (out of initial scope)
    0: IGNORE,  # No data
}
WORLDCOVER_NAMES = {
    10: "Tree cover",
    20: "Shrubland",
    30: "Grassland",
    40: "Cropland",
    50: "Built-up",
    60: "Bare / sparse vegetation",
    70: "Snow and ice",
    80: "Permanent water bodies",
    90: "Herbaceous wetland",
    95: "Mangroves",
    100: "Moss and lichen",
}

# Dynamic World band order -> Sylva classes
DYNAMIC_WORLD_BANDS = [
    "water",
    "trees",
    "grass",
    "flooded_vegetation",
    "crops",
    "shrub_and_scrub",
    "built",
    "bare",
    "snow_and_ice",
]
DYNAMIC_WORLD_MAP = {0: 3, 1: 0, 2: 1, 3: 1, 4: 1, 5: 1, 6: 4, 7: 2, 8: IGNORE}


def map_codes(arr: np.ndarray, mapping: dict[int, int], default: int = IGNORE) -> np.ndarray:
    lut = np.full(256, default, dtype=np.uint8)
    for k, v in mapping.items():
        lut[k] = v
    return lut[arr.astype(np.uint8)]
