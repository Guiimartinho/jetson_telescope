"""T15 — validação do pipeline com DADOS REAIS (não o céu sintético).

Usa um campo estelar REAL (CCD de M67, recorte 512×512 em tests/data/real_starfield_m67.fits;
origem: photutils.datasets.load_star_image). Pega o que o simulador esconde: PSFs reais, ruído
de leitura real, fundo real. Valida os 3 pilares do pipeline sobre esse campo:
  1) detecção + FWHM de estrelas reais,
  2) registro (astroalign/cv2) recuperando uma transformação conhecida,
  3) empilhamento reduzindo ruído ~√N.
Ver docs/21.
"""
import os

import numpy as np
import pytest

from src.gpu.quality import QualityConfig, detect_stars, measure_fwhm, laplacian_variance
from src.gpu.registration import estimate_transform, warp
from src.gpu.stacker import LiveStacker
from src.backend import asnumpy

FIXTURE = os.path.join(os.path.dirname(__file__), "data", "real_starfield_m67.fits")


@pytest.fixture(scope="module")
def real_field():
    from astropy.io import fits
    if not os.path.exists(FIXTURE):
        pytest.skip("fixture de campo real ausente (rode scripts/fetch_real_data.py)")
    with fits.open(FIXTURE) as hdul:
        return np.asarray(hdul[0].data, dtype=np.float32)


# ------------------------------------------------------- 1) detecção + FWHM
def test_detects_many_real_stars(real_field):
    cfg = QualityConfig()
    stars, flux = detect_stars(real_field, cfg)
    assert len(stars) >= 15                       # M67 é um aglomerado: dezenas de estrelas
    # estrelas ordenadas por brilho decrescente
    assert flux[0] >= flux[-1]


def test_fwhm_of_real_stars_is_plausible(real_field):
    cfg = QualityConfig(max_fwhm_px=99.0)         # não rejeita; só medir
    stars, _ = detect_stars(real_field, cfg)
    fwhm = measure_fwhm(real_field, stars, cfg)
    assert np.isfinite(fwhm)
    assert 1.0 < fwhm < 12.0                       # PSF real: alguns px


def test_laplacian_sharpness_positive(real_field):
    assert laplacian_variance(real_field) > 0.0


# ------------------------------------------------------- 2) registro real
def _apply_known_transform(img, dx, dy, angle_deg):
    """Cria uma cópia deslocada+rotacionada (transformação CONHECIDA) via cv2."""
    import cv2
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle_deg, 1.0)
    M[0, 2] += dx
    M[1, 2] += dy
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=0.0)


def _corr(a, b, mask):
    a, b = asnumpy(a)[mask > 0].ravel(), asnumpy(b)[mask > 0].ravel()
    return float(np.corrcoef(a, b)[0, 1])


def test_registers_real_starfield(real_field):
    cfg = QualityConfig()
    ref = real_field
    moved = _apply_known_transform(ref, dx=6.4, dy=-4.2, angle_deg=0.6)

    ref_stars, _ = detect_stars(ref, cfg)
    mv_stars, _ = detect_stars(moved, cfg)
    M = estimate_transform(mv_stars, ref_stars)          # mapeia moved -> ref
    assert M is not None, "registro falhou num campo estelar real"

    recovered, mask = warp(moved, M, ref.shape)
    valid = asnumpy(mask) > 0.5
    # o registro deve alinhar bem melhor que o desalinhado
    assert _corr(recovered, ref, valid) > 0.9
    assert _corr(recovered, ref, valid) > _corr(moved, ref, valid) + 0.05


# ------------------------------------------------------- 3) empilhamento √N
def test_stacking_reduces_noise_sqrt_n(real_field):
    ref = real_field
    n, sigma = 16, 60.0
    rng = np.random.default_rng(0)
    stacker = LiveStacker()
    for _ in range(n):
        noisy = ref + rng.normal(0.0, sigma, size=ref.shape).astype(np.float32)
        stacker.add(noisy, 1.0)
    result = asnumpy(stacker.result())

    # resíduo (empilhado - verdade) isola o ruído médio → deve cair ~√N
    resid_std = float(np.std(result - ref))
    single_std = sigma
    expected = single_std / np.sqrt(n)
    assert resid_std < single_std * 0.5                  # muito menos ruído que 1 frame
    assert 0.7 * expected < resid_std < 1.4 * expected   # coerente com √N


# ------------------------------------------------------- 4) fonte de foto real
def test_real_fits_source_yields_noisy_subs():
    from src.capture.real_source import RealFitsSource
    if not os.path.exists(FIXTURE):
        pytest.skip("fixture ausente")
    src = RealFitsSource(FIXTURE, view_w=640, view_h=480)
    f1, m1 = src.read()
    f2, _ = src.read()
    assert f1.shape == (480, 640)                        # encaixa no canvas do pipeline
    assert not np.array_equal(f1, f2)                    # subs diferem (ruído + deriva)
    stars, _ = detect_stars(f1, QualityConfig(max_fwhm_px=99))
    assert len(stars) >= 10                              # estrelas reais detectáveis no canvas
