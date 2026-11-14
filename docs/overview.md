# Project overview

Sylva is an independent educational and research platform for monitoring forest cover with satellite imagery. It is not operated by, endorsed by, or affiliated with ESA, NASA, Copernicus, Google, the University of Maryland or any agency.

## What it does

1. **Retrieves available Sentinel-2 Level-2A acquisitions** for an area of interest (AOI). It searches the catalogue of existing acquisitions; it is **not a real-time feed**.
2. **Builds analysis-ready observations:** only the AOI window of each band is read, then masked for clouds, shadows and missing data and placed on a shared 10 m UTM grid.
3. **Segments land cover with a U-Net** that this project implements in PyTorch and trains from random initialisation on its own data, producing calibrated per-pixel class probabilities including P(tree cover).
4. **Compares two or more observation dates** to flag *potential* forest-cover loss and gain, with uncertainty and quality checks.
5. **Vectorises potential changes** into attributed regions (area, dates, probabilities, spectral indices).
6. **Cross-checks each region** against Hansen Global Forest Change, an independent Landsat-based reference.
7. **Presents everything on an interactive map** with an investigation page for each region.

## How the terms are used

| Term | Meaning in Sylva |
|---|---|
| Predicted tree cover | Pixels where the U-Net's calibrated P(tree) ≥ 0.5 |
| Reference tree cover | Tree cover in WorldCover, Dynamic World or Hansen. These are model or algorithm outputs themselves |
| Observed spectral change | Change in NDVI, NBR or NDMI between dates |
| Potential forest loss | High P(tree) earlier, low P(tree) later, passing the quality rules |
| Spectrally supported | Potential loss with a matching NDVI/NBR decrease |
| Corroborated (Hansen) | ≥ 30% of the region overlaps Hansen tree-cover loss in the same period |
| Uncertain | Pixels that fail the confidence rules; reported separately, never counted as loss |

"Forest" means **tree cover as defined by the label products** (trees taller than about 5 m, canopy ≥ 10%). This is not a legal or FAO forest definition. A detected change is not a verified deforestation event, and satellite imagery alone cannot establish its cause or legality.

## Architecture

```
React + MapLibre frontend (:5173) ──/api──▶ FastAPI backend (:8000) ──▶ SQLite
                                              │   rio-tiler map tiles from local COGs
                                              └── worker process (durable job queue)
                                                     ├─ forestwatch.providers   (Earth Search STAC / COG)
                                                     ├─ forestwatch.preprocessing (scaling, masks, grid)
                                                     ├─ forestwatch.labels      (WorldCover, Hansen, Dynamic World)
                                                     ├─ forestwatch.ml          (U-Net, training, calibration, inference)
                                                     └─ forestwatch.change      (rules, co-registration, polygons)
```

All rasters are Cloud-Optimised GeoTIFFs on the AOI's grid; vectors are GeoJSON (EPSG:4326) and can be exported as GeoPackage, CSV or zipped bundles with a provenance record.
