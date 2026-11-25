# Reproducibility

Everything needed to reproduce the delivered model and analyses is in the repository: configuration (`configs/`), code (`backend/forestwatch`) and documented commands. Data is re-downloaded from the public sources.

## 1. Environment

Windows: `powershell -ExecutionPolicy Bypass -File .\setup.ps1`. On Linux or macOS:

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt
cd ../frontend && npm ci
```

Tested versions are pinned in `backend/requirements.txt` and `frontend/package-lock.json` (PyTorch 2.15, rasterio 1.5.2 with GDAL 3.12, Python 3.12, Node 22).

## 2. Training data

```bash
cd backend
python -m forestwatch.cli build-regions          # all regions in configs/regions.yaml
python -m forestwatch.cli build-regions --only para_altamira
```

For each region this:

* searches 2021 dry-season scenes;
* tries the five clearest acquisition days, keeping the first with ≥ 90% AOI-valid pixels (or a 3-date median composite if that is better);
* fetches WorldCover 2021 and Hansen v1.13 for the region;
* writes `data/regions/<name>/` containing `stack.tif`, `quality.tif`, `labels.tif`, `worldcover.tif`, `hansen_*.tif` and `region.json` (scene IDs, label report).

The scene selection is deterministic given the catalogue state; the chosen scene IDs are recorded, so a later rebuild can be compared.

## 3. Training

Through the Model Laboratory (recommended; it records every epoch in SQLite) or from the command line:

```bash
python -m forestwatch.cli train --config ../configs/training/standard.yaml
python -m forestwatch.cli train --config ../configs/training/quick.yaml
```

Training is seeded (`seed: 42`): Python, NumPy, PyTorch and per-sample crop RNGs are derived from it. CPU runs are close to deterministic; small numerical differences across hardware and thread counts are expected. CLI-trained models placed in `data/models/<name>/` are imported into the database automatically when the API starts.

## 4. Evaluation

Evaluation page → *Evaluate on test regions*, or:

```bash
python -m forestwatch.cli evaluate ../data/models/<experiment>/best.pt
```

Results are stored in `data/evaluations/<id>/evaluation.json`, alongside the prediction rasters per test region.

## 5. Change detection

1. Image Explorer: search the AOI and ingest an earlier and a later same-season acquisition (or run `python -m forestwatch.cli sample-data`, which ingests the clearest July 2024 and July 2025 scenes for the default AOI).
2. Change Detection Centre: choose both observations and run. The run records scene IDs, the checkpoint SHA-256, all thresholds and reference-data versions in its summary and in every export's `provenance.json`.

## 6. Tests

```bash
cd backend && python -m pytest                 # unit + integration + API (offline, real fixture crops)
SYLVA_RUN_NETWORK=1 python -m pytest -m network # optional live-provider tests
cd ../frontend && npm test && npx playwright test
```

The integration tests use two 160 × 160 crops of real ingested observations (`backend/tests/fixtures`).
