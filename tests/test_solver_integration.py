"""T14 — integração com o ASTAP REAL (binário + índice de estrelas). Pulado no CI/Windows.

Requer o ASTAP instalado no PATH e um FITS de céu real resolvível apontado por ASTAP_TEST_FITS
(precisa do índice de estrelas do ASTAP, ex.: H18/D50). Para rodar (WSL/Linux/Jetson ou PC com ASTAP):

    ASTAP_TEST_FITS=/caminho/campo.fits py -3.11 -m pytest tests/test_solver_integration.py -m hardware -v

Valida que o MESMO AstapSolver do CI resolve um campo real → RA/DEC plausíveis.
"""
import os
import shutil

import numpy as np
import pytest

from src.control.solver import AstapSolver

_ASTAP = shutil.which("astap") or shutil.which("astap_cli")
_FITS = os.environ.get("ASTAP_TEST_FITS")

pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(_ASTAP is None, reason="ASTAP não está no PATH"),
    pytest.mark.skipif(not (_FITS and os.path.exists(_FITS)),
                       reason="defina ASTAP_TEST_FITS apontando para um FITS resolvível"),
]


def test_real_astap_solves_field():
    from astropy.io import fits
    with fits.open(_FITS) as hdul:
        frame = np.asarray(hdul[0].data, dtype=np.float32)
    solver = AstapSolver(astap_bin=_ASTAP, fov_deg=float(os.environ.get("ASTAP_FOV", "3.0")))
    w = solver.solve_wcs(frame)
    assert w is not None, "ASTAP não resolveu (índice de estrelas instalado? FOV correto?)"
    assert 0.0 <= w.ra_deg < 360.0 and -90.0 <= w.dec_deg <= 90.0
    assert w.pixscale_arcsec > 0.0
