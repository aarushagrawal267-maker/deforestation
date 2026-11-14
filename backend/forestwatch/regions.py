"""Build training regions: real Sentinel-2 imagery + fused reference labels on one grid."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from .geo.grid import Grid
from .geo.raster_io import write_cog
from .labels.dynamic_world import load_dynamic_world
from .labels.fusion import build_labels
from .labels.reference import HANSEN_VERSION, WORLDCOVER, hansen_on_grid, worldcover_on_grid
from .preprocessing.ingest import composite, group_by_acquisition, ingest_scene, load_product
from .providers.earth_search import EarthSearchProvider
from .settings import REPO_ROOT


def load_region_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or REPO_ROOT / "configs" / "regions.yaml").read_text())


def region_bbox(center: list[float], size_deg: float) -> tuple[float, float, float, float]:
    lon, lat = center
    h = size_deg / 2
    return (lon - h, lat - h, lon + h, lat + h)


def select_and_ingest(
    bbox, start: str, end: str, work_dir: Path, grid: Grid, min_valid: float = 0.9, max_candidates: int = 5, log=print
) -> dict:
    """Try the least-cloudy candidates; keep the best AOI-valid scene, or composite if all are poor."""
    provider = EarthSearchProvider()
    scenes = provider.search(bbox, start, end, max_cloud=40, limit=60)
    if not scenes:
        raise RuntimeError(f"No Sentinel-2 scenes found for {bbox} {start}..{end}")
    groups = group_by_acquisition(scenes)
    groups.sort(key=lambda g: min((s.cloud_cover if s.cloud_cover is not None else 100) for s in g))
    tried = []
    for g in groups[:max_candidates]:
        d = work_dir / "candidates" / g[0].id
        meta = ingest_scene(g, grid, d)
        tried.append((meta["valid_fraction"], d, g[0].id))
        log(f"  candidate {'+'.join(s.id for s in g)}: AOI valid {meta['valid_fraction']:.1%}")
        if meta["valid_fraction"] >= min_valid:
            break
    tried.sort(reverse=True)
    best_valid, best_dir, best_id = tried[0]
    if best_valid >= min_valid or len(tried) < 2:
        return {"product_dir": best_dir, "mode": "single", "valid": best_valid}
    comp_dir = work_dir / "composite"
    meta = composite([d for _, d, _ in tried[:3]], comp_dir)
    log(f"  composite of {min(3, len(tried))} scenes: AOI valid {meta['valid_fraction']:.1%}")
    if meta["valid_fraction"] > best_valid:
        return {"product_dir": comp_dir, "mode": "composite", "valid": meta["valid_fraction"]}
    return {"product_dir": best_dir, "mode": "single", "valid": best_valid}


def build_region(spec: dict, size_deg: float, label_year: int, regions_dir: Path, log=print) -> dict:
    name = spec["name"]
    out = regions_dir / name
    out.mkdir(parents=True, exist_ok=True)
    bbox = region_bbox(spec["center"], spec.get("size_deg", size_deg))
    grid = Grid.from_bbox_lonlat(bbox)
    log(f"[{name}] grid {grid.width}x{grid.height} {grid.crs.to_string()}")
    sel = select_and_ingest(bbox, spec["window"][0], spec["window"][1], out / "work", grid, log=log)
    refl, q, grid, meta = load_product(sel["product_dir"])
    # Copy chosen product into region root
    for fn in ("stack.tif", "quality.tif", "meta.json"):
        (out / fn).write_bytes((sel["product_dir"] / fn).read_bytes())

    wc = worldcover_on_grid(grid, label_year)
    loss = hansen_on_grid(grid, "lossyear")
    tc = hansen_on_grid(grid, "treecover2000")
    dw = load_dynamic_world(out / "dynamic_world.tif", grid)
    labels, report = build_labels(wc, q, loss, label_year, dw_probs=dw)
    write_cog(out / "worldcover.tif", wc, grid, nodata=0, resampling_overview="nearest")
    write_cog(out / "hansen_lossyear.tif", loss, grid, resampling_overview="nearest")
    write_cog(out / "hansen_treecover2000.tif", tc, grid, nodata=255)
    write_cog(out / "labels.tif", labels, grid, nodata=255, resampling_overview="nearest")
    label_source = (
        f"ESA WorldCover {label_year} {WORLDCOVER[label_year]['version']}"
        + (" + Dynamic World agreement" if dw is not None else "")
        + f"; Hansen {HANSEN_VERSION} loss {label_year - 1}-{label_year + 1} ignored"
    )
    region_meta = {
        "name": name,
        "role": spec["role"],
        "description": spec.get("description", ""),
        "bbox": bbox,
        "center": spec["center"],
        "grid": grid.to_dict(),
        "label_year": label_year,
        "label_source": label_source,
        "label_type": "model-generated reference labels (not independent ground truth)",
        "label_report": report,
        "selection": {"mode": sel["mode"], "valid_fraction": sel["valid"]},
        "scene_ids": meta["scene_ids"],
        "acquired": meta["acquired"],
    }
    (out / "region.json").write_text(json.dumps(region_meta, indent=2))
    log(f"[{name}] labelled {report['labelled_fraction']:.1%}, classes {report['class_counts']}")
    return region_meta


def list_regions(regions_dir: Path) -> list[dict]:
    out = []
    for d in sorted(regions_dir.glob("*/region.json")):
        out.append(json.loads(d.read_text()))
    return out


def region_split(regions_dir: Path) -> dict[str, list[str]]:
    split: dict[str, list[str]] = {"train": [], "val": [], "test": []}
    for r in list_regions(regions_dir):
        split.setdefault(r["role"], []).append(r["name"])
    return split


def label_stats(regions_dir: Path) -> dict:
    tot = np.zeros(5, np.int64)
    for r in list_regions(regions_dir):
        for k, v in r["label_report"]["class_counts"].items():
            tot[int(k)] += v
    return {"class_counts": tot.tolist()}
