#!/usr/bin/env python3
"""T1 — Mosaico multi-painel. Captura uma grade de painéis autonomamente e costura (Siril).

Ex.:  python run_mosaic.py --rows 2 --cols 2 --frames 40
Abra http://localhost:8000 para ver os painéis avançarem (o alvo mostra RxCy).
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
from src.core.mosaic import Mosaic
from src.server.webview import FrameHub, WebView
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def main():
    ap = argparse.ArgumentParser(description="T1 — mosaico multi-painel")
    ap.add_argument("--rows", type=int, default=2)
    ap.add_argument("--cols", type=int, default=2)
    ap.add_argument("--step", type=int, default=280, help="passo entre painéis (px de mundo)")
    ap.add_argument("--frames", type=int, default=40, help="frames por painel")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    cfg = SessionConfig(source="sim", width=a.width, height=a.height,
                        web=not a.no_web, port=a.port)
    sky = SkyModel(n_stars=4000)                 # denso p/ cada painel ter estrelas
    mount = SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1])
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
        session.stop = True
    signal.signal(signal.SIGINT, _stop)

    out = Mosaic(session).run(sky.targets["M31"], rows=a.rows, cols=a.cols,
                              step_px=a.step, frames_per_panel=a.frames)
    print(f"\n>> Painéis prontos: {len(out['fits'])} FITS · mosaico costurado: {out['stitched']}")

    if web is not None:
        web.stop()


if __name__ == "__main__":
    main()
