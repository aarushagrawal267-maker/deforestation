# Model card: `unet-base32-v2` (default)

`unet-base32-v2` is the model activated on a fresh install. It is the same architecture, data, regions and
schedule as `unet-base32-v1` (documented in full below), with two training changes aimed at the weak
bare/sparse class, which v1 over-predicted (precision 0.17, recall 0.61):

* **Rare-class crop sampling:** 25% of training crops are centred on a pixel of a rare class (< 5% of labels:
  bare/sparse and water), so the model sees more real examples.
* **Milder class weights:** freq^-0.25 instead of freq^-0.5 (bare/sparse weight 2.0 instead of 3.2).

| | |
|---|---|
| Config | `configs/training/v2.yaml` (seed 42) |
| Training | CPU, early-stopped at epoch 18; selected epoch 11 (best validation mIoU **0.858**) |
| Calibration | T = **1.030**; validation ECE 0.0045 → **0.0023** |
| Checkpoint | `models/unet-base32-v2/best.pt`, SHA-256 `d6bede73dfbc987d943d4d034ba8ec1922e0ff7eea705f3206a0dceb5fa7f7c6` |
| Initialisation | random. **No pretrained or external model.** |

### Test regions (Novo Progresso, Puerto Maldonado; never used for training, checkpoint selection or calibration)

| Metric | v1 | **v2** |
|---|---|---|
| Mean IoU (5 classes) | 0.733 | **0.740** |
| Mean Dice | 0.801 | **0.811** |
| Overall agreement | 94.89% | 94.93% |
| Tree cover IoU | 0.939 | 0.940 |
| Other vegetation IoU | 0.841 | 0.844 |
| Bare / sparse IoU / precision / recall / F1 | 0.157 / 0.174 / 0.611 / 0.271 | **0.193 / 0.220 / 0.615 / 0.324** |
| Water IoU | 0.957 | 0.956 |
| Built-up IoU | 0.773 | 0.766 |
| Tree vs Hansen F1 | 0.797 | 0.797 |

The bare/sparse class improved (F1 +0.05) but **is still unreliable**: it is 0.3% of the training labels and
2,370 pixels in the test regions, so these numbers are noisy. Built-up dropped slightly. The improvement is modest
and comes from one training run per configuration (no repeated seeds).

### Independent re-check (2026-11-24, fresh rebuild of the test regions)

The two test regions were rebuilt from scratch on a clean checkout (`python -m forestwatch.cli build-regions --only
peru_puerto_maldonado --only para_novo_progresso`) and both shipped checkpoints were re-evaluated with
`python -m forestwatch.cli evaluate models/<name>/best.pt` (Linux, CPU, torch 2.15.0+cpu):

| Metric (pooled, 2,887,273 px) | v1 | v2 |
|---|---|---|
| Mean IoU (5 classes) | 0.715 | 0.714 |
| Mean Dice | 0.788 | 0.793 |
| Overall agreement | 94.85% | 94.24% |
| Tree cover IoU | 0.942 | 0.934 |
| Bare / sparse F1 | 0.257 | 0.308 |
| Tree vs Hansen F1 | 0.807 | 0.808 |
| mIoU Novo Progresso / Puerto Maldonado | 0.662 / 0.687 | 0.672 / 0.669 |

Novo Progresso rebuilt identically (v1 per-region mIoU 0.662, as in the original evaluation). Puerto Maldonado did
not: the catalogue now returns a same-day two-scene mosaic (`S2B_T19LDG_20210814T144726_L2A` +
`S2B_T19LDG_20210814T145620_L2A`), and the labelled pixel count differs slightly (2,887,273 vs 2,886,812), so the
pooled numbers above are lower than the original table, mostly through the water and built-up classes. On this
rebuild v2 is **not** clearly better than v1 overall; it keeps its gain on the bare/sparse class (F1 0.31 vs 0.26).
Treat the difference between the two models as within run-to-run and data-version noise.

### Baselines and uncertainty (2026-11-25, same rebuilt test regions)

To show what the U-Net adds, three simple baselines were fitted on the **six training regions only** and scored
on the same test pixels, labels and ignore mask with the same metric code. 95% intervals come from a paired
spatial block bootstrap (242 blocks of 128 × 128 px, 1,000 replicates). Reproduce with
`python -m forestwatch.cli baselines` after building the train and test regions (about 1.5 min on 4 CPU cores).

| Model (pooled test regions) | Mean IoU [95% CI] | Overall agreement | Tree IoU [95% CI] | Tree vs Hansen F1 |
|---|---|---|---|---|
| Majority class (tree cover everywhere) | 0.129 [0.120, 0.137] | 64.3% | 0.643 [0.601, 0.684] | n/a |
| NDVI ≥ 0.44 → tree (threshold fitted on training regions) | n/a (tree vs non-tree only) | n/a | 0.881 [0.862, 0.898] | 0.774 |
| Per-pixel gradient boosting on the 10 bands (no spatial context) | 0.657 [0.626, 0.680] | 92.4% | 0.927 [0.916, 0.937] | n/a |
| U-Net v1 | **0.715** [0.690, 0.735] | 94.85% | **0.942** [0.934, 0.950] | 0.807 |
| U-Net v2 (default) | 0.714 [0.689, 0.734] | 94.24% | 0.934 [0.924, 0.943] | 0.808 |

