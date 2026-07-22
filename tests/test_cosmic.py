"""Remoção de raios cósmicos / hot pixels (astroscrappy + fallback)."""
import numpy as np
import pytest

from src.postproc import cosmic


def _frame_with_spikes():
    rng = np.random.default_rng(0)
    img = rng.normal(500, 5, size=(80, 80)).astype(np.float32)
    img[20, 30] = 60000.0            # raio cósmico / hot pixel
    img[55, 60] = 55000.0
    img[10, 10] = 48000.0
    return img


def test_fallback_removes_spikes():
    img = _frame_with_spikes()
    out = cosmic.clean_cosmics(img, prefer_astroscrappy=False)     # força o método próprio
    assert out[20, 30] < 2000 and out[55, 60] < 2000               # spikes removidos
    assert abs(out[0, 0] - img[0, 0]) < 50                         # fundo preservado


@pytest.mark.skipif(not cosmic.astroscrappy_available(), reason="astroscrappy não instalado")
def test_astroscrappy_removes_spikes():
    img = _frame_with_spikes()
    out = cosmic.clean_cosmics(img)                                # usa L.A.Cosmic
    assert out.shape == img.shape and out.dtype == np.float32
    assert out[20, 30] < 5000 and out[55, 60] < 5000              # spikes limpos


def test_preserves_a_real_star():
    """Uma 'estrela' (mancha de vários px) não deve ser apagada como raio cósmico."""
    img = np.full((80, 80), 500.0, np.float32)
    img[40:43, 40:43] = 20000.0                                   # estrela 3x3
    out = cosmic.clean_cosmics(img)
    assert out[41, 41] > 5000                                     # estrela sobrevive
