"""Console de campo — Atlas (catálogo), histograma e render de imagem sob demanda."""
import numpy as np
import pytest

from src.server.console import (visible_targets, histogram_bins, warm_cache, Console,
                                STACKS, FAMOUS)
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
    assert by["M8"]["img"] == "lagoon_trifid"             # stack real
    assert by["Júpiter"]["img"] == "@jupiter"             # planeta (gerado dos modelos)
    m31 = by["M31"]["img"]                                # DSO: None OU foto do céu (@sky:) se baixada
    assert m31 is None or m31.startswith("@sky:")


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


def test_warm_cache_populates_catalog_and_never_raises():
    """Regressão: a 1ª abertura do Atlas levava 78,8 s no Orin. O warm-up paga esse custo no
    arranque do serviço, numa thread. Sem pyongc/astropy ele devolve False, nunca levanta."""
    from src.core import catalog as cat
    cat._CACHE = None                                     # força o caminho frio
    ok = warm_cache()
    assert ok is (True if cat.HAS_ONGC else False)
    if ok:
        assert cat._CACHE is not None and len(cat._CACHE) > 1000


def test_warm_cache_leaves_astropy_offline():
    """O warm-up também é o ponto onde o astropy é travado em modo offline (campo sem rede)."""
    pytest.importorskip("astropy")
    from astropy.utils import iers
    from src.core import catalog as cat
    iers.conf.auto_download = True
    cat._ASTROPY_OFFLINE = False
    warm_cache()
    assert iers.conf.auto_download is False


def test_state_reports_simulated_mount_by_default():
    """Sem link real (PC de dev, CI) a UI diz que a montagem é a simulada."""
    assert Console(FrameHub()).state()["mount"] == {"connected": False, "source": "sim"}


def test_state_reports_the_real_mount_link():
    """Com o link real ligado, a UI recebe o estado DELE: conectada ou não, posição, motivo."""
    class Link:
        def status(self):
            return {"connected": True, "ra_deg": 191.55, "dec_deg": 90.0, "error": None}

    st = Console(FrameHub(), mount_link=Link()).state()
    assert st["mount"]["source"] == "indi" and st["mount"]["connected"] is True
    assert st["mount"]["dec_deg"] == 90.0


def test_console_missing_image_none():
    con = Console(FrameHub())
    assert con.image_jpeg("nao_existe") is None


def test_console_histogram_fallback_empty():
    con = Console(FrameHub())                             # hub vazio, key inexistente
    assert con.histogram() == [0.0] * 40
