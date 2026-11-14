"""Command-line interface: ``python -m forestwatch.cli --help``."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from .settings import REPO_ROOT, get_settings

app = typer.Typer(help="Sylva forestwatch core CLI")


@app.command()
def build_regions(only: list[str] = typer.Option(None, help="Region names to build (default: all)")):
    """Download real Sentinel-2 + reference labels for the regions in configs/regions.yaml."""
    from .regions import build_region, load_region_config

    cfg = load_region_config()
    out = get_settings().path("regions")
    for spec in cfg["regions"]:
        if only and spec["name"] not in only:
            continue
        try:
            build_region(spec, cfg["size_deg"], cfg["label_year"], out)
        except Exception as e:  # keep going with other regions, report clearly
            typer.echo(f"[{spec['name']}] FAILED: {e}")


@app.command()
def train(config: Path = typer.Option(REPO_ROOT / "configs" / "training" / "standard.yaml"), out: Path | None = None):
    """Train the U-Net from scratch on the built regions."""
    from .ml.train import Callbacks, TrainConfig
    from .ml.train import train as run_train
    from .regions import region_split

    s = get_settings()
    d = yaml.safe_load(config.read_text())
    split = region_split(s.path("regions"))
    d.setdefault("train_regions", split["train"])
    d.setdefault("val_regions", split["val"])
    d.setdefault("test_regions", split["test"])
    cfg = TrainConfig.from_dict(d)

    class Print(Callbacks):
        def on_log(self, msg):
            typer.echo(msg)

    out = out or s.path("models", cfg.name)
    res = run_train(cfg, s.path("regions"), out, Print())
    typer.echo(json.dumps({k: v for k, v in res.items() if k != "history"}, indent=2))


@app.command()
def evaluate(checkpoint: Path, out: Path | None = None):
    """Evaluate a checkpoint on the held-out test regions."""
    from .ml.evaluate import evaluate_checkpoint
    from .regions import region_split

    s = get_settings()
    split = region_split(s.path("regions"))
    res = evaluate_checkpoint(checkpoint, s.path("regions"), split["test"], out or checkpoint.parent / "eval")
    typer.echo(json.dumps(res["overall_reference_agreement"], indent=2)[:2000])


@app.command()
def doctor():
    """Check that the geospatial and ML stack works (used by setup.ps1)."""
    import tempfile

    import numpy as np
    import rasterio
    import torch

    from .geo.grid import Grid
    from .geo.raster_io import read_stack, write_cog
    from .ml.device import device_info
    from .ml.unet import UNet

    info = device_info()
    typer.echo(f"python OK | torch {torch.__version__} | device {info['device']} | CUDA available: {info['cuda_available']}")
    typer.echo(f"rasterio {rasterio.__version__} | GDAL {rasterio.__gdal_version__}")
    g = Grid.from_bbox_lonlat((-55.40, -7.10, -55.39, -7.09))
    with tempfile.TemporaryDirectory() as d:
        p = write_cog(Path(d) / "t.tif", np.ones(g.shape, np.uint8), g)
        arr, g2, _ = read_stack(p)
        assert g2.to_dict() == g.to_dict() and arr.sum() == g.width * g.height
    typer.echo("COG write/read with georeferencing OK")
    y = UNet(10, 5, 8, 2)(torch.zeros(1, 10, 64, 64))
    assert y.shape == (1, 5, 64, 64)
    typer.echo("U-Net forward pass OK")
    typer.echo(f"data dir: {get_settings().data_dir}")


@app.command()
def sample_data(
    windows: list[str] = typer.Option(["2024-06-15:2024-09-15", "2025-06-15:2025-09-15"], help="start:end date windows"),
    max_cloud: float = 5.0,
):
    """Ingest the clearest acquisition in each window for the default AOI (AOI window only, ~40 MB each)."""
    from app.db.init import get_setting, init_db
    from app.db.models import AOI
    from app.db.session import SessionLocal
    from app.jobs.tasks import _register_product

    from .geo.grid import Grid
    from .preprocessing.ingest import group_by_acquisition, ingest_scene
    from .providers.earth_search import EarthSearchProvider

    init_db()
    with SessionLocal() as db:
        aoi = db.get(AOI, get_setting(db, "active_aoi_id"))
        grid = Grid.from_dict(aoi.grid)
        bbox, aoi_id = tuple(aoi.bbox), aoi.id
    prov = EarthSearchProvider()
    for w in windows:
        start, end = w.split(":")
        scenes = prov.search(bbox, start, end, max_cloud=max_cloud, limit=50)
        if not scenes:
            typer.echo(f"No scenes with <= {max_cloud}% cloud in {w}")
            continue
        groups = sorted(group_by_acquisition(scenes), key=lambda g: min(s.cloud_cover or 100 for s in g))
        import uuid

        pid = f"obs_{uuid.uuid4().hex[:10]}"
        out = get_settings().path("products", aoi_id, pid)
        meta = ingest_scene(groups[0], grid, out)
        with SessionLocal() as db:
            _register_product(db, aoi_id, pid, out, meta, prov.name)
        typer.echo(f"{groups[0][0].id}: {meta['valid_fraction']:.1%} valid -> {pid}")


if __name__ == "__main__":
    app()
