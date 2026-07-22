"""Catálogo do céu (OpenNGC) + filtro pela óptica. Pula se pyongc não estiver instalado."""
import math
import pytest

from src.core import catalog as cat

pytestmark = pytest.mark.skipif(not cat.HAS_ONGC, reason="pyongc não instalado (OpenNGC)")


def test_rig_fov_and_maglimit():
    rig = cat.Rig(focal_mm=250, aperture_mm=51, sensor_w_mm=11.2, sensor_h_mm=6.3)
    fw, fh = rig.fov_deg()
    assert 2.0 < fw < 3.5 and 1.0 < fh < 2.0                    # ~2.6 x 1.4 graus
    assert 14.0 < rig.limiting_mag() < 17.0                     # empilhando ~15-16


def test_parse_coords():
    assert cat._parse_ra("13:29:52.71") == pytest.approx(202.47, abs=0.1)
    assert cat._parse_dec("+47:11:42.6") == pytest.approx(47.20, abs=0.1)
    assert cat._parse_dec("-05:23:28") == pytest.approx(-5.39, abs=0.1)


def test_find_messier_resolves_radec():
    o = cat.find("M31")
    assert o is not None
    assert o.ra_deg == pytest.approx(10.68, abs=0.3)           # Andrômeda
    assert o.dec_deg == pytest.approx(41.27, abs=0.3)
    assert o.kind == "Galaxy"


def test_load_has_thousands_of_dsos():
    objs = cat.load()
    assert len(objs) > 5000
    assert all(o.ra_deg is not None for o in objs[:50])


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


def test_altitude_computes():
    from astropy.time import Time
    o = cat.find("M31")
    alt = cat.altitude_deg(o, lat=-23.5, lon=-46.6, when=Time("2026-01-01T03:00:00"))
    assert -90.0 <= alt <= 90.0
