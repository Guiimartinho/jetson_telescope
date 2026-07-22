"""T4 — controles no navegador (fila de comandos + parada via web)."""
from src.server.webview import FrameHub
from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount


def test_framehub_command_queue():
    h = FrameHub()
    h.push_command("stop")
    h.push_command("x")
    assert h.pop_commands() == ["stop", "x"]
    assert h.pop_commands() == []                    # esvazia após consumir


def test_poll_commands_sets_stop():
    h = FrameHub()
    src = SkyCameraSource(SkyModel(), SimMount(), None, view_w=200, view_h=150)
    s = Session(SessionConfig(width=200, height=150, web=False), source=src, hub=h)
    h.push_command("stop")
    s._poll_commands()
    assert s.stop is True


def test_web_stop_halts_run_stack(tmp_path):
    h = FrameHub()
    sky = SkyModel(n_stars=4000)
    src = SkyCameraSource(sky, SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1]),
                          None, view_w=300, view_h=220, bad_frac=0.0)
    s = Session(SessionConfig(width=300, height=220, frames=0, web=False, out_dir=str(tmp_path)),
                source=src, hub=h)
    h.push_command("stop")                           # loop infinito, mas para no 1º poll
    st = s.run_stack()
    assert s.stop is True and st["accepted"] == 0
