"""T5 — Value Objects + perfis de equipamento (YAML)."""
import pytest

from src.core.vo import Pointing, Fwhm, PixelScale, EquipmentProfile
from src.core.profiles import load_profile, profile_from_dict


def test_pixel_scale_from_optics():
    ps = PixelScale.from_optics(2.9, 250.0)
    assert abs(ps.arcsec_per_px - 206.265 * 2.9 / 250.0) < 1e-6


def test_fwhm_arcsec():
    assert abs(Fwhm(3.0).arcsec(PixelScale(2.39)) - 7.17) < 0.01


def test_value_objects_are_frozen():
    p = Pointing(10.0, 41.0)
    with pytest.raises(Exception):
        p.ra_deg = 0.0


def test_equipment_profile_derived():
    e = EquipmentProfile("x", "cam", 2.9, "mnt", 250.0, 51.0)
    assert abs(e.fratio - 250 / 51) < 1e-6
    assert abs(e.pixscale.arcsec_per_px - 206.265 * 2.9 / 250) < 1e-6


def test_load_profile_yaml():
    e = load_profile("profiles/redcat51_am3n_imx585.yaml")
    assert e.camera == "ZWO ASI585MC" and e.focal_mm == 250.0
    assert abs(e.pixscale.arcsec_per_px - 2.393) < 0.01


def test_profile_from_dict_incomplete_raises():
    with pytest.raises(ValueError):
        profile_from_dict({"name": "x"})
