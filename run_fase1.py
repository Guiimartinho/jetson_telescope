#!/usr/bin/env python3
"""Fase 1 completa — Live Stacking autônomo com live view no navegador.

Pipeline (docs/03 e docs/08):
  fonte (simulador OU câmera INDI) -> [debayer] -> calibração -> portão FWHM
    -> registro (astroalign/reuso) -> stacker CUDA float32 -> live view MJPEG

Detecta backend automaticamente (CuPy/GPU na Jetson, NumPy/CPU no PC de dev) e
reuso de astroalign se instalado.

Exemplos:
  # PC de dev (simulador) + live view em http://localhost:8000
  python run_fase1.py

  # validação headless rápida (sem web), 60 frames
  python run_fase1.py --frames 60 --no-web

  # Jetson, 4K, câmera real via INDI
  python run_fase1.py --source indi --width 3840 --height 2160

Ver docs/07-demo-fase1.md.
"""
from __future__ import annotations
import argparse
import signal

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.server.webview import FrameHub, WebView


def main():
    ap = argparse.ArgumentParser(description="Fase 1 — Live Stacking (Jetson/PC)")
    ap.add_argument("--source", choices=["sim", "indi"], default="sim")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--frames", type=int, default=0, help="0 = live até Ctrl+C")
    ap.add_argument("--stars", type=int, default=60, help="(simulador)")
    ap.add_argument("--bad-frac", type=float, default=0.15, help="(simulador)")
    ap.add_argument("--no-web", action="store_true", help="desliga o live view")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--out", default="output")
    ap.add_argument("--save-every", type=int, default=25)
    ap.add_argument("--calibrate", action="store_true",
                    help="(simulador) injeta bias/dark/vinheta/pixels quentes e os corrige")
    a = ap.parse_args()

    cfg = SessionConfig(source=a.source, width=a.width, height=a.height,
                        frames=a.frames, web=not a.no_web, port=a.port,
                        out_dir=a.out, save_every=a.save_every)
    cfg.sim.width, cfg.sim.height = cfg.width, cfg.height   # sincroniza dimensões do simulador
    cfg.sim.n_stars = a.stars
    cfg.sim.bad_frac = a.bad_frac

    source = calib = None
    if a.calibrate and a.source == "sim":
        from src.capture.source import SimulatorSource
        from src.capture.simulator import StarFieldSimulator
        from src.gpu.calibration import Calibrator
        cfg.sim.bias, cfg.sim.dark_current = 200.0, 6.0
        cfg.sim.hot_pixel_frac, cfg.sim.vignette = 0.002, 0.40
        source = SimulatorSource(cfg.sim)
        twin = StarFieldSimulator(cfg.sim)          # gêmeo: mesmos artefatos fixos
        calib = Calibrator.from_frames(
            dark=[twin.dark_frame() for _ in range(12)],
            flat=[twin.flat_frame() for _ in range(12)],
            bias=[twin.bias_frame() for _ in range(12)])
        print(">> Calibração ATIVA: master dark/flat/bias (12 cada) — corrige vinheta + pixels quentes\n")

    hub = None
    web = None
    if cfg.web:
        hub = FrameHub()
        web = WebView(hub, host=cfg.host, port=cfg.port)
        web.start()
        print(f">> Live view: http://localhost:{cfg.port}  (abra no navegador)\n")

    session = Session(cfg, hub=hub, source=source, calibrator=calib)

    def _stop(*_):
        print("\n>> encerrando…")
        session.stop = True
    signal.signal(signal.SIGINT, _stop)

    try:
        session.run()
    finally:
        if web is not None and cfg.frames == 0:
            print(">> live view continua ativo; Ctrl+C novamente para sair.")
        elif web is not None:
            web.stop()


if __name__ == "__main__":
    main()
