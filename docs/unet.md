# U-Net model

Sylva's segmentation model is a **U-Net implemented in this repository** (`backend/forestwatch/ml/unet.py`) and trained **from random initialisation** on this project's Sentinel-2 regions. No external, pretrained or third-party model is used for segmentation.

## Architecture

```
input  (10 bands, 256×256)
  └─ DoubleConv 10→32 ───────────────────────────────────────────┐ skip
      └─ MaxPool → DoubleConv 32→64 ─────────────────────────┐    │
          └─ MaxPool → DoubleConv 64→128 ────────────────┐   │    │
              └─ MaxPool → DoubleConv 128→256 ───────┐   │   │    │
                  └─ MaxPool → DoubleConv 256→512    │   │   │    │
                      Dropout2d(0.2)  (bottleneck)   │   │   │    │
                  ┌─ Up ×2 + 1×1 conv, concat ◀──────┘   │   │    │
              ┌─ Up, concat ◀────────────────────────────┘   │    │
          ┌─ Up, concat ◀────────────────────────────────────┘    │
      ┌─ Up, concat ◀─────────────────────────────────────────────┘
  1×1 conv 32→5  → softmax (calibrated by temperature T)
DoubleConv = (3×3 conv → BatchNorm → ReLU) × 2
```

* **Encoder:** 4 down-sampling stages (max-pool) doubling channels 32 → 512.
* **Decoder:** bilinear up-sampling followed by a 1×1 convolution, chosen to avoid the checkerboard artefacts of transposed convolution (which remains available as an option), then concatenation with the matching encoder features (skip connections) and a DoubleConv.
* **Initialisation:** Kaiming-normal weights.
* **Size:** about 7.24 M parameters at base width 32. The "quick" profile (width 16) has about 1.8 M.
* **Configurable:** input bands, width, depth (2–5), dropout and up-sampling mode, all from the Model Laboratory.

## Inputs

10 surface-reflectance bands, standardised per band with mean and standard deviation computed **from training regions only**. Masked pixels are set to 0 after standardisation and excluded from the loss.

## Classes

| ID | Class | WorldCover source classes |
|---|---|---|
| 0 | Tree cover | 10 Tree cover, 95 Mangroves |
| 1 | Other vegetation | 20 Shrubland, 30 Grassland, 40 Cropland, 90 Herbaceous wetland |
| 2 | Bare / sparse | 60 Bare / sparse vegetation |
| 3 | Water | 80 Permanent water |
| 4 | Built-up | 50 Built-up |
| 255 | Ignored | boundaries, recent loss, invalid imagery, snow, moss, no data |

There is no trained "uncertain" class, because no reference product defines one reliably. Uncertainty is expressed at inference time through calibrated probabilities (0.4 < P < 0.6) and normalised entropy.

## Training

| Setting | Default |
|---|---|
| Crops | random 256×256 crops from training regions, skipping crops with < 30% labelled pixels |
| Augmentation | flips, 90° rotations, per-band gain/offset jitter (σ = 0.05), Gaussian noise (σ = 0.03); no colour transforms |
| Loss | class-weighted cross-entropy (`ignore_index` = 255) + 0.5 × multi-class soft Dice |
| Class weights | inverse square-root frequency, normalised, capped at 10 |
| Optimiser | AdamW, lr 1e-3, weight decay 1e-4 |
| Schedule | 1-epoch linear warm-up, then cosine decay to 2% |
| Batch | 8 (CPU); mixed precision on CUDA |
| Selection | best validation mIoU; early stopping after 7 epochs without improvement |
| Calibration | temperature scaling (L-BFGS on validation logits); ECE reported before and after |

Every epoch's losses and metrics are written to SQLite by the training job and plotted in the Model Laboratory. Checkpoints contain the weights, architecture, band list, normalisation statistics, class names, temperature, training configuration, the per-epoch history and the scene IDs used.

## Evaluation

See *Model card* for the measured results and their interpretation.
