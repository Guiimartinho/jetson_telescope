"""Estúdio — carrega stack linear e renderiza JPEG sob demanda (endpoint /render)."""
import numpy as np
import pytest

from src.server.studio import Studio, CATALOG, _load_linear
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
