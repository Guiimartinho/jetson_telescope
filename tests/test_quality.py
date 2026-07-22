import numpy as np

from src.gpu.quality import QualityConfig, detect_stars, measure_fwhm, assess
from tests._helpers import plant_star, star_field


def test_fwhm_matches_known_sigma():
    img = np.full((160, 160), 100.0, np.float32)
    for x, y in [(30, 30), (100, 40), (60, 110), (130, 130), (40, 90)]:
        plant_star(img, x, y, flux=9000, sigma=1.5)
    cfg = QualityConfig()
    fwhm = measure_fwhm(img, detect_stars(img, cfg)[0], cfg)
    assert abs(fwhm - 2.3548 * 1.5) < 1.2      # FWHM verdadeiro ~ 3.53


def test_blur_has_larger_fwhm_than_sharp():
    cfg = QualityConfig()
    sharp, _ = star_field(sigma=1.3, seed=1)
    blur, _ = star_field(sigma=3.6, seed=1)
    fs = measure_fwhm(sharp, detect_stars(sharp, cfg)[0], cfg)
    fb = measure_fwhm(blur, detect_stars(blur, cfg)[0], cfg)
    assert fb > fs
    assert fb > cfg.max_fwhm_px                # borrado deve estourar o portão


def test_assess_accepts_good_rejects_blur():
    cfg = QualityConfig()
    good, _ = star_field(sigma=1.4, noise=3.0, seed=2)
    blur, _ = star_field(sigma=3.8, noise=3.0, seed=2)
    assert assess(good, cfg)["accepted"] is True
    assert assess(blur, cfg)["accepted"] is False


def test_assess_rejects_starless_frame():
    cfg = QualityConfig()
    rng = np.random.default_rng(0)
    empty = np.full((200, 200), 100.0, np.float32) + rng.normal(0, 3, (200, 200)).astype(np.float32)
    r = assess(empty, cfg)
    assert r["accepted"] is False
    assert r["n_stars"] < cfg.min_stars


def test_weight_is_inverse_fwhm_squared():
    cfg = QualityConfig()
    good, _ = star_field(sigma=1.4, noise=2.0, seed=3)
    r = assess(good, cfg)
    assert r["weight"] > 0
    np.testing.assert_allclose(r["weight"], 1.0 / (r["fwhm"] ** 2), rtol=1e-6)
