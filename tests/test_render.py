"""Motor de render de produto — controles + presets sobre o stack linear."""
import numpy as np
import pytest

from src.postproc.render import RenderParams, render, PRESETS


def _linear(h=60, w=80):
    rng = np.random.default_rng(0)
    img = rng.uniform(0, 50, size=(h, w, 3)).astype(np.float32)
    img[h // 2 - 3:h // 2 + 3, w // 2 - 3:w // 2 + 3] = 5000.0     # uma "estrela"/nebulosa
    return img


def test_render_returns_uint8_rgb():
    out = render(_linear())
    assert out.dtype == np.uint8 and out.shape[-1] == 3
    assert out.min() >= 0 and out.max() <= 255
    assert out.max() > out.min()                                   # não é imagem chapada


def test_render_mono_input_promotes_to_rgb():
    out = render(np.full((40, 40), 100.0, np.float32))
    assert out.shape == (40, 40, 3)


def test_max_side_downscales():
    out = render(_linear(200, 300), max_side=100)
    assert max(out.shape[:2]) == 100


def test_stretch_lifts_faint_signal():
    lin = _linear()
    low = render(lin, RenderParams(stretch=2.0))
    high = render(lin, RenderParams(stretch=25.0))
    assert high.mean() > low.mean()                                # mais stretch = fundo mais claro


def test_params_from_query_parses_types():
    p = RenderParams.from_query({"stretch": "15", "saturation": "1.8",
                                 "scnr": "0.5", "remove_grad": "true"})
    assert p.stretch == 15.0 and p.saturation == 1.8 and p.scnr == 0.5
    assert p.remove_grad is True


def test_scnr_removes_green_cast():
    """SCNR (T18): um frame com excesso de verde deve ficar com menos verde após o render."""
    rng = np.random.default_rng(2)
    lin = rng.uniform(0, 30, size=(50, 50, 3)).astype(np.float32)
    lin[..., 1] += 300.0                                          # green cast forte
    no_scnr = render(lin, RenderParams(scnr=0.0, saturation=1.0)).astype(float)
    with_scnr = render(lin, RenderParams(scnr=1.0, saturation=1.0)).astype(float)
    # fração de verde (G / soma) cai com SCNR
    def green_frac(im):
        return im[..., 1].sum() / (im.sum() + 1e-6)
    assert green_frac(with_scnr) < green_frac(no_scnr)


def test_all_presets_render():
    lin = _linear()
    for name, params in PRESETS.items():
        out = render(lin, params)
        assert out.shape[-1] == 3, name