Paired differences (same resampled blocks):

* U-Net v1 − per-pixel classifier: mIoU +0.045 to +0.072, tree IoU +0.012 to +0.019 (most of the gain is in
  built-up IoU 0.72 vs 0.55 and other vegetation 0.85 vs 0.79). The spatial context of the U-Net helps, but
  a per-pixel classifier already gets tree cover largely right.
* U-Net v2 − v1: mIoU −0.009 to +0.006 (no difference); tree IoU −0.012 to −0.006 (v2 slightly **worse** on
  the class that change detection uses). On the original data version the same comparison was +0.001
  (0.940 vs 0.939), so the sign depends on which scene mosaic is used for Puerto Maldonado.

**How to read the intervals.** They describe sampling variability *within these two test regions* only. They
do not include variability between regions (per-region mIoU differs by up to 0.03), between training seeds
(one run per configuration) or between data versions (the Puerto Maldonado mosaic changed pooled mIoU by
0.02–0.03), so the real uncertainty is larger than the intervals show.

**Test-set reuse.** v2 was designed after looking at v1's test-region bare/sparse precision and recall, so the
test regions are no longer a fully untouched hold-out for the v1 vs v2 comparison. The choice of v2 as the
default is supported by validation mIoU (0.858 vs 0.849), not only by the test table. Do not pick the default
model by comparing test-region numbers; retrain with several seeds and compare on validation regions.

### Change-detection runs with v2 (Novo Progresso, stricter gain rule)

| Run | Dates | Potential loss | Regions | Hansen-corroborated | Spectrally supported | Model only | Potential gain |
|---|---|---|---|---|---|---|---|
| `chg_15636eb9be` | 2024-07-09 → 2025-07-19 | **581.9 ± 106.1 ha** | 221 | 106 | 110 | 5 | 2.9 ha (5 regions) |
| `chg_b619870dfc` | 2023-07-30 → 2024-07-09 (+ 2025 persistence) | **304.8 ± 70.8 ha** | 176 | 57 | 68 | 51 | 1.1 ha (1 region) |

v2 flags more potential loss than v1 (581.9 vs 489.3 ha for 2024 → 2025) and more of it is Hansen-corroborated
(106 vs 88 regions). In the 2023 → 2024 run, 103 of 176 loss regions were still non-forest in July 2025.
Gain uses the stricter rule described in `docs/change-detection.md`. As with v1, none of this is verified deforestation.

---

# Previous model: `unet-base32-v1`

| | |
|---|---|
| Experiment | `exp_c496001f43` |
| Architecture | U-Net (this repository), base width 32, depth 4, bilinear up-sampling, dropout 0.2, **7,242,949 parameters** |
| Initialisation | random (Kaiming). **No pretrained or external model.** |
| Inputs | Sentinel-2 L2A surface reflectance, 10 bands (B2, B3, B4, B5, B6, B7, B8, B8A, B11, B12), 10 m grid |
| Output | 5 classes: tree cover, other vegetation, bare/sparse, water, built-up |
| Training data | 6 regions, 2021 dry season (about 13 × 13 km each): Rondônia, Altamira, Sinop, Rio Branco, Riau (Indonesia), San Ignacio (Bolivia, dry forest) |
| Labels | ESA WorldCover 2021 v200 mapped to 5 classes; boundaries, Hansen 2020–2022 loss and invalid pixels ignored. **Model-generated labels, not ground truth** |
| Validation | Manaus (composite), Colniza (both humid Amazon); used for checkpoint selection and calibration |
| Test (held out) | Novo Progresso (Pará, Brazil), Puerto Maldonado (Madre de Dios, Peru) |
| Training | 20 epochs × 480 random 256 px crops, batch 8, AdamW 1e-3, cosine schedule, CE + 0.5 Dice, seed 42 |
| Compute | CPU only (4 threads), **74 minutes** |
| Selected epoch | 17 (best validation mIoU **0.849**) |
| Calibration | temperature T = **1.086**; validation ECE 0.0083 → **0.0037** |
| Checkpoint SHA-256 | `8ef94edd4c814d10b1b662e2d1d8fb1df13dbe37ba4a86628baaf68618d42c54` |

All numbers below were produced by the evaluation job `eval_6436b23f01` on the two **test regions**, which were not used for training, checkpoint selection or calibration.

## 1. Agreement with WorldCover-derived reference labels (test regions)

2,886,812 labelled, valid pixels.

