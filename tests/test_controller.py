"""Painel de controle — despacho de modos e parada."""
import time

from src.core.config import SessionConfig
from src.core.controller import Controller


def test_controller_builds_world():
    c = Controller(SessionConfig(width=200, height=150, web=False))
    assert "M31" in c.sky.targets
    assert c.session.mount is c.mount and c.session.filterwheel is not None


def test_controller_stop_command():
    c = Controller(SessionConfig(width=200, height=150, web=False))
    c.session.stop = False
    c.dispatch("stop")
    assert c.session.stop is True


def test_controller_starts_and_stops_a_mode(tmp_path):
    c = Controller(SessionConfig(width=300, height=220, web=False, out_dir=str(tmp_path)))
    c.dispatch("start:autofind:M31")                 # inicia modo numa thread
    time.sleep(0.6)
    assert c._worker is not None and c._worker.is_alive()
    c.dispatch("stop")                               # pede parada pela "UI"
    c._worker.join(timeout=15)
    assert not c._worker.is_alive()                  # encerrou de fato


def test_reset_state_recovers_from_terminal_stopped():
    """Regressão: STOPPED é terminal; reset_state permite iniciar um novo modo."""
    from src.core.orchestrator import Session
    from src.core.state import State
    s = Session(SessionConfig(width=100, height=100, web=False))
    s._set_state(State.STACKING)
    s._set_state(State.STOPPED)                      # terminal
    s.reset_state()
    assert s.sm.state is State.IDLE
    s._set_state(State.TRACKING)                     # não levanta após reset
    assert s.sm.state is State.TRACKING


def test_hub_stats_reflect_stopped_after_stop(tmp_path):
    """Regressao: o painel (via hub) mostrava STACKING pra sempre porque _set_state(STOPPED)
    nao empurrava o estado pro hub. /stats le do hub, entao ficava preso no ultimo frame."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=300, height=220, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:stack:M31")
    time.sleep(0.8)
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=15)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"          # o hub reflete a parada, nao STACKING


def test_controller_goto_mode_centers(tmp_path):
    """Modo GOTO celeste (T16): roda o laço RA/DEC e centraliza (erro pequeno em arcmin)."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=200, height=150, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:goto:M42")
    if c._worker:
        c._worker.join(timeout=30)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"
    assert stats.get("err_unit") == "arcmin"
    assert stats.get("error_px", 99) <= 1.0            # centralizou (<1 arcmin)


def test_controller_realdata_mode_stacks_real_photo(tmp_path):
    """Modo 'Dados reais': empilha a foto REAL de M67 (o dado real, visível no painel)."""
    import os
    from src.server.webview import FrameHub
    fixture = os.path.join(os.path.dirname(__file__), "data", "real_starfield_m67.fits")
    if not os.path.exists(fixture):
        import pytest
        pytest.skip("fixture de foto real ausente")
    hub = FrameHub()
    c = Controller(SessionConfig(width=400, height=300, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:realdata")
    time.sleep(1.5)
    _, stats = hub.get()
    assert stats.get("target") == "M67 (foto real)"
    assert stats.get("state") in ("STACKING", "STOPPED")
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=15)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"
    assert stats.get("accepted", 0) >= 1                 # aceitou frames reais (não rejeitou tudo)


def test_mode_completing_naturally_leaves_panel_ready(tmp_path):
    """Regressao: um modo que TERMINA SOZINHO (nao pelo Parar) nao pode deixar o painel preso
    num estado 'rodando' (ex.: STACKING) — senao os botoes parecem mortos. Deve ir p/ IDLE/STOPPED."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=300, height=220, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:goto:M31")                      # goto termina sozinho (converge)
    if c._worker:
        c._worker.join(timeout=30)
    _, stats = hub.get()
    assert stats.get("state") in ("IDLE", "STOPPED")  # painel pronto, nao congelado
    # e um novo modo inicia normalmente depois
    c.dispatch("start:tracking")
    ok = False
    for _ in range(40):
        time.sleep(0.2)
        if c.session.sm.state.name == "TRACKING":
            ok = True
            break
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=10)
    assert ok


def test_controller_switches_between_modes(tmp_path):
    """Regressão: trocar de modo (após um parar) deve iniciar o próximo, não travar em STOPPED."""
    c = Controller(SessionConfig(width=300, height=220, web=False, out_dir=str(tmp_path)))
    c.dispatch("start:scheduler")
    time.sleep(0.8)
    c.dispatch("start:tracking")
    ok = False
    for _ in range(40):
        time.sleep(0.2)
        if c.session.sm.state.name == "TRACKING":
            ok = True
            break
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=10)
    assert ok
