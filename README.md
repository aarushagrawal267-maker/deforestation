# Sylva: forest change intelligence

Sylva is a locally run research platform. It segments tree cover in **real Copernicus Sentinel-2 Level-2A imagery** with a **U-Net trained from scratch in this repository**, compares observation dates to flag **potential forest-cover loss**, and lets you investigate every detected region on an interactive map.

> Independent educational/research implementation, not affiliated with ESA, NASA or Copernicus. Detected changes are *potential* forest-cover changes, not verified deforestation events; imagery alone cannot establish their cause. Sylva analyses **available acquisitions**; it is not a real-time feed.

| | |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |

## Features

* **Satellite Image Explorer:** search available Sentinel-2 L2A acquisitions for an AOI with a cloud-cover timeline. Ingest single dates (same-day multi-tile mosaics) or median composites as analysis-ready observations; view true colour, false colour, SWIR, NDVI or any single band; swipe-compare dates.
* **Geospatial pipeline:** windowed COG reads (only the AOI is downloaded), radiometric scaling with processing-baseline harmonisation, SCL + cloud-probability masking with a 40 m buffer, a shared UTM 10 m grid, COG outputs with preserved georeferencing.
* **Own U-Net model:** encoder-decoder with skip connections (PyTorch, about 7.2 M parameters), trained from random initialisation on 10 Sentinel-2 bands with weak labels from ESA WorldCover. Region-level train/validation/test split, CE + Dice loss, temperature-scaled calibration.
* **Model Laboratory:** configure bands, architecture, regions and hyper-parameters; train in a background worker with live loss and IoU curves from real epochs; compare experiments; choose the active model.
* **Model Evaluation:** held-out test regions with mIoU, per-class IoU, Dice/F1, precision, recall, confusion matrix, agreement with Hansen GFC, a reliability diagram, and prediction-vs-reference maps.
* **Segmentation Centre:** calibrated P(tree), class and uncertainty maps, a pixel inspector, swipe comparison and GeoTIFF export.
* **Change Detection Centre:** compare two dates (plus an optional persistence date) with editable decision thresholds. Results are categorised (stable forest, potential loss, potential gain, non-forest, uncertain, invalid), vectorised into regions (0.5 ha minimum mapping unit), co-registration checked, and corroborated against Hansen GFC.
* **Forest Loss Investigation:** for every region: coordinates, area ± uncertainty, dates, P(tree) before and after, NDVI/NBR/NDMI, data quality, calibrated confidence, reference comparison, before/after image chips, an evidence ladder and an analyst assessment.
* **Interactive Forest Map:** MapLibre layers for imagery, probability, classes, change categories, ΔP, regions, WorldCover and Hansen loss year, with legends, opacity, swipe mode and a pixel/region inspector.
* **Dataset Explorer, Monitoring History and Research & Docs** pages. Exports (GeoJSON, GeoPackage, CSV, GeoTIFF, bundle) carry a `provenance.json`.

## Windows quick start

Prerequisites: Windows 10/11, **Python 3.11–3.13**, **Node.js 20+**, about 5 GB free disk (more for training data). An NVIDIA GPU is optional.

```powershell
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
```

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -WithSampleData
```

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

```powershell
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

`setup.ps1` creates `backend\.venv`, installs PyTorch (a CUDA build is tried automatically if `nvidia-smi` finds a GPU; force with `-Cpu` or `-Cuda`), installs the backend and frontend dependencies, creates `.env`, initialises the SQLite database and runs a smoke check. `-WithSampleData` ingests two real observations (July 2024 and July 2025) of the default AOI, about 80 MB. `-WithTrainingData` builds the training regions, about 1 GB. **No training is ever started automatically.**

`start.ps1` launches the API, the job worker and the frontend in the background, records their PIDs in `.run\pids.json`, waits until they are healthy and opens the browser (`-NoBrowser` to skip, `-Preview` to serve the production build). Logs go to `logs\`. `stop.ps1` stops exactly those process trees and, as a fallback, only processes whose command line is Sylva's.

### First run walkthrough

1. **Datasets** → *Build missing* (or `setup.ps1 -WithTrainingData`) to download the training regions.
2. **Model Lab** → configure and *Start training*. The quick profile (width 16, 10 epochs) takes roughly 15–40 minutes on a laptop CPU; then click *Use for analysis*.
3. **Evaluation** → *Evaluate on test regions*.
4. **Image Explorer** → search the AOI, ingest an earlier and a later same-season acquisition (or use `-WithSampleData`).
5. **Change Detection** → choose both observations → *Run multi-date analysis*.
6. **Forest Map / Investigation** → inspect regions; export results.

## Linux/macOS (development)

```bash
cd backend && python3.12 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements-dev.txt
cd ../frontend && npm ci && cd .. && cp .env.example .env
./scripts/dev.sh
```

## Data access & credentials

| Source | Credentials |
|---|---|
| Sentinel-2 L2A via Earth Search (AWS Open Data) | **none** |
| ESA WorldCover (public S3) | none |
| Hansen GFC v1.13 (Google Cloud Storage) | none |
| Copernicus Data Space Ecosystem | free account; optional. Set `SYLVA_CDSE_USERNAME` / `SYLVA_CDSE_PASSWORD` in `.env` |
| Dynamic World | Google Earth Engine account; optional. See `scripts/export_dynamic_world.py` |

Credentials live only in `.env` (git-ignored), are read only by the backend and are never sent to the browser. Everything you ingest is cached under `data/`, so training, segmentation and change detection work offline afterwards.

## Command line

```bash
cd backend
python -m forestwatch.cli doctor                  # environment check
python -m forestwatch.cli build-regions           # training data
python -m forestwatch.cli train --config ../configs/training/quick.yaml
python -m forestwatch.cli evaluate ../data/models/<name>/best.pt
python -m forestwatch.cli sample-data             # two observations of the default AOI
```

## Tests

```bash
cd backend && python -m pytest                   # unit, integration (real fixture crops), API workflow
cd frontend && npm test                          # component tests
cd frontend && npx playwright test               # end-to-end (app must be running)
```

## Repository layout

```
backend/
  forestwatch/        core library: providers, geo, preprocessing, labels, ml (U-Net), change, pipeline, CLI
  app/                FastAPI app: routers, SQLAlchemy models, job queue + worker, tile service
  tests/              unit, integration, api (+ fixtures: real Sentinel-2 crops)
frontend/             React + TypeScript + Vite + Tailwind + MapLibre + Recharts (11 pages)
configs/              regions.yaml (training split), training/*.yaml
docs/                 methodology, datasets, U-Net, change detection, model card, limitations, reproducibility, references
scripts/              dev.sh, export_dynamic_world.py
setup.ps1 start.ps1 stop.ps1
CHECKLIST.md          development checklist and acceptance status
```

## Documentation

See `docs/` (also rendered in the app under *Research & Docs*): [overview](docs/overview.md), [methodology](docs/methodology.md), [Sentinel-2](docs/sentinel2.md), [U-Net](docs/unet.md), [change detection](docs/change-detection.md), [datasets](docs/datasets.md), [model card](docs/model-card.md), [limitations](docs/limitations.md), [reproducibility](docs/reproducibility.md), [references](docs/references.md).

## Attribution

Contains modified Copernicus Sentinel data (2021–2025). ESA WorldCover © ESA WorldCover project, CC BY 4.0. Hansen/UMD/Google/USGS/NASA Global Forest Change, CC BY 4.0. Basemap: OpenFreeMap, © OpenMapTiles, © OpenStreetMap contributors.
