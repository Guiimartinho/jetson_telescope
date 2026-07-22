"""T19 — deconvolução Richardson-Lucy + denoise."""
import numpy as np
import pytest
from scipy.signal import fftconvolve

from src.postproc.deconv import (gaussian_psf, richardson_lucy, deconvolve_rgb,
                                 denoise_luminance)


def test_gaussian_psf_normalized():
    psf = gaussian_psf(1.5)
    assert psf.ndim == 2 and psf.shape[0] == psf.shape[1]
    assert psf.sum() == pytest.approx(1.0, abs=1e-5)


def test_richardson_lucy_recovers_sharpness():
    # imagem nítida (ponto) -> borrada -> deconvolução deve reafiar (pico maior que o borrado)
    img = np.zeros((41, 41), np.float32)
    img[20, 20] = 100.0
    psf = gaussian_psf(1.8)
    blurred = fftconvolve(img, psf, mode="same")
    restored = richardson_lucy(blurred, psf, iterations=20)
    assert restored.max() > blurred.max() * 1.5           # recuperou o pico


def test_deconvolve_rgb_noop_when_zero():
    rgb = np.random.default_rng(0).uniform(0, 100, (30, 40, 3)).astype(np.float32)
    out = deconvolve_rgb(rgb, iterations=0)
    assert np.array_equal(out, rgb)


def test_deconvolve_rgb_increases_detail():
    rng = np.random.default_rng(1)
    sharp = rng.uniform(0, 100, (60, 60, 3)).astype(np.float32)
    psf = gaussian_psf(1.6)
    blurred = np.dstack([fftconvolve(sharp[..., c], psf, mode="same") for c in range(3)])
    out = deconvolve_rgb(blurred, iterations=15, sigma=1.6)
    # mais detalhe = maior variância do gradiente (nitidez)
    def sharpness(im):
        g = im.mean(2)
        return float(np.var(np.gradient(g)[0]))
    assert sharpness(out) > sharpness(blurred)


def test_denoise_luminance_runs():
    u8 = (np.random.default_rng(2).uniform(0, 255, (40, 40, 3))).astype(np.uint8)
    out = denoise_luminance(u8, 0.5)
    assert out.shape == u8.shape and out.dtype == np.uint8
    assert np.array_equal(denoise_luminance(u8, 0.0), u8)   # 0 = no-op
