"""Testes dos ports de controle: montagem, focalizador, solver, autofoco."""
import numpy as np

from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver
from src.control.autofocus import fit_critical_focus, _hyperbola, AutoFocuser
from src.capture.sky import SkyModel, SkyCameraSource
from src.gpu.quality import QualityConfig


# ---- montagem -------------------------------------------------------------
def test_slew_lands_near_target():
    m = SimMount(goto_err_px=170, seed=1)
    errs = []
    for _ in range(40):
        m.slew(1000, 1000)
        cx, cy, _ = m.pointing()
        errs.append(np.hypot(cx - 1000, cy - 1000))
    assert 50 < np.mean(errs) < 400          # erro compatível com goto_err


def test_nudge_reduces_pointing_error():
    m = SimMount(seed=7)
    m.slew(500, 500)
    cx, cy, _ = m.pointing()
    e0 = np.hypot(cx - 500, cy - 500)
    m.nudge(500 - cx, 500 - cy)
    cx, cy, _ = m.pointing()
    assert np.hypot(cx - 500, cy - 500) < e0
    assert np.hypot(cx - 500, cy - 500) < 25   # resíduo mecânico pequeno


def test_closed_loop_autofind_converges():
    """O laço slew→solve→corrige deve centralizar (< 8 px)."""
    m = SimMount(seed=4)
    tx, ty = 500.0, 500.0
    m.slew(tx, ty)
    for _ in range(15):
        cx, cy, _ = m.pointing()
        ex, ey = cx - tx, cy - ty
        if np.hypot(ex, ey) <= 8:
            break
        m.nudge(-ex, -ey)
    cx, cy, _ = m.pointing()
    assert np.hypot(cx - tx, cy - ty) <= 8


# ---- solver ---------------------------------------------------------------
def test_sim_solver_returns_true_pointing_within_noise():
    m = SimMount(cx=1234, cy=567)
    sol = SimSolver(m, noise_px=1.0).solve(None)
    assert np.hypot(sol[0] - 1234, sol[1] - 567) < 6


# ---- autofoco -------------------------------------------------------------
def test_fit_recovers_hyperbola_vertex():
    c_true = 6300.0
    x = np.linspace(2000, 10000, 15)
    y = _hyperbola(x, 2.0, 0.01, c_true)
    assert abs(fit_critical_focus(x, y) - c_true) < 60


def test_autofocuser_finds_focus():
    sky = SkyModel()
    mount = SimMount(cx=1560, cy=1350)             # apontado p/ M31 (muitas estrelas)
    foc = SimFocuser(position=4200, best=6300)
    src = SkyCameraSource(sky, mount, foc, view_w=400, view_h=300, bad_frac=0.0)
    best, fwhm, _ = AutoFocuser(src, foc, QualityConfig()).run()
    assert abs(best - 6300) < 600
    assert fwhm < 5.0
