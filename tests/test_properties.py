"""Testes baseados em propriedades (hypothesis) — invariantes que valem p/ QUALQUER entrada.

Pegam casos-limite que testes por exemplo não pensariam. Ver docs/10 §3.
"""
import numpy as np
from hypothesis import given, settings, strategies as st
from hypothesis.extra.numpy import arrays, array_shapes

from src.backend import asnumpy
from src.gpu.stacker import LiveStacker
from src.gpu.quality import QualityConfig, detect_stars, measure_fwhm
from src.gpu.calibration import Calibrator
from src.util.imageio import autostretch, robust_std, encode_jpeg
from tests._helpers import plant_star

_img = arrays(np.float32, array_shapes(min_dims=2, max_dims=2, min_side=4, max_side=24),
              elements=st.floats(-1e3, 1e4, allow_nan=False, allow_infinity=False))


@given(vals=st.lists(st.floats(0, 1e4, allow_nan=False, allow_infinity=False),
                     min_size=1, max_size=6),
       ws=st.lists(st.floats(0.1, 10, allow_nan=False, allow_infinity=False),
                   min_size=1, max_size=6))
def test_stack_result_is_bounded_by_inputs(vals, ws):
    """A média ponderada nunca sai de [min, max] dos valores de entrada."""
    n = min(len(vals), len(ws))
    vals, ws = vals[:n], ws[:n]
    s = LiveStacker()
    for v, w in zip(vals, ws):
        s.add(np.full((2, 2), v, np.float32), w)
    r = asnumpy(s.result())
    assert r.min() >= min(vals) - 1e-2
    assert r.max() <= max(vals) + 1e-2


@given(arr=_img)
def test_autostretch_always_uint8_in_range(arr):
    out = autostretch(arr)
    assert out.dtype == np.uint8 and out.min() >= 0 and out.max() <= 255


@given(arr=_img)
def test_robust_std_is_nonnegative(arr):
    assert robust_std(arr) >= 0.0


@given(arr=arrays(np.float32, array_shapes(min_dims=2, max_dims=2, min_side=6, max_side=30),
                  elements=st.floats(0, 4000, allow_nan=False, allow_infinity=False)))
def test_encode_jpeg_always_valid(arr):
    assert encode_jpeg(arr)[:2] == b"\xff\xd8"        # marcador SOI de JPEG


@given(f=st.floats(0, 1000), d=st.floats(0, 2000))
def test_calibration_never_negative(f, d):
    frame = np.full((3, 3), f, np.float32)
    dark = np.full((3, 3), d, np.float32)
    assert asnumpy(Calibrator(dark).apply(frame)).min() >= 0.0


@settings(max_examples=20, deadline=None)
@given(s1=st.floats(1.0, 2.0), delta=st.floats(0.6, 2.0))
def test_fwhm_grows_with_sigma(s1, delta):
    """FWHM medido é monotônico na largura real da PSF (invariante físico)."""
    cfg = QualityConfig()

    def fwhm_at(sig):
        img = np.full((90, 90), 100.0, np.float32)
        for x, y in [(28, 28), (60, 32), (40, 62), (64, 64)]:
            plant_star(img, x, y, flux=9000, sigma=sig)
        return measure_fwhm(img, detect_stars(img, cfg)[0], cfg)

    assert fwhm_at(s1 + delta) >= fwhm_at(s1) - 0.8   # folga p/ discretização
