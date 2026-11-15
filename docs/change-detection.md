# Change detection

## Workflow

1. Select an **earlier** and a **later** observation of the same AOI. Using the same season (for example both in the dry season) reduces phenological false changes. An optional **third, later observation** enables a persistence check.
2. Both observations are already on the same 10 m grid. A **residual co-registration** check runs phase correlation on high-pass-filtered NIR. Shifts above 0.5 px are corrected by translating the later image; smaller residuals are handled by edge suppression.
3. The **same U-Net checkpoint** with the same calibration produces P(tree) and entropy for each date.
4. **Spectral indices** are computed for each date: NDVI, NBR and NDMI, and their differences (later − earlier).
5. Each pixel is classified (defaults below; all are editable in the Change Detection Centre).

| Category | Rule |
|---|---|
| Cloud / invalid | invalid (cloud, shadow, buffer, no data) on **either** date |
| Stable forest | P₁ ≥ 0.6 and P₂ ≥ 0.6 |
| **Potential forest loss** | P₁ ≥ 0.6, P₂ ≤ 0.4, ΔP ≤ −0.3, entropy ≤ 0.8 on both dates |
| Potential vegetation / tree-cover gain | **stricter than loss:** P₁ ≤ 0.2, P₂ ≥ 0.8, ΔP ≥ +0.3, ΔNDVI ≥ +0.10, entropy ≤ 0.8, opening radius 2 px. Candidates that cross 0.4/0.6 but fail these are *uncertain* |
| Non-forest stable | P₁ ≤ 0.4 and P₂ ≤ 0.4 |
| Uncertain change | everything else (intermediate probabilities, high entropy, small ΔP) |

   Why gain is stricter: closed canopy rarely appears within one year, so most one-year "gain" at the loss thresholds was pasture or regrowth edges and phenology nudging P(tree) across 0.5. With the loss-style rule the 2024 → 2025 run reported 314.8 ha of gain in 246 regions; with the stricter rule it reports 6.8 ha in 5 regions, while loss is unchanged (489.3 ha).

6. **Edge suppression:** a morphological opening (radius 1 px) removes one-pixel strips along forest edges, a typical misregistration artefact.
7. **Spectral support:** a pixel is spectrally supported when ΔNDVI ≤ −0.10 or ΔNBR ≤ −0.10. By default, unsupported loss is still reported but flagged; the "require spectral support" option turns it into *uncertain* instead.
8. **Polygons:** 8-connected components with a **minimum mapping unit of 0.5 ha** (50 pixels, the FAO area threshold) are vectorised, simplified (5 m tolerance, topology preserved) and given:
   * an ID, centroid, bounding box, pixel count, geodesic area ± boundary uncertainty;
   * mean P(tree) on both dates, ΔP and entropy;
   * mean NDVI, NBR and NDMI on both dates and their deltas;
   * the fraction of pixels with spectral support and the fraction with fire-like ΔNBR (≤ −0.27, after Key & Benson);
   * the fraction overlapping **Hansen GFC loss** in the years spanned by the two dates (Hansen v1.13 covers 2001–2025);
   * the WorldCover tree fraction (reference context);
   * the persistence fraction, when a third observation is used;
   * the distance to the nearest invalid pixel.

## Evidence levels

| Level | Condition |
|---|---|
| Model only (`potential`) | passes the segmentation rules |
| Spectrally supported | ≥ 50% of pixels with NDVI/NBR decrease |
| Corroborated · Hansen GFC | ≥ 30% of the region overlaps Hansen loss in the period |

A region flagged as *possibly fire-related* (≥ 50% fire-like ΔNBR) is annotated only; the cause is never asserted.

## What the rules account for

| Confounder | Mitigation |
|---|---|
| Seasonal vegetation change | same-season pairs recommended; loss requires confident tree cover beforehand |
| Agricultural harvest | crops are "other vegetation" before harvest, so a harvest is not a tree → non-tree transition |
| Temporary clearing / regrowth | persistence check with a later observation |
| Clouds and shadows | dilated masks; validity required on both dates; distance-to-cloud attribute |
| Fire | dNBR annotation; still reported only as potential loss |
| Misregistration | phase-correlation check and correction; edge suppression |
| Sensor / processing differences | Collection-1 single baseline; offset harmonisation for legacy data |
| Prediction uncertainty | calibrated probabilities; intermediate band and entropy → uncertain |

## Wording

Sylva reports "**potential forest loss detected**" or "**suspected forest-cover change**". None of these is a verified deforestation event, and Hansen corroboration indicates agreement with another remote-sensing product, not ground verification.
