import numpy as np
import scipy.ndimage as ndi

from src.backend import asnumpy
from src.planetary.wavelets import wavelet_sharpen, atrous


def _lapvar(x):
    return ndi.laplace(x.astype(np.float64)).var()


def test_identity_reconstruction():
    # à trous com todos os pesos = 1 reconstrói EXATAMENTE (Σ detalhes + resíduo = original)
    img = np.random.default_rng(0).uniform(0, 255, (64, 64)).astype(np.float32)
    out = wavelet_sharpen(img, weights=(1.0, 1.0, 1.0, 1.0), clip=False)
    np.testing.assert_allclose(out, img, atol=1e-2)


def test_atrous_layers_count():
    img = np.random.default_rng(1).uniform(0, 1, (32, 32)).astype(np.float32)
    details, residual = atrous(img, 3)
    details = [asnumpy(d) for d in details]
    residual = asnumpy(residual)
    assert len(details) == 3 and residual.shape == img.shape
    recon = residual + sum(details)
    np.testing.assert_allclose(recon, img, atol=1e-3)


def test_sharpen_increases_detail():
    base = np.random.default_rng(2).uniform(0, 255, (96, 96)).astype(np.float32)
    blur = ndi.gaussian_filter(base, 2.0)
    sharp = wavelet_sharpen(blur, weights=(0.5, 2.0, 2.5, 1.5))
    assert _lapvar(sharp) > _lapvar(blur)


def test_preserves_shape_dtype_color():
    img = np.random.default_rng(3).uniform(0, 255, (40, 50, 3)).astype(np.uint8)
    out = wavelet_sharpen(img)
    assert out.shape == img.shape and out.dtype == np.uint8


def test_clip_keeps_range():
    img = np.full((20, 20), 250.0, np.float32)
    out = wavelet_sharpen(img, weights=(3.0, 3.0, 3.0), clip=True)
    assert out.max() <= 255.0 and out.min() >= 0.0
