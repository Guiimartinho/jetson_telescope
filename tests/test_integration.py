"""Testes de integração — a sessão inteira via adapters simulados (sem hardware)."""
import numpy as np

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.capture.sky import SkyModel, SkyCameraSource
from src.capture.source import SimulatorSource, FrameSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def _session(frames=8, w=400, h=300, focus_pos=6300):
    sky = SkyModel()
    mount = SimMount(cx=1560, cy=1350)
    foc = SimFocuser(position=focus_pos, best=6300)
    src = SkyCameraSource(sky, mount, foc, view_w=w, view_h=h, bad_frac=0.0)
    solver = SimSolver(mount)
    cfg = SessionConfig(source="sim", width=w, height=h, frames=frames, web=False)
    return Session(cfg, source=src, mount=mount, focuser=foc, solver=solver), sky


def test_auto_find_converges_end_to_end():
    s, sky = _session()
    ok = s.auto_find(sky.targets["M31"], tol_px=10, max_iters=15)
    assert ok is True
    assert s.stats["error_px"] <= 10


def test_autofocus_end_to_end():
    s, _ = _session(focus_pos=4200)
    s.autofocus()
    assert s.focuser.position() == s.stats["focus_pos"]
    assert abs(s.focuser.position() - 6300) < 600


def test_run_stack_accumulates_and_improves_snr(tmp_path):
    s, _ = _session(frames=8, focus_pos=6300)      # já em foco
    s.cfg.out_dir = str(tmp_path)
    stats = s.run_stack()
    assert stats["accepted"] >= 4
    assert stats["snr"] >= 1.0


# ---- contrato dos ports ---------------------------------------------------
def test_framesource_contract():
    """Todo FrameSource devolve (ndarray 2D/3D, dict) — contrato do port."""
    sky = SkyModel()
    sources = [
        SimulatorSource(),
        SkyCameraSource(sky, SimMount(), None, view_w=200, view_h=150),
    ]
    for src in sources:
        assert isinstance(src, FrameSource)
        frame, meta = src.read()
        assert isinstance(frame, np.ndarray) and frame.ndim in (2, 3)
        assert isinstance(meta, dict)