| Metric | Value |
|---|---|
| Mean IoU (5 classes) | **0.733** |
| Mean Dice / F1 | 0.801 |
| Overall agreement | 94.9% |
| Macro precision / recall | 0.772 / 0.879 |

| Class | IoU | Precision | Recall | F1 | Support (px) |
|---|---|---|---|---|---|
| Tree cover | **0.939** | 0.971 | 0.966 | 0.969 | 1,856,917 |
| Other vegetation | 0.841 | 0.922 | 0.905 | 0.914 | 782,505 |
| Bare / sparse | 0.157 | 0.174 | 0.611 | 0.271 | 2,370 |
| Water | 0.957 | 0.960 | 0.997 | 0.978 | 127,771 |
| Built-up | 0.773 | 0.830 | 0.918 | 0.872 | 117,249 |

Per region:

| Region | mIoU | Tree IoU | Overall agreement | Valid pixels |
|---|---|---|---|---|
| para_novo_progresso | 0.662 | 0.933 | 94.6% | 99.9% |
| peru_puerto_maldonado | 0.697 | 0.944 | 95.2% | 99.7% |

The lower per-region mIoU (vs the pooled value) comes from the very rare bare/sparse class, which averages in with equal weight.

**Interpretation.** These numbers measure how well the U-Net reproduces WorldCover on unseen regions. WorldCover itself has about 77% overall accuracy against independent reference data, so this is not accuracy against reality. Ignored pixels (class boundaries, recent loss, clouds), which are the hardest ones, are excluded and inflate the scores.

## 2. Agreement with Hansen GFC tree cover (more independent)

Tree class vs Hansen `treecover2000` ≥ 30% minus loss up to 2021, compared on 3 × 3 blocks (~30 m).

| Precision | Recall | F1 | IoU | Agreement |
|---|---|---|---|---|
| 0.698 | 0.928 | **0.797** | 0.662 | 78.1% |

Per region: Novo Progresso F1 0.855, Puerto Maldonado F1 0.751. Hansen is Landsat-based and uses a different definition (canopy ≥ 30% here), a different resolution and the 2000 baseline. Much of the "precision" gap is the U-Net calling secondary regrowth (absent from the 2000 baseline) tree cover. That is consistent with WorldCover, but not a pure error either way.

## 3. Change-detection runs (default AOI, Novo Progresso, 396 km²)

| Run | Dates | Potential loss | Regions (≥ 0.5 ha) | Hansen-corroborated | Spectrally supported | Model only | Potential gain | Valid both dates | Residual shift |
|---|---|---|---|---|---|---|---|---|---|
| `chg_df5cf6cf52` | 2024-07-09 → 2025-07-19 | **489.3 ± 89.4 ha** | 192 | 88 | 101 | 3 | 314.8 ha | 99.8% | 0.06 px |
| `chg_ab37f10f8c` | 2023-07-30 → 2024-07-09 (+ 2025-07-19 persistence) | **279.3 ± 63.9 ha** | 157 | 47 | 76 | 34 | 54.6 ha | 99.8% | 0.07 px |

* "±" is boundary-placement uncertainty only (perimeter × ½ pixel); classification error is not included.
* In the 2023 → 2024 run, **91 of 157** potential-loss regions remained non-forest in July 2025 (persistence ≥ 50%). The others may be regrowth, temporary change or false positives.
* The 2024 → 2025 **potential gain (315 ha)** is large for one year and should be treated with caution: inspection suggests much of it is pasture/regrowth edges whose probability crossed the threshold, not new forest.
* Neither run's "loss" is verified deforestation; Hansen corroboration means agreement with another remote-sensing product.

## Intended use

Educational and research exploration of tree-cover change in tropical South American forest landscapes using dry-season Sentinel-2 imagery, with human review of every flagged region.

## Not intended for

Legal, regulatory or enforcement decisions; attributing cause or responsibility; official area statistics; regions or seasons far outside the training domain (temperate/boreal forest, snow, wet-season imagery) without retraining and evaluation.

## Known weaknesses

* **Bare / sparse** (F1 0.27) is unreliable: under 1% of training labels; confused with built-up and other vegetation.
* Trained on dry-season imagery; deciduous dry forest in leaf-off condition is harder (one training region only).
* Inherits WorldCover's systematic errors (for example regrowth, plantations and agroforestry all as "tree cover").
* Validation mIoU fluctuated between epochs (0.77–0.85 after epoch 6); the selected checkpoint is the validation maximum, so the validation score is optimistic. The test numbers are the less biased ones, but the test regions informed the v2 design (see *Test-set reuse* above), and two regions are a small sample.

## Training history note

An earlier run used Bolivia (dry forest) as a validation region. Tree IoU on validation fell to about 0.3 because no dry forest was in training, which was a domain gap rather than a model bug. That run was stopped after 6 epochs. Bolivia was moved to training and Colniza added for validation before the run documented here. Test regions were never changed.
