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
| 23 | Windows setup script | ✅ | `setup.ps1` run successfully on GitHub Actions `windows-latest` |
| 24 | Windows startup script | ✅ | `start.ps1`, then health checks of API, docs, frontend and proxy on `windows-latest` |
| 25 | Windows shutdown script | ✅ | `stop.ps1`; verified port 8000 released on `windows-latest` |
| 26 | README | ✅ | `README.md` (screenshots, how it works, tech stack, limitations, license) |
| 27 | Dataset documentation | ✅ | `docs/datasets.md` |
| 28 | Scientific methodology | ✅ | `docs/methodology.md`, `docs/change-detection.md`, `docs/unet.md` |
| 29 | Research references | ✅ | `docs/references.md` |
| 30 | Limitations & reproducibility | ✅ | `docs/limitations.md`, `docs/reproducibility.md`, `docs/model-card.md` |
| 31 | LICENSE | ✅ | `LICENSE` (MIT for code; data keeps its own licences) |
| 32 | Linux/macOS start & stop scripts | ✅ | `scripts/dev.sh`, `scripts/stop.sh` (stops the whole process tree) |
| 33 | Dependency security | ✅ | `npm audit`: 0 vulnerabilities after upgrading maplibre-gl 4→6, react-router-dom 6→7, vite 6.0→6.4, vitest 2→4, @playwright/test 1.49→1.63 (2026-11-24); `ruff check` clean |

## Acceptance criteria

| Criterion | Status | Notes |
|---|---|---|
| Application starts on Windows | ✅ | GitHub Actions `windows-scripts` job (`.github/workflows/ci.yml`): setup.ps1 → backend tests → start.ps1 → health checks → stop.ps1 on `windows-latest`, passed. Not yet tried on the owner's own laptop |
| Frontend and backend communicate | ✅ | Vite proxy; Playwright `/api/health` through the frontend |
| Real Sentinel-2 imagery obtained / loaded locally | ✅ | windowed COG reads; cached products reused offline |
| Preprocessing works | ✅ | unit and integration tests on real fixture crops |
| Cloud and shadow masking works | ✅ | quality codes tested; quality summaries per observation |
| Geospatial alignment preserved | ✅ | grid-identity assertions for every output |
| U-Net can be trained locally | ✅ | v1: 20 epochs on CPU, 74 min, test mIoU 0.733; v2 (default): test mIoU 0.740, tree IoU 0.940, bare F1 0.324. Re-check on freshly rebuilt test regions (2026-11-24): v1 0.715, v2 0.714 mIoU (Puerto Maldonado rebuilt from a different scene mosaic; see model card) |
| Real segmentation predictions | ✅ | segmentation of the 2025 observation |
| Forest probability maps displayed | ✅ | map and segmentation pages |
| Two observation dates compared | ✅ | change runs |
| Potential forest-loss regions identified | ✅ | 2024→2025: 192 regions, 489.3 ± 89.4 ha (88 Hansen-corroborated); 2023→2024: 157 regions, 279.3 ± 63.9 ha |
| Map displays results | ✅ | screenshot-verified |
| Detected regions can be investigated | ✅ | investigation page; API test for region detail and review |
| Geospatial results exported | ✅ | GeoJSON / GPKG / CSV / GeoTIFF / bundle with provenance; API test downloads zips |
| Evaluation metrics from actual results | ✅ | `data/evaluations/<id>/evaluation.json` |
| Experiment history saved | ✅ | history page and tables |
| Important features pass automated tests | ✅ | backend pytest 60 passed, 3 skipped (re-run 2026-11-25, Linux CPU, after the checkpoint-robustness and split-hygiene fixes) (+3 live-provider tests passed with `SYLVA_RUN_NETWORK=1`); frontend vitest 8 passed; Playwright e2e 14 passed against both the dev server and the production build (`vite preview`) and the single-origin hosted mode (`SYLVA_FRONTEND_DIST`, where Swagger now lives at `/api/swagger` so it no longer hides the docs list) |
| Documentation explains reproduction | ✅ | `docs/reproducibility.md` |

## Known gaps / not done

* **Windows** is verified on a GitHub-hosted Windows Server runner, not on a physical laptop; first run on the target laptop is still worth doing.
* **Dynamic World** labels are supported in code (`labels/dynamic_world.py`, `scripts/export_dynamic_world.py`) but not used: no Earth Engine account was configured.
* **CDSE authenticated download** is implemented as a token flow but not verified (no credentials). Earth Search (no credentials) is the working provider.
* **GPU path** (CUDA wheels, mixed precision) is implemented but untested: no GPU here.
* **Potential gain** uses a stricter rule than loss (see docs/change-detection.md), since one-year gain was mostly pasture or regrowth edges.
* **Sample-based area estimation** (Olofsson) is not implemented; areas are mapped areas with boundary uncertainty. Analyst reviews are stored as a first step.
* **Bare/sparse class** is still weak (F1 0.32 with v2, up from 0.27; 0.3% of training labels).
