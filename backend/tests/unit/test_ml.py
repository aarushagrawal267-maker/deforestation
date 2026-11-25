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


def test_load_checkpoint_clear_errors(tmp_path):
    from forestwatch.ml.infer import CheckpointError, load_checkpoint

    with pytest.raises(CheckpointError, match="not found"):
        load_checkpoint(tmp_path / "missing.pt")
    bad = tmp_path / "bad.pt"
    bad.write_bytes(b"truncated")
    with pytest.raises(CheckpointError, match="could not be read"):
        load_checkpoint(bad)
    torch.save({"state_dict": {}}, tmp_path / "partial.pt")
    with pytest.raises(CheckpointError, match="missing model_config"):
        load_checkpoint(tmp_path / "partial.pt")


def test_train_rejects_val_test_overlap(tmp_path):
    from forestwatch.ml.train import TrainConfig, train

    cfg = TrainConfig(train_regions=["a"], val_regions=["b"], test_regions=["b"])
    with pytest.raises(ValueError, match="validation and test"):
        train(cfg, tmp_path, tmp_path / "out")


def test_block_bootstrap_matches_metrics_and_brackets_point_estimate():
    from forestwatch.ml.baselines import _miou_tree_iou, block_bootstrap, block_confusions

    rng = np.random.default_rng(0)
    target = rng.integers(0, 5, size=(300, 260)).astype(np.uint8)
    target[:20] = IGNORE
    noisy = np.where(rng.random(target.shape) < 0.2, rng.integers(0, 5, size=target.shape), target).astype(np.uint8)
    blocks = block_confusions(noisy, target, block=64)
    # blocks partition the labelled pixels: their sum is the full confusion matrix
    full = confusion(noisy, target, 5)
    np.testing.assert_array_equal(blocks.sum(axis=0), full)
    miou, tree = _miou_tree_iou(full[None])
    ref = metrics_from_confusion(full)
    assert miou[0] == pytest.approx(ref["mean_iou"])
    assert tree[0] == pytest.approx(ref["per_class"][0]["iou"])

    res = block_bootstrap({"a": blocks, "b": blocks}, n_boot=200, seed=1)
    lo, hi = res["models"]["a"]["mean_iou_ci"]
    assert lo <= ref["mean_iou"] <= hi and hi - lo < 0.1
    # identical models: the paired difference is exactly zero in every replicate
    assert res["differences"]["b - a"]["mean_iou_ci"] == [0.0, 0.0]


def test_block_bootstrap_rejects_mismatched_blocks():
    from forestwatch.ml.baselines import block_bootstrap

    with pytest.raises(ValueError):
        block_bootstrap({"a": np.ones((3, 5, 5)), "b": np.ones((4, 5, 5))})


def test_ndvi_threshold_fitted_on_given_regions():
    from forestwatch.ml.baselines import fit_ndvi_threshold
    from forestwatch.ml.dataset import RegionData

    bands = ["B2", "B3", "B4", "B5", "B6", "B7", "B8", "B8A", "B11", "B12"]
    refl = np.full((10, 40, 40), 0.1, np.float32)
    labels = np.ones((40, 40), np.uint8)
    refl[6, :20] = 0.5  # NDVI (0.5-0.1)/(0.5+0.1) = 0.67 for tree pixels
    refl[6, 20:] = 0.2  # NDVI 0.33 for non-tree pixels
    labels[:20] = 0
    th = fit_ndvi_threshold([RegionData("r", refl, labels, {})], bands)
    assert 0.33 < th <= 0.67


def _tiny_ckpt(path, bands, test_regions=("t",)):
    m = UNet(len(bands), 5, 8, 2)
    path.parent.mkdir(parents=True)
    torch.save(
        {
            "state_dict": m.state_dict(),
            "model_config": m.config,
            "bands": list(bands),
            "norm_stats": {"mean": [0.1] * len(bands), "std": [0.05] * len(bands)},
            "train_config": {"train_regions": ["a"], "val_regions": ["v"], "test_regions": list(test_regions)},
        },
        path,
    )
    return path


def test_baselines_feed_each_checkpoint_its_own_bands(tmp_path, monkeypatch):
    """A model trained on a band subset is compared with a 10-band model without mixing up their inputs."""
    import forestwatch.ml.baselines as bl
    from forestwatch.ml.dataset import RegionData
    from forestwatch.preprocessing.bands import BAND_NAMES

    rng = np.random.default_rng(0)

    def fake_region(region_dir, bands):
        refl = rng.random((len(bands), 140, 140)).astype(np.float32) * 0.3
        labels = rng.integers(0, 5, size=(140, 140)).astype(np.uint8)
        return RegionData(region_dir.name, refl, labels, {"label_year": 2021})

    monkeypatch.setattr(bl, "load_region", fake_region)
    monkeypatch.setattr(bl, "hansen_tree_agreement", lambda *a: {"tp": 1.0, "fp": 0.0, "fn": 0.0, "tn": 1.0})
    subset = _tiny_ckpt(tmp_path / "subset" / "best.pt", ["B4", "B8"])  # first, so its bands used to leak into the rest
    full = _tiny_ckpt(tmp_path / "full" / "best.pt", BAND_NAMES)
    res = bl.run_baselines(tmp_path, ["a"], ["t"], [subset, full], n_boot=20)
    assert set(res["five_class"]) == {"subset", "full", "pixel_gbdt", "majority_class"}

    with pytest.raises(ValueError, match="folders named"):
        bl.run_baselines(tmp_path, ["a"], ["t"], [full, full], n_boot=20)
