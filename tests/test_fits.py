"""Testes de saída/leitura FITS com WCS (reuso astropy)."""
import numpy as np
import pytest

from src.io.fits_io import save_fits, load_fits, WcsInfo, HAS_ASTROPY

pytestmark = pytest.mark.skipif(not HAS_ASTROPY, reason="astropy ausente")


def test_save_load_roundtrip_and_meta(tmp_path):
    img = np.random.default_rng(0).uniform(0, 1000, (30, 40)).astype(np.float32)
    p = str(tmp_path / "x.fits")
    save_fits(p, img, meta={"OBJECT": "M31", "NCOMBINE": 42})
    data, hdr = load_fits(p)
    assert data.shape == (30, 40)
    np.testing.assert_allclose(data, img, rtol=1e-5)
    assert hdr["OBJECT"] == "M31" and int(hdr["NCOMBINE"]) == 42


def test_wcs_is_written_and_parseable(tmp_path):
    from astropy.wcs import WCS
    p = str(tmp_path / "w.fits")
    save_fits(p, np.zeros((100, 120), np.float32),
              wcs=WcsInfo(ra_deg=10.68, dec_deg=41.27, pixscale_arcsec=2.9))
    _, hdr = load_fits(p)
    w = WCS(hdr)
    assert w.has_celestial
    sky = w.pixel_to_world(120 / 2, 100 / 2)      # centro -> ~ (ra, dec) dados
    assert abs(sky.ra.deg - 10.68) < 0.1 and abs(sky.dec.deg - 41.27) < 0.1


def test_color_saved_as_three_planes(tmp_path):
    img = np.zeros((20, 30, 3), np.float32)
    img[..., 1] = 5.0
    p = str(tmp_path / "c.fits")
    save_fits(p, img)
    data, _ = load_fits(p)
    assert data.shape == (3, 20, 30)
    np.testing.assert_allclose(data[1], 5.0)
