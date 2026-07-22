"""Estúdio — carrega stack linear e renderiza JPEG sob demanda (endpoint /render)."""
import numpy as np
import pytest

from src.server.studio import Studio, CATALOG, PLANETARY, _load_linear, render_planetary
from src.postproc.render import RenderParams, PRESETS


def _make_fits(path, h=50, w=70):
    from astropy.io import fits
    rng = np.random.default_rng(1)
    arr = rng.uniform(0, 40, size=(3, h, w)).astype(np.float32)    # 3xHxW (como salvamos)
    fits.PrimaryHDU(arr).writeto(path, overwrite=True)


def test_load_linear_orients_to_hwc(tmp_path):
    p = tmp_path / "s.fits"
    _make_fits(str(p))
    arr = _load_linear(str(p))
    assert arr.ndim == 3 and arr.shape[2] == 3                     # 3xHxW -> HxWx3


def test_studio_renders_jpeg(tmp_path, monkeypatch):
    p = tmp_path / "stack.fits"
    _make_fits(str(p))
    monkeypatch.setitem(CATALOG, "test", {"name": "T", "kind": "n", "stack": str(p),
                                          "subs": 1, "exp": "1m", "cam": "sim"})
    s = Studio(preview_max=40)
    jpg = s.render_jpeg("test", RenderParams(), full=False)
    assert jpg is not None and jpg[:2] == b"\xff\xd8"             # magic de JPEG
    full = s.render_jpeg("test", PRESETS["vivido"], full=True)
    assert full is not None and full[:2] == b"\xff\xd8"


def test_studio_missing_target_returns_none():
    s = Studio()
    assert s.render_jpeg("nao_existe", RenderParams()) is None


def test_real_catalog_entry_present():
    assert "lagoon_trifid" in CATALOG                              # o alvo real do dataset Siril


def test_render_planetary_wavelet_adds_detail():
    """render_planetary com wavelets deve revelar detalhe (var. do Laplaciano) num base LIMPO.

    Num base limpo (baixo ruído), realçar as escalas médias aumenta o detalhe. (Num frame ruidoso o
    número cai, porque a escala fina — ruído — é atenuada; por isso o teste usa base limpo.)"""
    import cv2
    from src.planetary.simulator import PlanetSimulator
    base = PlanetSimulator(size=96, seed=1, color=True, noise=0.4, seeing=(1.5, 1.5)).frames(1)[0]
    soft = render_planetary(base, {"wavelet": "0.0"})
    sharp = render_planetary(base, {"wavelet": "1.2"})
    lv = lambda x: cv2.Laplacian(cv2.cvtColor(x, cv2.COLOR_RGB2GRAY), cv2.CV_64F).var()
    assert soft.shape == base.shape and soft.dtype == np.uint8
    assert lv(sharp) > lv(soft)


def test_studio_renders_planetary_target():
    """Alvo planetário: gera o lucky-stack sob demanda e renderiza JPEG (sem FITS)."""
    s = Studio()
    jpg = s.render_planetary_jpeg("jupiter", {"wavelet": "1.2", "saturation": "1.3"})
    assert jpg is not None and jpg[:2] == b"\xff\xd8"
    assert s._mode.get("jupiter") == "planetary"                   # marcado como planetário
    jpg2 = s.render_planetary_jpeg("jupiter", {"wavelet": "0.5"})  # base cacheado
    assert jpg2 is not None and jpg2[:2] == b"\xff\xd8"


def test_planetary_targets_defined():
    assert "jupiter" in PLANETARY and "moon" in PLANETARY
    assert PLANETARY["jupiter"]["mode"] == "planetary"
