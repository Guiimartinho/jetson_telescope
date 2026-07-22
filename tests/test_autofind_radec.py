"""T16 — auto-find celeste em malha fechada (RA/DEC) com dublês, e a interface deg do IndiMount."""
import pytest

from src.control.autofind_radec import angular_sep_arcmin, close_loop_goto
from src.control.mount import SimRaDecMount
from src.control.solver import SimRaDecSolver

# alvos com RA/DEC reais aproximados (graus)
M31 = (10.68, 41.27)
M42 = (83.82, -5.39)


def test_angular_sep_known_values():
    assert angular_sep_arcmin((0, 0), (1, 0)) == pytest.approx(60.0, abs=0.1)   # 1° = 60'
    assert angular_sep_arcmin((0, 0), (0, 0)) == pytest.approx(0.0)
    # 1° em RA no equador ~ 60'; perto do polo encolhe
    assert angular_sep_arcmin((0, 60), (1, 60)) < 31.0


def test_goto_converges_and_centers():
    mount = SimRaDecMount(ra_deg=M31[0], dec_deg=M31[1], goto_err_arcmin=14.0)
    solver = SimRaDecSolver(mount)
    ok, err, iters = close_loop_goto(mount, solver, M31, tol_arcmin=1.0, max_iters=6)
    assert ok and err <= 1.0
    assert iters <= 3                                 # como no auto-find de pixels: ~2 iters


def test_goto_starts_far_ends_near():
    mount = SimRaDecMount(ra_deg=0.0, dec_deg=0.0, goto_err_arcmin=20.0)
    solver = SimRaDecSolver(mount)
    seen = []
    close_loop_goto(mount, solver, M42, tol_arcmin=0.8,
                    progress=lambda i, e, w, f: seen.append(e))
    assert seen[0] > 10.0                             # começa longe (erro do GOTO bruto)
    assert seen[-1] < 0.8                             # termina centralizado


def test_goto_reports_states():
    mount = SimRaDecMount(ra_deg=M31[0], dec_deg=M31[1])
    solver = SimRaDecSolver(mount)
    states = []
    close_loop_goto(mount, solver, M31, on_state=states.append)
    assert "SLEWING" in states and "SOLVING" in states


def test_goto_respects_should_stop():
    mount = SimRaDecMount(ra_deg=M31[0], dec_deg=M31[1], goto_err_arcmin=30.0)
    solver = SimRaDecSolver(mount)
    ok, err, iters = close_loop_goto(mount, solver, M31, should_stop=lambda: True, max_iters=6)
    assert iters == 6 and not ok                      # abortou em toda iteração → não centrou


def test_indimount_deg_interface_against_fake_indi():
    """A interface goto/sync/position (graus) do IndiMount fala com o INDI (RA em horas)."""
    from src.control.mount import IndiMount
    from src.io.indi_client import IndiClient
    from tests.fake_indi import FakeIndiServer
    srv = FakeIndiServer().start()
    try:
        cli = IndiClient("127.0.0.1", srv.port).connect()
        m = IndiMount(device="Telescope Simulator", client=cli).connect()
        m.goto(83.82, -5.39)                          # graus -> INDI recebe 83.82/15 h
        ra_deg, dec = m.position()
        assert ra_deg == pytest.approx(83.82, abs=0.05)
        assert dec == pytest.approx(-5.39, abs=0.05)
        cli.close()
    finally:
        srv.stop()
