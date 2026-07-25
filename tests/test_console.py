"""Console de campo — Atlas (catálogo), histograma e render de imagem sob demanda."""
import numpy as np

from src.server.console import (visible_targets, histogram_bins, Console, STACKS, FAMOUS)
from src.server.webview import FrameHub


def _make_fits(path, h=48, w=64):
    from astropy.io import fits
    rng = np.random.default_rng(3)
    arr = rng.uniform(0, 40, size=(3, h, w)).astype(np.float32)
    arr[:, h // 2 - 3:h // 2 + 3, w // 2 - 3:w // 2 + 3] = 4000.0
    fits.PrimaryHDU(arr).writeto(path, overwrite=True)


def test_histogram_bins_shape_and_norm():
    rng = np.random.default_rng(0)
    img = (rng.uniform(0, 255, (40, 50, 3))).astype(np.uint8)
    bins = histogram_bins(img, n=40)
    assert len(bins) == 40
    assert max(bins) == 1.0 and min(bins) >= 0.0          # normalizado 0..1


def test_visible_targets_structure():
    ts = visible_targets()
    assert len(ts) == len(FAMOUS)
    for t in ts:                                          # contrato de cada alvo
        assert {"desig", "name", "cat", "mag", "alt", "visible", "img"} <= set(t)
    by = {t["desig"]: t for t in ts}
    assert by["M8"]["img"] == "lagoon_trifid"             # os 3 reais têm imagem
    assert by["M31"]["img"] is None                       # os demais não (ainda)


def test_console_renders_real_image(tmp_path, monkeypatch):
    p = tmp_path / "s.fits"
    _make_fits(str(p))
    monkeypatch.setitem(STACKS, "tt", {"name": "T", "kind": "nebulosa", "stack": str(p),
                                       "subs": 1, "exp": "1m", "cam": "sim"})
    con = Console(FrameHub())
    full = con.image_jpeg("tt")
    thumb = con.image_jpeg("tt", thumb=True)
    assert full and full[:2] == b"\xff\xd8"               # JPEG
    assert thumb and thumb[:2] == b"\xff\xd8"
    assert len(con.histogram("tt")) == 40                 # histograma do render real


def test_console_missing_image_none():
    con = Console(FrameHub())
    assert con.image_jpeg("nao_existe") is None


def test_console_histogram_fallback_empty():
    con = Console(FrameHub())                             # hub vazio, key inexistente
    assert con.histogram() == [0.0] * 40
