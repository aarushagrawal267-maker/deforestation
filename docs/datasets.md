# Datasets & provenance

Only the parts of each dataset that intersect an AOI or training region are read; nothing is downloaded in full.

## A. Copernicus Sentinel-2 MSI Level-2A

| Field | Value |
|---|---|
| Official source | https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-missions/sentinel-2 |
| Provider | European Space Agency / European Commission (Copernicus) |
| Access used | Element 84 Earth Search STAC (`https://earth-search.aws.element84.com/v1`), collection `sentinel-2-c1-l2a` (Collection 1); `sentinel-2-l2a` as a gap filler. COG assets on AWS Open Data, no credentials |
| Alternative | Copernicus Data Space Ecosystem: open STAC catalogue; downloads need a free account (`SYLVA_CDSE_USERNAME` / `SYLVA_CDSE_PASSWORD`) |
| Version | Collection 1, processing baseline 05.xx (recorded per observation) |
| Resolution | 10 / 20 m (60 m bands unused) |
| CRS | UTM of each MGRS tile; reprojected to the AOI's UTM grid |
| Temporal coverage | 2015-06-27 onward; check availability per AOI and period |
| Licence | Free, full and open Copernicus licence. Attribution: "Contains modified Copernicus Sentinel data [year]" |
| Processing history | stored per observation (`meta.json` and the Dataset Explorer): asset URLs, scene IDs, baselines, scaling, masking, resampling |
| Intended use | input imagery for training, segmentation and change detection |
| Limitations | cloud/shadow masking errors; 20 m bands; persistent tropical cloud; acquisition gaps |

## B. Dynamic World V1 (optional)

| Field | Value |
|---|---|
| Source | https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1 |
| Provider | Google, World Resources Institute (Brown et al., 2022) |
| Resolution / classes | 10 m; 9 classes with per-class probabilities, one image per Sentinel-2 L1C scene |
| Access | Google Earth Engine only (free noncommercial account + Cloud project). `scripts/export_dynamic_world.py` exports the probability bands on a region grid |
| Licence | CC BY 4.0 |
| Role | same-date agreement filter for weak labels (pixels kept only where Dynamic World is confident and agrees with WorldCover) |
| Status | supported in code, **not used in the delivered model** (no Earth Engine account was configured) |
| Limitations | derived from Sentinel-2 by a neural network; not independent ground truth. A model trained to reproduce it cannot claim independent validation |

## C. ESA WorldCover

| Field | Value |
|---|---|
| Source | https://esa-worldcover.org/en/data-access (public S3 bucket `esa-worldcover`) |
| Provider | ESA / WorldCover consortium |
| Versions | 2020 v100, **2021 v200** (training labels) |
| Resolution / CRS | 10 m, EPSG:4326, 3° × 3° tiles |
| Licence | CC BY 4.0 |
| Role | training labels (2021) paired with 2021 imagery; reference context for detected regions |
| Limitations | Sentinel-1/2-based model output (overall accuracy roughly 74% for 2020 and 77% for 2021); **2020 and 2021 use different algorithms, so their differences are not treated as change**; annual, so within-year change is missing |

## D. Hansen Global Forest Change

| Field | Value |
|---|---|
| Source | https://glad.earthengine.app/view/global-forest-change (files from Google Cloud Storage `earthenginepartners-hansen`) |
| Provider | University of Maryland, Hansen et al. (2013) and annual updates |
| Version | **GFC-2025-v1.13** (loss years 2001–2025) |
| Layers used | `treecover2000` (%), `lossyear` |
| Resolution / CRS | 1 arc-second (about 30 m), EPSG:4326, 10° × 10° tiles |
| Licence | CC BY 4.0 |
| Role | masking labels with recent loss; corroboration of potential-loss regions; independent tree-extent agreement in evaluation |
| Limitations | "tree-cover loss" = stand-replacing disturbance of any cause (clearing, plantation harvest, fire, storms), **not equivalent to deforestation**; about 30 m resolution; annual; methodology changes over versions make trend comparisons inconsistent; the 2000 baseline ages over time |

## Training regions (2021)

Configured in `configs/regions.yaml`: about 13 × 13 km squares, each with the clearest 2021 dry-season acquisition. Same-day multi-tile mosaics or median composites are used where needed.

| Region | Role | Setting |
|---|---|---|
| rondonia_ariquemes | train | pasture/forest mosaic, town (4-tile mosaic) |
| para_altamira | train | Xingu river, town, forest |
| mato_grosso_sinop | train | cropland, city, forest remnants |
| acre_rio_branco | train | city, river, pasture, forest |
| riau_pekanbaru | train | plantations, peat forest, city (Indonesia) |
| bolivia_san_ignacio | train | Chiquitano dry (deciduous) forest |
| amazonas_manaus | validation | city edge, Rio Negro, forest (3-date composite) |
| mato_grosso_colniza | validation | humid forest frontier |
| peru_puerto_maldonado | **test** | town, river, gold-mining scars, forest |
| para_novo_progresso | **test** | BR-163 frontier (also the default monitoring AOI) |

Each region folder records scene IDs, acquisition dates, the label source and a label report (counts of ignored pixels by reason).
