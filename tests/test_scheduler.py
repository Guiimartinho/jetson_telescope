"""Testes do agendador multi-alvo (Plan mode) — Fase 3."""
from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.scheduler import Scheduler, Target
from src.core.state import State
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def _session(w=300, h=220, focus=6300):
    sky = SkyModel()
    mount = SimMount()
    foc = SimFocuser(position=focus, best=6300)
    src = SkyCameraSource(sky, mount, foc, view_w=w, view_h=h, bad_frac=0.0)
    return Session(SessionConfig(width=w, height=h, web=False),
                   source=src, mount=mount, focuser=foc, solver=SimSolver(mount)), sky


def test_target_visibility_and_priority_order():
    hi = Target("A", (0, 0), priority=5)
    lo = Target("B", (0, 0), priority=1)
    off = Target("C", (0, 0), visible=False)
    assert hi.is_visible() and not off.is_visible()
    assert Target("D", (0, 0), visible=lambda: False).is_visible() is False
    ordered = sorted([lo, hi], key=lambda t: -t.priority)
    assert [t.name for t in ordered] == ["A", "B"]


def test_scheduler_runs_queue_in_priority_order_and_skips_invisible(tmp_path):
    s, sky = _session()
    s.cfg.out_dir = str(tmp_path)
    targets = [
        Target("M45", sky.targets["M45"], frames=4, priority=1),
        Target("M31", sky.targets["M31"], frames=4, priority=3),
        Target("M42", sky.targets["M42"], frames=4, priority=2, visible=False),
    ]
    out = Scheduler(s, do_autofocus=False).run(targets)

    assert [r["name"] for r in out["results"]] == ["M31", "M45"]   # prioridade desc
    assert out["skipped"] == ["M42"]                                # invisível pulado
    assert all(r["status"] == "ok" for r in out["results"])
    assert all(r["accepted"] >= 1 for r in out["results"])
    assert s.sm.state is State.IDLE                                 # terminou limpo


def test_scheduler_survives_failed_target(tmp_path):
    """Falha de auto-find num alvo não derruba a agenda (robustez)."""
    s, sky = _session()
    s.cfg.out_dir = str(tmp_path)
    s.solver = None                                                # força falha de find
    out = Scheduler(s, do_autofocus=False).run(
        [Target("M31", sky.targets["M31"], frames=3, priority=1)])
    assert out["results"][0]["status"] == "falha-autofind"
    assert s.sm.state is State.IDLE                                 # sem crash, estado limpo


def test_scheduler_updates_queue_stats(tmp_path):
    s, sky = _session()
    s.cfg.out_dir = str(tmp_path)
    Scheduler(s, do_autofocus=False).run(
        [Target("M31", sky.targets["M31"], frames=3, priority=1)])
    assert s.stats["queue_total"] == 1 and s.stats["queue_done"] == 1
    assert s.stats["target"] == "M31"
