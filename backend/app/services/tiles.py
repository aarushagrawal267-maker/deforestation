"""Render local COG products as Web Mercator map tiles and image chips (rio-tiler)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from rio_tiler.colormap import cmap
from rio_tiler.errors import TileOutsideBounds
from rio_tiler.io import Reader

from forestwatch.change.compare import CATEGORIES
from forestwatch.labels.classes import CLASSES, WORLDCOVER_MAP
from forestwatch.preprocessing.bands import BAND_NAMES


def _transparent_png(size: int = 256) -> bytes:
    """A valid fully transparent RGBA PNG (returned for tiles outside a raster)."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * size for _ in range(size))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


TRANSPARENT_PNG = _transparent_png()


def _hex(c: str, a: int = 255) -> tuple[int, int, int, int]:
    c = c.lstrip("#")
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), a)


CLASS_CMAP = {c["id"]: _hex(c["color"]) for c in CLASSES}
CHANGE_CMAP = {c["id"]: _hex(c["color"], 0 if c["key"] in ("stable_nonforest",) else 220) for c in CATEGORIES}
CHANGE_CMAP[0] = (107, 114, 128, 150)
CHANGE_CMAP[1] = (47, 143, 91, 90)
WORLDCOVER_CMAP = {
    10: _hex("#006400"), 20: _hex("#ffbb22"), 30: _hex("#ffff4c"), 40: _hex("#f096ff"), 50: _hex("#fa0000"),
    60: _hex("#b4b4b4"), 70: _hex("#f0f0f0"), 80: _hex("#0064c8"), 90: _hex("#0096a0"), 95: _hex("#00cf75"),
    100: _hex("#fae6a0"), 0: (0, 0, 0, 0),
}


def _loss_year_cmap() -> dict:
    out = {0: (0, 0, 0, 0)}
    for y in range(1, 26):
        t = y / 25
        out[y] = (int(255 * (0.6 + 0.4 * t)), int(200 * (1 - t)), int(60 * (1 - t)), 230)
    return out


LOSSYEAR_CMAP = _loss_year_cmap()


@lru_cache(maxsize=1)
def prob_cmap() -> dict:
    """Perceptually ordered ramp for P(tree): pale sand (0) -> deep green (1), on values 0..250."""
    stops = [(0, (236, 226, 198)), (0.4, (190, 196, 120)), (0.6, (110, 160, 80)), (1.0, (12, 70, 40))]
    out = {}
    for v in range(256):
        if v > 250:
            out[v] = (0, 0, 0, 0)
            continue
        t = v / 250
        for (t0, c0), (t1, c1) in zip(stops[:-1], stops[1:]):
            if t <= t1:
                f = (t - t0) / (t1 - t0)
                rgb = tuple(int(c0[i] + f * (c1[i] - c0[i])) for i in range(3))
                out[v] = (*rgb, 235)
                break
    return out


def _b(name: str) -> int:
    return BAND_NAMES.index(name) + 1


RGB_RENDERS = {
    "truecolor": ([_b("B4"), _b("B3"), _b("B2")], [(0, 1400), (0, 1200), (0, 1000)]),
    "falsecolor": ([_b("B8"), _b("B4"), _b("B3")], [(0, 4500), (0, 1400), (0, 1200)]),
    "swir": ([_b("B12"), _b("B8A"), _b("B4")], [(0, 3000), (0, 4500), (0, 1400)]),
}
BAND_RANGES = {n: (0, 1500) if n in ("B2", "B3", "B4", "B5") else (0, 4500) for n in BAND_NAMES}


def render_image(path: Path, render: str, band: str | None, tile=None, bbox=None, size: int = 256) -> bytes:
    """Render a tile (tile=(x,y,z)) or a chip (bbox lon/lat) of the raster at ``path``."""
    kwargs: dict = {}
    colormap = None
    rescale = None
    if render in RGB_RENDERS:
        kwargs["indexes"], rescale = RGB_RENDERS[render]
    elif render == "band":
        b = band or "B8"
        kwargs["indexes"] = [_b(b)]
        rescale = [BAND_RANGES[b]]
        colormap = cmap.get("greys_r")
    elif render in ("ndvi", "nbr", "ndmi"):
        a, c = {"ndvi": ("B8", "B4"), "nbr": ("B8", "B12"), "ndmi": ("B8", "B11")}[render]
        kwargs["expression"] = f"(b{_b(a)}-b{_b(c)})/(b{_b(a)}+b{_b(c)})"
        rescale = [(-0.2, 0.9)]
        colormap = cmap.get("rdylgn")
    elif render == "prob":
        kwargs["indexes"] = [1]
        colormap = prob_cmap()
    elif render == "entropy":
        kwargs["indexes"] = [1]
        rescale = [(0, 250)]
        colormap = cmap.get("magma")
    elif render == "class":
        kwargs["indexes"] = [1]
        colormap = CLASS_CMAP
    elif render == "labels":
        kwargs["indexes"] = [1]
        colormap = CLASS_CMAP
    elif render == "change":
        kwargs["indexes"] = [1]
        colormap = CHANGE_CMAP
    elif render == "delta":
        kwargs["indexes"] = [1]
        rescale = [(-100, 100)]
        colormap = cmap.get("rdbu")
    elif render == "worldcover":
        kwargs["indexes"] = [1]
        colormap = WORLDCOVER_CMAP
    elif render == "lossyear":
        kwargs["indexes"] = [1]
        colormap = LOSSYEAR_CMAP
    else:
        raise ValueError(f"Unknown render '{render}'")

    with Reader(str(path)) as src:
        try:
            if tile is not None:
                x, y, z = tile
                img = src.tile(x, y, z, tilesize=size, **kwargs)
            else:
                img = src.part(bbox, max_size=size, **kwargs)
        except TileOutsideBounds:
            return TRANSPARENT_PNG
    if render == "ndvi" or render in ("nbr", "ndmi"):
        img.array = np.ma.masked_invalid(img.array)
    if rescale:
        img.rescale(in_range=rescale)
    if render == "lossyear":
        pass
    return img.render(img_format="PNG", colormap=colormap)


def worldcover_is_tree(code: int) -> bool:
    return WORLDCOVER_MAP.get(code) == 0
