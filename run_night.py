#!/usr/bin/env python3
"""T12 — Modo autônomo noturno: uma "noite" completa sem operador.

Percorre uma lista de observações (single/mosaico, com filtro automático por tipo), fazendo
auto-find → autofoco → stack → FITS/WCS → resumo, e grava telemetria. Abra http://localhost:8000.
"""
from __future__ import annotations
import argparse
import signal
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.autonomous import AutonomousNight, Observation
from src.core.session_store import Telemetry
from src.server.webview import FrameHub, WebView
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver
from src.control.filterwheel import SimFilterWheel


def main():
    ap = argparse.ArgumentParser(description="T12 — modo autônomo noturno")
    ap.add_argument("--frames", type=int, default=40, help="frames por alvo/painel")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--loop", action="store_true")
    a = ap.parse_args()

    cfg = SessionConfig(width=a.width, height=a.height, web=not a.no_web, port=a.port, enhance=True)
    sky = SkyModel(n_stars=4000)
    mount = SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1])
    focuser = SimFocuser(position=4200, best=6300)
    source = SkyCameraSource(sky, mount, focuser, view_w=a.width, view_h=a.height)

    hub = web = None
    if cfg.web:
        hub = FrameHub()
        web = WebView(hub, host=cfg.host, port=cfg.port)
        web.start()
        print(f">> Live view: http://localhost:{cfg.port}\n")

    session = Session(cfg, hub=hub, source=source, mount=mount, focuser=focuser,
                      solver=SimSolver(mount), filterwheel=SimFilterWheel())

    def _stop(*_):
        session.stop = True
    signal.signal(signal.SIGINT, _stop)

    obs = [
        Observation("M31", sky.targets["M31"], frames=a.frames, kind="galaxy", priority=3),
        Observation("M42", sky.targets["M42"], frames=a.frames, kind="nebula", priority=2),
        Observation("M45", sky.targets["M45"], frames=max(a.frames // 2, 10),
                    kind="galaxy", mosaic=(2, 2), priority=1),
    ]
    night = AutonomousNight(session, telemetry=Telemetry("output/night.jsonl"))

    while True:
        focuser.move_to(4200)
        night.run(obs)
        if not a.loop or session.stop:
            break

    if web is not None and not a.loop:
        web.stop()


if __name__ == "__main__":
    main()
