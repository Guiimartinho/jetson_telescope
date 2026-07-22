"""T14 — plate solving REAL via ASTAP: parser puro + fluxo e2e com um ASTAP falso.

Roda no Windows/CI sem ASTAP instalado (o binário real é testado em test_solver_integration.py).
"""
import os
import sys

import numpy as np
import pytest

from src.control.solver import AstapSolver, parse_astap_result

FAKE = os.path.join(os.path.dirname(__file__), "fake_astap.py")

# saída .ini enlatada de um ASTAP real que RESOLVEU (formato KEY=VALUE)
SOLVED_INI = """PLTSOLVD=T
CRVAL1=83.822083
CRVAL2=-5.391111
CRPIX1=512.0
CRPIX2=384.0
CDELT1=-0.000555556
CDELT2=0.000555556
CROTA2=1.50
FOV_H=1.0
"""

UNSOLVED_INI = "PLTSOLVD=F\nWARNING=no stars matched\n"

CD_MATRIX_INI = """PLTSOLVD=T
CRVAL1=200.0
CRVAL2=45.0
CD1_1=-0.000392837
CD1_2=0.000392837
CD2_1=0.000392837
CD2_2=0.000392837
"""


def test_parse_solved():
    w = parse_astap_result(SOLVED_INI)
    assert w is not None
    assert w.ra_deg == pytest.approx(83.822083, abs=1e-4)
    assert w.dec_deg == pytest.approx(-5.391111, abs=1e-4)
    assert w.pixscale_arcsec == pytest.approx(2.0, abs=0.01)     # 0.000555556 deg * 3600
    assert w.rotation_deg == pytest.approx(1.5, abs=0.01)


def test_parse_unsolved_returns_none():
    assert parse_astap_result(UNSOLVED_INI) is None
    assert parse_astap_result("garbage without keys") is None


def test_parse_cd_matrix_derives_scale_and_rotation():
    w = parse_astap_result(CD_MATRIX_INI)
    assert w is not None
    # |(cd11, cd21)| * 3600 = sqrt(2)*0.000392837*3600 ~ 2.0 arcsec/px
    assert w.pixscale_arcsec == pytest.approx(2.0, abs=0.02)
    assert w.rotation_deg == pytest.approx(135.0, abs=0.5)       # atan2(+,-) = 135°


def _frame():
    rng = np.random.default_rng(0)
    return rng.normal(100, 5, size=(80, 100)).astype(np.float32)


def test_astap_solver_end_to_end_with_fake_binary():
    solver = AstapSolver(astap_bin=[sys.executable, FAKE], fov_deg=1.0)
    w = solver.solve_wcs(_frame())
    assert w is not None
    assert w.ra_deg == pytest.approx(83.8221, abs=1e-3)          # o padrão do ASTAP falso
    assert w.dec_deg == pytest.approx(-5.3911, abs=1e-3)


def test_astap_solver_uses_hint_roundtrip():
    solver = AstapSolver(astap_bin=[sys.executable, FAKE], fov_deg=1.0)
    w = solver.solve_wcs(_frame(), hint=(5.5, -12.0))            # RA=5.5h, DEC=-12°
    assert w.ra_deg == pytest.approx(5.5 * 15.0, abs=1e-2)       # 82.5°
    assert w.dec_deg == pytest.approx(-12.0, abs=1e-2)


def test_astap_solver_port_tuple():
    solver = AstapSolver(astap_bin=[sys.executable, FAKE], fov_deg=1.0)
    out = solver.solve(_frame())
    assert isinstance(out, tuple) and len(out) == 3
    assert out[0] == pytest.approx(83.8221, abs=1e-3)


def test_astap_solver_missing_binary_returns_none():
    solver = AstapSolver(astap_bin="astap_nao_existe_xyz", fov_deg=1.0)
    assert solver.solve_wcs(_frame()) is None                   # falha limpa, sem crash
