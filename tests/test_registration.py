import numpy as np

from src.gpu.registration import estimate_transform, warp


def _apply(M, pts):
    return pts @ M[:, :2].T + M[:, 2]


def test_identity_transform():
    rng = np.random.default_rng(0)
    P = rng.uniform(50, 350, size=(10, 2)).astype(np.float32)
    M = estimate_transform(P, P)
    assert M is not None
    np.testing.assert_allclose(_apply(M, P), P, atol=1.5)


def test_recovers_translation():
    rng = np.random.default_rng(1)
    P = rng.uniform(60, 340, size=(12, 2)).astype(np.float32)
    S = P + np.array([7.0, -4.0], np.float32)     # frame deslocado
    M = estimate_transform(S, P)                   # mapeia S -> P (referencial)
    assert M is not None
    np.testing.assert_allclose(_apply(M, S), P, atol=1.5)


def test_warp_shape_and_border_mask():
    img = np.zeros((60, 80), np.float32)
    img[30, 40] = 1000.0
    M = np.array([[1, 0, 5], [0, 1, 0]], np.float32)   # desloca +5 em x
    warped, mask = warp(img, M, (60, 80))
    assert warped.shape == (60, 80) and mask.shape == (60, 80)
    assert mask.max() == 1.0 and mask.min() == 0.0     # bordas ficam inválidas


def test_too_few_stars_returns_none():
    P = np.array([[10.0, 10.0], [20.0, 20.0]], np.float32)   # só 2 pontos
    assert estimate_transform(P, P) is None
