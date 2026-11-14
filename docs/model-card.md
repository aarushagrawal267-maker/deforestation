# Model card: `unet-base32-v1`

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
* Validation mIoU fluctuated between epochs (0.77–0.85 after epoch 6); the selected checkpoint is the validation maximum, so the validation score is optimistic. The test numbers above are the unbiased ones.

## Training history note

An earlier run used Bolivia (dry forest) as a validation region. Tree IoU on validation fell to about 0.3 because no dry forest was in training, which was a domain gap rather than a model bug. That run was stopped after 6 epochs. Bolivia was moved to training and Colniza added for validation before the run documented here. Test regions were never changed.
