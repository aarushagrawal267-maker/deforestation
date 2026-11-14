# Methodology

## 1. Analysis grid

Each AOI gets one grid: the UTM zone of its centre, 10 m pixels, with the origin snapped to a multiple of 10 m. Every observation, label, prediction and change product for the AOI is written on this exact grid (same CRS, transform and shape). This guarantees pixel-wise correspondence between dates without further resampling, and tests check that the georeferencing is identical end to end.

## 2. Acquisition and preprocessing

1. **Catalogue search:** STAC query of Earth Search `sentinel-2-c1-l2a` for the AOI bounding box, a date window and a scene cloud limit.
2. **Windowed reads:** each band COG is read through a GDAL `WarpedVRT` onto the AOI grid, so only the AOI window is transferred. 10 m bands use bilinear resampling (effectively unchanged on aligned grids); 20 m bands use bilinear upsampling; SCL and cloud probability use nearest neighbour.
3. **Same-day mosaics:** an AOI on an MGRS tile boundary is covered by several tiles of the same overpass, so pixels missing in one tile are filled from the next.
4. **Composites (optional):** a per-pixel median of valid observations across several dates reduces cloud gaps in persistently cloudy regions.
5. **Radiometric scaling** with baseline harmonisation (see *Sentinel-2*).
6. **Quality mask:** codes for valid, no data, cloud, shadow, buffer and low quality. Only valid pixels are used anywhere downstream.

## 3. Training labels

Labels come from ESA WorldCover 2021 (v200), paired with 2021 dry-season Sentinel-2 imagery of the same region, and are mapped to five classes (tree cover, other vegetation, bare/sparse, water, built-up). A pixel is set to *ignore* when:

* it is within 1 px of a class boundary (registration and mixed-pixel uncertainty);
* Hansen GFC records loss in 2020–2022, so the label may describe the landscape before or after the change;
* it is invalid in the imagery (cloud, shadow, buffer, no data);
* its WorldCover class is out of scope (snow/ice, moss/lichen) or missing;
* if Dynamic World probabilities are supplied, its Dynamic World top class has probability < 0.6 or disagrees with WorldCover.

These are **model-generated reference labels**, not independent ground truth. The U-Net learns to reproduce them, including their errors.

## 4. Geographic split

Regions are assigned to train, validation or test **as whole regions**. No tile of a validation or test region is ever used in training, which prevents the spatial leakage that random tile splits cause. Validation regions are used for checkpoint selection, temperature scaling and threshold choices; test regions are used only for the final evaluation.

## 5. Model, training and calibration

See *U-Net model*. In short: a 10-band U-Net trained from scratch with class-weighted cross-entropy plus Dice loss, AdamW, cosine learning-rate schedule, early stopping on validation mIoU, and temperature scaling on validation regions so that probabilities are interpretable as confidence.

## 6. Inference

The AOI is processed in 256 × 256 tiles with 64 px overlap, blended with a Hann window to avoid seams. Outputs are calibrated class probabilities (stored ×250 as uint8), the argmax class map and normalised predictive entropy, all on the input grid.

## 7. Change detection

See *Change detection*.

## 8. Area estimates

* **Mapped area:** the count of 10 m pixels (100 m² nominal) or the geodesic area of vectorised regions, computed on the WGS84 ellipsoid.
* **Boundary uncertainty:** perimeter × half a pixel, reported as ± for every region.
* **Not included:** classification error (omission and commission). Pixel-counting areas from a map are biased. Unbiased area estimation needs a stratified reference sample (Olofsson et al., 2014); the investigation page lets an analyst record visual assessments as a first step towards that.
