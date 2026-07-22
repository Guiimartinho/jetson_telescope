#!/usr/bin/env python3
"""Fase 3 (parte) — Agendador multi-alvo (Plan mode).

Percorre uma fila de alvos SOZINHO, como o DWARF a noite toda:
para cada alvo → auto-find → autofoco → live stack por N frames → próximo.
Abra http://localhost:8000 para ver a fila avançar (fase + alvo + progresso).

Exemplos:
  python run_scheduler.py                 # M31→M42→M45, 60 frames cada, live view
  python run_scheduler.py --loop          # repete a agenda indefinidamente (demo)
  python run_scheduler.py --no-web --frames 8   # headless rápido
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
from src.core.scheduler import Scheduler, Target
from src.server.webview import FrameHub, WebView
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def main():
    ap = argparse.ArgumentParser(description="Fase 3 — agendador multi-alvo (Plan mode)")
    ap.add_argument("--frames", type=int, default=60, help="frames de integração por alvo")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--loop", action="store_true", help="repete a agenda indefinidamente")
    a = ap.parse_args()

    cfg = SessionConfig(source="sim", width=a.width, height=a.height,
                        web=not a.no_web, port=a.port)
    sky = SkyModel()
    mount = SimMount()
    focuser = SimFocuser(position=4200, best=6300)
    source = SkyCameraSource(sky, mount, focuser, view_w=a.width, view_h=a.height)
    solver = SimSolver(mount)

    hub = web = None
    if cfg.web:
        hub = FrameHub()
        web = WebView(hub, host=cfg.host, port=cfg.port)
        web.start()
        print(f">> Live view: http://localhost:{cfg.port}\n")

    session = Session(cfg, hub=hub, source=source, mount=mount,
                      focuser=focuser, solver=solver)

    def _stop(*_):
        print("\n>> encerrando…")
        session.stop = True
    signal.signal(signal.SIGINT, _stop)

    targets = [
        Target("M31", sky.targets["M31"], frames=a.frames, priority=3),
        Target("M42", sky.targets["M42"], frames=a.frames, priority=2),
        Target("M45", sky.targets["M45"], frames=a.frames, priority=1),
    ]
    sched = Scheduler(session)

    while True:
        sched.run(targets)
        if not a.loop or session.stop:
            break
        focuser.move_to(4200)              # desfoca p/ o próximo ciclo da demo

    if web is not None and not a.loop:
        web.stop()


if __name__ == "__main__":
    main()
