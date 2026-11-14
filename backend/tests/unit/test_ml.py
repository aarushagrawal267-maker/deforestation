import numpy as np
import pytest
import torch
from sklearn.metrics import confusion_matrix, f1_score, jaccard_score

from forestwatch.labels.classes import IGNORE
from forestwatch.ml.calibrate import fit_temperature
from forestwatch.ml.dataset import augment, normalize
from forestwatch.ml.infer import entropy, predict_probs
from forestwatch.ml.losses import SegLoss, soft_dice_loss
from forestwatch.ml.metrics import binary_metrics, confusion, expected_calibration_error, metrics_from_confusion
from forestwatch.ml.train import lr_lambda
from forestwatch.ml.unet import UNet, count_parameters


@pytest.mark.parametrize("bands,base,depth,size", [(10, 16, 4, 64), (4, 8, 3, 48), (10, 8, 2, 37)])
def test_unet_output_shape(bands, base, depth, size):
    m = UNet(bands, 5, base, depth)
    y = m(torch.randn(2, bands, size, size))
    assert y.shape == (2, 5, size, size)


def test_unet_param_count_default():
    n = count_parameters(UNet(10, 5, 32, 4))
    assert 7_000_000 < n < 9_000_000


def test_skip_connections_present():
    m = UNet(10, 5, 8, 3)  # channels 8,16,32,64
    # each decoder block convolves (upsampled features + encoder skip) concatenated
    assert [u.conv.block[0].in_channels for u in m.ups] == [32 + 32, 16 + 16, 8 + 8]


def test_loss_ignores_ignore_index():
    logits = torch.randn(1, 5, 4, 4, requires_grad=True)
    t = torch.full((1, 4, 4), IGNORE)
    assert float(SegLoss()(logits, t)) == 0.0
    t[0, 0, 0] = 2
    loss = SegLoss()(logits, t)
    loss.backward()
    g = logits.grad[0, :, 1:, 1:]
    assert torch.count_nonzero(g) == 0  # ignored pixels get no CE gradient (dice uses masked probs)


def test_dice_perfect_prediction_is_zero():
    t = torch.randint(0, 5, (2, 8, 8))
    logits = torch.nn.functional.one_hot(t, 5).permute(0, 3, 1, 2).float() * 50
    assert float(soft_dice_loss(logits, t)) < 1e-3


def test_metrics_match_sklearn():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 5, 5000)
    p = np.where(rng.random(5000) < 0.7, y, rng.integers(0, 5, 5000))
    y_ign = y.copy()
    y_ign[:100] = IGNORE
    cm = confusion(p, y_ign, 5)
    np.testing.assert_array_equal(cm, confusion_matrix(y[100:], p[100:], labels=range(5)))
    m = metrics_from_confusion(cm)
    np.testing.assert_allclose(m["mean_iou"], jaccard_score(y[100:], p[100:], average="macro"), rtol=1e-9)
    np.testing.assert_allclose(m["mean_dice"], f1_score(y[100:], p[100:], average="macro"), rtol=1e-9)


def test_binary_metrics():
    p = np.array([1, 1, 0, 0], bool)
    r = np.array([1, 0, 1, 0], bool)
    m = binary_metrics(p, r, np.ones(4, bool))
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["iou"] == 1 / 3


def test_ece_perfectly_calibrated():
    conf = np.full(1000, 0.8)
    correct = np.zeros(1000, bool)
    correct[:800] = True
    ece, _ = expected_calibration_error(conf, correct)
    assert ece < 1e-9


def test_normalize_handles_nan():
    refl = np.ones((2, 3, 3), np.float32)
    refl[0, 0, 0] = np.nan
    x = normalize(refl, {"mean": [1.0, 0.5], "std": [1.0, 0.5]})
    assert x[0, 0, 0] == 0 and np.isfinite(x).all() and np.allclose(x[1], 1.0)


def test_augment_keeps_alignment():
    rng = np.random.default_rng(3)
    x = np.zeros((2, 8, 8), np.float32)
    y = np.zeros((8, 8), np.uint8)
    x[:, 1, 2] = 10
    y[1, 2] = 3
    xa, ya = augment(x, y, rng, gain_jitter=0, noise=0)
    assert np.argwhere(ya == 3).tolist() == np.argwhere(xa[0] == 10).tolist()


def test_lr_schedule():
    assert lr_lambda(0, 1, 10) == 0.05
    assert lr_lambda(1, 1, 10) == pytest.approx(1.0)
    assert lr_lambda(10, 1, 10) == pytest.approx(0.02)


def test_overfit_single_batch():
    torch.manual_seed(0)
    m = UNet(4, 5, 8, 2, dropout=0)
    x = torch.randn(2, 4, 32, 32)
    y = (x[:, 0] > 0).long() + 2 * (x[:, 1] > 1).long()
    opt = torch.optim.Adam(m.parameters(), 1e-2)
    loss_fn = SegLoss("ce")
    for _ in range(150):
        opt.zero_grad()
        loss = loss_fn(m(x), y)
        loss.backward()
        opt.step()
    acc = (m.eval()(x).argmax(1) == y).float().mean()
    assert float(acc) > 0.95


def test_predict_probs_tiling_matches_grid_and_sums_to_one():
    m = UNet(10, 5, 8, 2).eval()
    refl = np.random.default_rng(0).random((10, 150, 170)).astype(np.float32) * 0.3
    refl[:, 0, 0] = np.nan
    stats = {"mean": [0.15] * 10, "std": [0.1] * 10}
    p = predict_probs(m, refl, stats, tile=64, overlap=16)
    assert p.shape == (5, 150, 170)
    assert np.isnan(p[:, 0, 0]).all()
    np.testing.assert_allclose(np.nansum(p, axis=0)[1:, 1:], 1.0, atol=1e-4)
    e = entropy(p)
    assert np.nanmax(e) <= 1.0001 and np.nanmin(e) >= 0


def test_temperature_scaling_reduces_overconfidence():
    torch.manual_seed(0)

    class Overconfident(torch.nn.Module):
        config = {"num_classes": 2}

        def forward(self, x):
            # logits ~ correct 70% of time but very confident
            return x * 20

    x = torch.randn(8, 2, 16, 16)
    y = x.argmax(1)
    flip = torch.rand(8, 16, 16) < 0.3
    y = torch.where(flip, 1 - y, y)
    loader = [(x, y)]
    res = fit_temperature(Overconfident(), loader, torch.device("cpu"))
    assert res["temperature"] > 2 and res["ece_after"] < res["ece_before"]
