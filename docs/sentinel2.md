# Sentinel-2 & multispectral imagery

## The mission

Copernicus Sentinel-2 carries the MultiSpectral Instrument (MSI), which measures reflected sunlight in 13 spectral bands. The constellation (Sentinel-2A launched 2015, 2B in 2017, 2C in 2024) revisits a given point about every 5 days at the equator. Data is distributed in 110 × 110 km tiles on the Military Grid Reference System (MGRS), each in the UTM zone of its location.

## Level-2A surface reflectance

Level-2A products are atmospherically corrected by ESA's Sen2Cor processor to *bottom-of-atmosphere* reflectance. They include a **Scene Classification Layer (SCL)** at 20 m (cloud, cloud shadow, vegetation, water and so on) and a cloud-probability layer.

Sylva uses **Collection 1** from Element 84 Earth Search: the archive reprocessed by ESA to a single processing baseline (05.xx). This matters because baseline 04.00 (January 2022) introduced a −1000 DN offset (`BOA_ADD_OFFSET`). Mixing old and new legacy products without correction creates false reflectance changes, a classic source of false "deforestation". Surface reflectance is computed as

```
reflectance = DN × 0.0001 − 0.1      (Collection 1 and baselines ≥ 04.00)
reflectance = DN × 0.0001            (legacy baselines < 04.00)
```

Earth Search's Collection 1 has gaps in some periods (for example 2022 over parts of the Amazon). Sylva can fall back to the legacy `sentinel-2-l2a` collection and applies the baseline-specific offset above, so mixed comparisons stay consistent.

## Bands used

| Band | Name | Centre (nm) | Native resolution |
|---|---|---|---|
| B2 | Blue | 490 | 10 m |
| B3 | Green | 560 | 10 m |
| B4 | Red | 665 | 10 m |
| B5 | Red edge 1 | 705 | 20 m |
| B6 | Red edge 2 | 740 | 20 m |
| B7 | Red edge 3 | 783 | 20 m |
| B8 | NIR (broad) | 842 | 10 m |
| B8A | NIR (narrow) | 865 | 20 m |
| B11 | SWIR 1 | 1610 | 20 m |
| B12 | SWIR 2 | 2190 | 20 m |

The 60 m atmospheric bands (B1, B9, B10) are not used. **The 20 m bands are upsampled to the 10 m grid with bilinear interpolation. This does not create 10 m information**: their effective resolution remains 20 m, and the model's sharpness near small features is limited accordingly.

## Why multispectral bands matter for forests

* **Red vs NIR:** healthy leaves absorb red light and strongly reflect near-infrared, which is the basis of NDVI.
* **Red edge (B5–B7):** sensitive to chlorophyll content and canopy structure.
* **SWIR (B11, B12):** sensitive to leaf water and exposed soil. Clearings and burnt areas show a sharp SWIR increase, which is why NBR and NDMI are used as supporting indicators.

## Composites shown in the app

* **True colour:** B4, B3, B2.
* **False colour (vegetation):** B8, B4, B3. Vegetation appears red.
* **SWIR composite:** B12, B8A, B4. Bare soil and clearings stand out.
* **NDVI:** (B8 − B4) / (B8 + B4).

## Quality masking

| SCL class | Treatment |
|---|---|
| 0 no data, 1 saturated/defective | invalid |
| 3 cloud shadow | invalid |
| 8, 9 cloud (medium/high probability), 10 thin cirrus | invalid |
| 2 dark area / topographic shadow, 11 snow | low quality → invalid |
| cloud probability ≥ 40% | invalid |
| within 40 m (4 px) of cloud/shadow | buffer → invalid |
| 4, 5, 6, 7 | valid |

SCL is known to miss thin cloud edges and to under-detect shadows, which is why the dilation buffer exists and why change detection requires validity on both dates.
