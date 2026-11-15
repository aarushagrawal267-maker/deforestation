# Development checklist & acceptance status

Status key: ✅ done and verified · ⚠️ done with a stated limitation · ❌ not done.
"Verified" means exercised by an automated test or an actual run in the development environment (Linux container, CPU only).

## Deliverables

| # | Deliverable | Status | Evidence |
|---|---|---|---|
| 1 | Complete frontend (11 pages) | ✅ | `frontend/src/pages/*`; Playwright: every page renders with no console errors |
| 2 | Complete backend | ✅ | FastAPI routers in `backend/app/api/routers`; API tests |
| 3 | Sentinel-2 acquisition pipeline | ✅ | Earth Search Collection 1 + legacy gap filler; real ingests of 2023/2024/2025 observations and 10 training regions |
| 4 | Image preprocessing | ✅ | `forestwatch/preprocessing`; unit tests (scaling, baseline harmonisation, composite) |
| 5 | Cloud & shadow masking | ✅ | SCL + cloud probability + 40 m buffer; `test_quality_codes_and_buffer` |
| 6 | Geospatial alignment | ✅ | shared UTM grids; georeference-identity tests through segmentation and change outputs; phase-correlation co-registration test |
| 7 | Training dataset preparation | ✅ | `forestwatch/regions.py`; 10 real regions with label reports |
| 8 | U-Net model | ✅ | `forestwatch/ml/unet.py`, from scratch, skip connections tested; trained checkpoint shipped in `models/unet-base32-v1` and auto-activated on a fresh install (API test) |
| 9 | Training pipeline | ✅ | real 20-epoch CPU run through the worker; epochs stored in SQLite |
| 10 | Model evaluation | ✅ | held-out test regions; see `docs/model-card.md` |
| 11 | Forest probability maps | ✅ | segmentation runs → `probs.tif`; map layers |
| 12 | Multi-date change detection | ✅ | real runs 2024→2025 and 2023→2024 (+2025 persistence) for Novo Progresso |
| 13 | Potential forest-loss polygons | ✅ | vectorised regions with attributes; polygon area tests |
| 14 | Interactive geospatial map | ✅ | MapLibre map page; Playwright tile test |
| 15 | Satellite image explorer | ✅ | search, timeline, ingest, renders, swipe compare |
| 16 | Forest investigation interface | ✅ | list + detail with chips, indicators, evidence ladder, review |
| 17 | Dataset explorer | ✅ | datasets, bands, label scheme, regions, observations |
| 18 | Model laboratory | ✅ | configure / train / cancel / curves / compare / activate |
| 19 | Experiment tracking | ✅ | `experiments`, `epoch_metrics`, `evaluations` tables |
| 20 | SQLite database | ✅ | `data/sylva.sqlite` (WAL) |
| 21 | Documented API | ✅ | http://localhost:8000/docs |
| 22 | Automated tests | ✅ | backend pytest, frontend vitest, Playwright e2e |
| 23 | Windows setup script | ⚠️ | `setup.ps1` written; **not executed on Windows** during development (see below) |
| 24 | Windows startup script | ⚠️ | `start.ps1`; same caveat |
| 25 | Windows shutdown script | ⚠️ | `stop.ps1`; same caveat |
| 26 | README | ✅ | `README.md` |
| 27 | Dataset documentation | ✅ | `docs/datasets.md` |
| 28 | Scientific methodology | ✅ | `docs/methodology.md`, `docs/change-detection.md`, `docs/unet.md` |
| 29 | Research references | ✅ | `docs/references.md` |
| 30 | Limitations & reproducibility | ✅ | `docs/limitations.md`, `docs/reproducibility.md`, `docs/model-card.md` |

## Acceptance criteria

| Criterion | Status | Notes |
|---|---|---|
| Application starts on Windows | ⚠️ | Not run on Windows here. A manually triggered GitHub Actions job (`.github/workflows/ci.yml`, `windows-scripts`) runs setup → tests → start → health checks → stop on `windows-latest`; it has not been run yet |
| Frontend and backend communicate | ✅ | Vite proxy; Playwright `/api/health` through the frontend |
| Real Sentinel-2 imagery obtained / loaded locally | ✅ | windowed COG reads; cached products reused offline |
| Preprocessing works | ✅ | unit and integration tests on real fixture crops |
| Cloud and shadow masking works | ✅ | quality codes tested; quality summaries per observation |
| Geospatial alignment preserved | ✅ | grid-identity assertions for every output |
| U-Net can be trained locally | ✅ | 20 epochs on CPU, 74 min, 7.24 M parameters; best val mIoU 0.849; test mIoU 0.733, tree IoU 0.939 |
| Real segmentation predictions | ✅ | segmentation of the 2025 observation |
| Forest probability maps displayed | ✅ | map and segmentation pages |
| Two observation dates compared | ✅ | change runs |
| Potential forest-loss regions identified | ✅ | 2024→2025: 192 regions, 489.3 ± 89.4 ha (88 Hansen-corroborated); 2023→2024: 157 regions, 279.3 ± 63.9 ha |
| Map displays results | ✅ | screenshot-verified |
| Detected regions can be investigated | ✅ | investigation page; API test for region detail and review |
| Geospatial results exported | ✅ | GeoJSON / GPKG / CSV / GeoTIFF / bundle with provenance; API test downloads zips |
| Evaluation metrics from actual results | ✅ | `data/evaluations/<id>/evaluation.json` |
| Experiment history saved | ✅ | history page and tables |
| Important features pass automated tests | ✅ | backend pytest 50 passed (+3 live-provider tests passed with `SYLVA_RUN_NETWORK=1`); frontend vitest 8 passed; Playwright e2e 14 passed |
| Documentation explains reproduction | ✅ | `docs/reproducibility.md` |

## Known gaps / not done

* **Windows execution not verified** in this environment (Linux container; running a PowerShell binary was not permitted here). Run `setup.ps1` / `start.ps1` / `stop.ps1` on the target laptop, or trigger the Windows CI job.
* **Dynamic World** labels are supported in code (`labels/dynamic_world.py`, `scripts/export_dynamic_world.py`) but not used: no Earth Engine account was configured.
* **CDSE authenticated download** is implemented as a token flow but not verified (no credentials). Earth Search (no credentials) is the working provider.
* **GPU path** (CUDA wheels, mixed precision) is implemented but untested: no GPU here.
* **Sample-based area estimation** (Olofsson) is not implemented; areas are mapped areas with boundary uncertainty. Analyst reviews are stored as a first step.
* **Bare/sparse class** is weak (rare in the training labels).
