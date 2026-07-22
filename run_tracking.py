#!/usr/bin/env python3
"""T11 — Fase 4: rastreamento de objeto rápido (satélite/ISS) em tempo real.

Um objeto cruza o campo; o laço detecta → prevê velocidade → corrige a montagem por
feed-forward, mantendo-o centralizado. Abra http://localhost:8000 (fase 'rastreando').

Na Jetson: detector YOLOv8→TensorRT; aqui cai no fallback CV. Ver docs/18.
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
from src.server.webview import FrameHub, WebView
from src.capture.sky import SkyModel
from src.capture.satellite import SatelliteScene
from src.control.mount import SimMount
from src.control.detector import YoloTensorRTDetector


def main():
    ap = argparse.ArgumentParser(description="T11 — rastreamento satélite/ISS")
    ap.add_argument("--frames", type=int, default=500)
    ap.add_argument("--vx", type=float, default=4.0)
    ap.add_argument("--vy", type=float, default=2.0)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--loop", action="store_true", help="repete o trânsito (demo contínua)")
    a = ap.parse_args()

    cfg = SessionConfig(width=a.width, height=a.height, web=not a.no_web, port=a.port)
    sky = SkyModel(n_stars=3000)
    mount = SimMount(cx=3000.0, cy=2200.0, nudge_residual_px=0.6, drift_px=0.0)
    scene = SatelliteScene(sky, mount, obj0=(3000.0, 2200.0), vel=(a.vx, a.vy),
                           view_w=a.width, view_h=a.height)
    detector = YoloTensorRTDetector()             # cai no fallback CV no PC

    hub = web = None
    if cfg.web:
        hub = FrameHub()
        web = WebView(hub, host=cfg.host, port=cfg.port)
        web.start()
        print(f">> Live view: http://localhost:{cfg.port}\n")

    session = Session(cfg, hub=hub, mount=mount)

    def _stop(*_):
        session.stop = True
    signal.signal(signal.SIGINT, _stop)

    while True:
        scene.t = 0
        mount.cx, mount.cy, mount.rot = 3000.0, 2200.0, 0.0   # reinicia o trânsito
        errs = session.track(scene, detector, frames=a.frames)
        if errs:
            print(f">> rastreamento: {len(errs)} frames, erro final ~"
                  f"{sum(errs[len(errs)//2:])/max(len(errs)//2,1):.1f} px")
        if not a.loop or session.stop:
            break

    if web is not None and not a.loop:
        web.stop()


if __name__ == "__main__":
    main()
