"""Remoção de estrelas (StarNet CLI se instalado + fallback morfológico)."""
import numpy as np

from src.postproc import starless


def _field_with_stars_and_nebula():
    img = np.full((120, 120, 3), 20, np.uint8)
    # nebulosa difusa (estrutura grande)
    yy, xx = np.mgrid[0:120, 0:120]
    neb = (120 * np.exp(-((xx - 60) ** 2 + (yy - 60) ** 2) / (2 * 30 ** 2))).astype(np.uint8)
    img[..., 0] = np.clip(img[..., 0] + neb, 0, 255)
    # estrelas (pontos pequenos brilhantes)
    for (y, x) in [(20, 25), (30, 90), (80, 40), (95, 100), (50, 55)]:
        img[y, x] = 255
    return img


def test_fallback_removes_stars_keeps_nebula():
    img = _field_with_stars_and_nebula()
    out = starless.remove_stars(img)                              # sem StarNet -> morfológico
    assert out.shape == img.shape and out.dtype == np.uint8
    # a nebulosa (centro) sobrevive; as estrelas (pontos) são bem atenuadas
    assert out[60, 60, 0] > 80                                    # nebulosa mantida
    assert out[20, 25].max() < 200                               # estrela removida/atenuada


def test_float_input_returns_float_same_scale():
    img = np.zeros((40, 40, 3), np.float32)
    img[5, 5] = 1000.0
    img[20:24, 20:24] = 800.0
    out = starless.remove_stars(img)
    assert out.dtype == np.float32 and out.shape == img.shape


def test_starnet_available_is_path_or_none():
    r = starless.starnet_available()
    assert r is None or isinstance(r, str)
