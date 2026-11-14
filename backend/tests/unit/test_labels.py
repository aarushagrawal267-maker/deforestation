import numpy as np

from forestwatch.labels.classes import IGNORE, WORLDCOVER_MAP, map_codes
from forestwatch.labels.fusion import build_labels, class_boundaries
from forestwatch.labels.reference import hansen_tiles, worldcover_tiles
from forestwatch.preprocessing.masking import Q_CLOUD, Q_VALID


def test_worldcover_tile_names():
    assert worldcover_tiles((-55.47, -7.14, -55.29, -6.96)) == ["S09W057"]
    assert worldcover_tiles((101.4, 0.45, 101.5, 0.55)) == ["N00E099"]
    assert len(worldcover_tiles((-57.1, -6.1, -56.9, -5.9))) == 4


def test_hansen_tile_names():
    assert hansen_tiles((-55.47, -7.14, -55.29, -6.96)) == ["00N_060W"]
    assert hansen_tiles((101.4, 0.45, 101.5, 0.55)) == ["10N_100E"]
    assert hansen_tiles((-60.5, -16.5, -60.4, -16.3)) == ["10S_070W"]


def test_worldcover_mapping():
    wc = np.array([[10, 95, 20, 30, 40, 50, 60, 80, 90, 70, 100, 0]], np.uint8)
    out = map_codes(wc, WORLDCOVER_MAP)
    assert out.tolist() == [[0, 0, 1, 1, 1, 4, 2, 3, 1, IGNORE, IGNORE, IGNORE]]


def test_boundaries():
    lab = np.zeros((6, 6), np.uint8)
    lab[:, 3:] = 1
    b = class_boundaries(lab, 1)
    assert b[:, 2:4].all() and not b[:, 0].any() and not b[:, 5].any()


def test_build_labels_rules():
    wc = np.full((10, 10), 10, np.uint8)  # all trees
    wc[:, 5:] = 30  # grassland on right
    q = np.full((10, 10), Q_VALID, np.uint8)
    q[0, 0] = Q_CLOUD
    loss = np.zeros((10, 10), np.uint8)
    loss[8, 1] = 21  # loss in label year -> ignored
    loss[8, 2] = 15  # older loss -> kept
    lab, rep = build_labels(wc, q, loss, label_year=2021, boundary_px=1)
    assert lab[0, 0] == IGNORE  # cloud
    assert lab[8, 1] == IGNORE  # recent Hansen loss
    assert lab[8, 2] == 0
    assert (lab[:, 4:6] == IGNORE).all()  # class boundary
    assert lab[5, 8] == 1
    assert rep["ignored_hansen_recent_loss"] == 1
    assert rep["labelled_pixels"] == int((lab != IGNORE).sum())


def test_dynamic_world_agreement_filter():
    wc = np.full((4, 4), 10, np.uint8)
    q = np.zeros((4, 4), np.uint8)
    probs = np.zeros((9, 4, 4), np.float32)
    probs[1] = 0.9  # trees, confident
    probs[1, 0, 0], probs[2, 0, 0] = 0.3, 0.7  # DW says grass -> disagree
    probs[1, 1, 1], probs[2, 1, 1] = 0.5, 0.5  # low confidence
    lab, rep = build_labels(wc, q, None, dw_probs=probs, boundary_px=0)
    assert lab[0, 0] == IGNORE and lab[1, 1] == IGNORE and lab[2, 2] == 0
    assert rep["ignored_dynamic_world_disagreement_or_low_confidence"] == 2
