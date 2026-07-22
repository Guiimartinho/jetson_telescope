"""Testes de robustez: caminhos de erro, casos-limite e contratos dos escafolds.

Software robusto = falhar de forma clara e nunca quebrar em condições ruins. Ver docs/10.
"""
import pytest

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount


# ---- ring buffer ----------------------------------------------------------
def test_ring_buffer_reuses_buffers_in_cycle():
    from src.capture.ring_buffer import RingBuffer
    rb = RingBuffer(slots=3, shape=(2, 2))
    ids = [id(rb.acquire()) for _ in range(6)]
    assert ids[:3] == ids[3:]           # reusa em rodízio (sem alocar)
    assert len(set(ids[:3])) == 3       # 3 buffers distintos


# ---- simulador ------------------------------------------------------------
def test_simulator_emits_good_and_bad_frames():
    from src.capture.simulator import StarFieldSimulator, SimConfig
    sim = StarFieldSimulator(SimConfig(width=200, height=150, bad_frac=0.5, seed=1))
    kinds = {sim.frame(i)[1]["kind"] for i in range(30)}
    assert "good" in kinds
    assert "blur" in kinds or "cloud" in kinds


def test_simmount_tick_advances_and_slew_errs():
    m = SimMount(cx=100.0, cy=100.0, drift_px=0.5, goto_err_px=120, seed=2)
    x0 = m.pointing()[0]
    m.tick()
    assert m.pointing()[0] > x0                       # deriva de tracking
    m.slew(1000, 1000)
    assert m.pointing() != (1000.0, 1000.0, 0.0)      # GOTO 'bruto' erra


# ---- adapters INDI falham de forma CLARA quando não há servidor -----------
# (Antes eram escafolds que levantavam NotImplementedError; agora são implementados
#  sobre o IndiClient puro-Python e validados contra o servidor falso — ver test_indi_*.
#  Sem um indiserver no ar, devem falhar com erro de CONEXÃO óbvio, não erro críptico.)
def test_build_source_indi_fails_clearly_without_server():
    from src.capture.source import build_source
    with pytest.raises(OSError):                      # ConnectionRefused: porta morta
        build_source("indi", host="127.0.0.1", port=1)


def test_indi_adapters_fail_clearly_without_server():
    from src.control.mount import IndiMount
    from src.control.focuser import IndiFocuser
    with pytest.raises(OSError):
        IndiMount(host="127.0.0.1", port=1)
    with pytest.raises(OSError):
        IndiFocuser(host="127.0.0.1", port=1)


def test_build_source_unknown_kind_raises():
    from src.capture.source import build_source
    with pytest.raises(ValueError):
        build_source("telepatia")


# ---- caminhos de erro do orquestrador (sem crash) -------------------------
def _cam(cx, cy, w=200, h=150):
    return SkyCameraSource(SkyModel(), SimMount(cx=cx, cy=cy), None,
                           view_w=w, view_h=h, bad_frac=0.0)


def test_run_stack_all_rejected_does_not_crash(tmp_path):
    """Apontado p/ fora do céu (sem estrelas) → tudo rejeitado, sem exceção."""
    cfg = SessionConfig(width=200, height=150, frames=4, web=False, out_dir=str(tmp_path))
    stats = Session(cfg, source=_cam(-9000, -9000)).run_stack()
    assert stats["accepted"] == 0 and stats["rejected"] == 4


def test_auto_find_without_solver_returns_false():
    sky = SkyModel()
    mount = SimMount(cx=1560, cy=1350)
    src = SkyCameraSource(sky, mount, None, view_w=200, view_h=150, bad_frac=0.0)
    s = Session(SessionConfig(width=200, height=150, web=False),
                source=src, mount=mount, solver=None)
    assert s.auto_find(sky.targets["M31"], max_iters=3) is False


def test_session_syncs_simulator_dimensions():
    """Regressão: _get_source deve alinhar cfg.sim ao tamanho do pipeline."""
    cfg = SessionConfig(source="sim", width=320, height=240, web=False)
    cfg.sim.width, cfg.sim.height = 1600, 1200          # desalinhado de propósito
    frame, _ = Session(cfg)._get_source().read()
    assert frame.shape == (240, 320)
