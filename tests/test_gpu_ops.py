"""Correção das ops aceleradas: o caminho GPU deve concordar com o de CPU."""
import numpy as np
import pytest

from src.backend import asnumpy
from src.gpu.registration import _warp_cpu, _warp_gpu, warp, _GPU_WARP
from src.gpu.quality import laplacian_variance
from tests._helpers import star_field, plant_star


def _rot_trans(deg, tx, ty):
    th = np.deg2rad(deg)
    return np.array([[np.cos(th), -np.sin(th), tx],
                     [np.sin(th), np.cos(th), ty]], np.float32)


@pytest.mark.skipif(not _GPU_WARP, reason="CuPy/GPU ausente")
def test_gpu_warp_places_star_like_cpu():
    """Valida a convenção de coordenadas: a estrela cai no mesmo lugar em CPU e GPU."""
    img = np.full((192, 256), 100.0, np.float32)
    plant_star(img, 80, 60, flux=20000, sigma=1.5)
    M = _rot_trans(5.0, 12.0, -7.0)
    wc, _ = _warp_cpu(img, M, img.shape)
    wg = asnumpy(_warp_gpu(img, M, img.shape)[0])

    def peak_xy(a):
        i = np.unravel_index(int(np.argmax(a)), a.shape)
        return i[1], i[0]
    (xc, yc), (xg, yg) = peak_xy(wc), peak_xy(wg)
    assert abs(xc - xg) <= 1 and abs(yc - yg) <= 1


@pytest.mark.skipif(not _GPU_WARP, reason="CuPy/GPU ausente")
def test_gpu_warp_matches_cpu_on_average():
    img, _ = star_field(w=256, h=192, n=15, noise=0.0, seed=3)
    M = _rot_trans(3.0, 6.0, -4.0)
    wc, mc = _warp_cpu(img, M, img.shape)
    wg, mg = (asnumpy(x) for x in _warp_gpu(img, M, img.shape))
    valid = (mc > 0.5) & (mg > 0.5)
    mad = float(np.abs(wc[valid] - wg[valid]).mean())
    assert mad / max(float(np.abs(wc[valid]).mean()), 1e-6) < 0.05


def test_warp_dispatch_returns_correct_shape():
    img, _ = star_field(w=200, h=160, seed=1)
    warped, mask = warp(img, _rot_trans(2.0, 5.0, 3.0), img.shape)
    assert asnumpy(warped).shape == (160, 200) and asnumpy(mask).shape == (160, 200)


def test_laplacian_variance_increases_with_sharpness():
    sharp, _ = star_field(sigma=1.2, noise=0.0, seed=1)
    blur, _ = star_field(sigma=3.5, noise=0.0, seed=1)
    assert laplacian_variance(sharp) > laplacian_variance(blur) > 0
