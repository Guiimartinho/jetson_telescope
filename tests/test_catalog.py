"""Catálogo do céu (OpenNGC) + filtro pela óptica. Pula se pyongc não estiver instalado."""
import math
import pytest

from src.core import catalog as cat

# só os testes que consultam o catálogo dependem do pyongc; os de óptica/parser e os de
# operação offline (astropy) rodam sempre — são a garantia de campo (docs/34).
needs_ongc = pytest.mark.skipif(not cat.HAS_ONGC, reason="pyongc não instalado (OpenNGC)")


# ---- operação offline (sem internet no campo) -----------------------------
def test_configure_astropy_offline_disables_download():
    """Regressão: o astropy tentava BAIXAR a tabela IERS na 1ª transformação (~70 s no Orin,
    e timeout em campo, onde não há internet). Ver docs/34."""
    pytest.importorskip("astropy")
    from astropy.utils import iers
    assert cat.configure_astropy_offline() is True
    assert iers.conf.auto_download is False
    assert cat.configure_astropy_offline() is True          # idempotente


def test_altitude_still_works_offline():
    """O download desligado NÃO pode quebrar o cálculo: sem `iers_degraded_accuracy='ignore'`,
    uma data fora da cobertura da tabela embutida viraria exceção."""
    pytest.importorskip("astropy")
    from datetime import datetime, timezone
    cat.configure_astropy_offline()
    m31 = cat.SkyObject(name="M031", ra_deg=10.68, dec_deg=41.27, kind="Galaxy",
                        mag=3.4, size_arcmin=178.0, common="Andromeda")
    alt = cat.altitude_deg(m31, lat=-23.55, lon=-46.63, when=datetime.now(timezone.utc))
    assert -90.0 <= alt <= 90.0


def test_altitude_leaves_download_disabled():
    """Qualquer caminho que calcule altitude deixa o astropy offline (não só o warm-up)."""
    pytest.importorskip("astropy")
    from astropy.utils import iers
    from astropy.time import Time
    iers.conf.auto_download = True                          # simula o padrão do astropy
    cat._ASTROPY_OFFLINE = False                            # força reconfiguração
    obj = cat.SkyObject(name="X", ra_deg=0.0, dec_deg=0.0, kind="Galaxy",
                        mag=None, size_arcmin=None)
    cat.altitude_deg(obj, lat=0.0, lon=0.0, when=Time("2026-01-01T00:00:00"))
    assert iers.conf.auto_download is False


def test_rig_fov_and_maglimit():
    rig = cat.Rig(focal_mm=250, aperture_mm=51, sensor_w_mm=11.2, sensor_h_mm=6.3)
    fw, fh = rig.fov_deg()
    assert 2.0 < fw < 3.5 and 1.0 < fh < 2.0                    # ~2.6 x 1.4 graus
    assert 14.0 < rig.limiting_mag() < 17.0                     # empilhando ~15-16


def test_parse_coords():
    assert cat._parse_ra("13:29:52.71") == pytest.approx(202.47, abs=0.1)
    assert cat._parse_dec("+47:11:42.6") == pytest.approx(47.20, abs=0.1)
    assert cat._parse_dec("-05:23:28") == pytest.approx(-5.39, abs=0.1)


@needs_ongc
def test_find_messier_resolves_radec():
    o = cat.find("M31")
    assert o is not None
    assert o.ra_deg == pytest.approx(10.68, abs=0.3)           # Andrômeda
    assert o.dec_deg == pytest.approx(41.27, abs=0.3)
    assert o.kind == "Galaxy"


@needs_ongc
def test_load_has_thousands_of_dsos():
    objs = cat.load()
    assert len(objs) > 5000
    assert all(o.ra_deg is not None for o in objs[:50])


@needs_ongc
def test_framable_filters_by_optics():
    rig = cat.DEFAULT_RIG
    objs = cat.load()
    fr = cat.framable(objs, rig)
    assert 0 < len(fr) < len(objs)                             # filtra, mas sobra bastante
    fov_min = min(rig.fov_deg()) * 60.0
    for o in fr[:200]:
        if o.mag is not None:
            assert o.mag <= rig.limiting_mag() + 1e-6
        if o.size_arcmin is not None:
            assert o.size_arcmin <= 0.9 * fov_min + 1e-6       # cabe no quadro


@needs_ongc
def test_altitude_computes():
    from astropy.time import Time
    o = cat.find("M31")
    alt = cat.altitude_deg(o, lat=-23.5, lon=-46.6, when=Time("2026-01-01T03:00:00"))
    assert -90.0 <= alt <= 90.0
