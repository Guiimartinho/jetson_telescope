#!/usr/bin/env python3
"""Fase 2 — Autonomia: AUTO-FIND (GOTO + plate solving) + AUTOFOCO + LIVE STACK.

Demonstra, em simulação (sem hardware), a sequência que o DWARF faz sozinho:
  1. slew 'bruto' para o alvo (erra por ~centenas de px — erro mecânico)
  2. laço de plate solving: resolve → calcula erro → corrige → repete até centralizar
  3. autofoco por curva de FWHM (hipérbole)
  4. live stacking do alvo centralizado e focado

Na Jetson, trocar SimMount/SimFocuser/SimSolver por INDI/ASTAP — o núcleo não muda.
Abra http://localhost:8000 para ver ao vivo (fase, erro de apontamento, FWHM, SNR).
Ver docs/09-fase2-autonomia.md.

Exemplos:
  python run_fase2.py                 # alvo M31, live view
  python run_fase2.py --target M42 --frames 200
  python run_fase2.py --no-web        # headless
"""
from __future__ import annotations
import argparse
import signal
import sys

try:                                   # console do Windows (cp1252) -> UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.server.webview import FrameHub, WebView
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def main():
    ap = argparse.ArgumentParser(description="Fase 2 — auto-find + autofoco + stacking")
    ap.add_argument("--target", default="M31", choices=["M31", "M42", "M45"])
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--frames", type=int, default=0, help="0 = live até Ctrl+C")
    ap.add_argument("--loop", action="store_true",
                    help="cicla M31→M42→M45 refazendo find+foco+stack (bom p/ demo)")
    ap.add_argument("--no-web", action="store_true")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--out", default="output")
    a = ap.parse_args()

    cfg = SessionConfig(source="sim", width=a.width, height=a.height,
                        frames=a.frames, web=not a.no_web, port=a.port, out_dir=a.out)

    # --- mundo simulado (na Jetson: INDI + câmera real + ASTAP) ---------------
    sky = SkyModel()
    mount = SimMount()
    focuser = SimFocuser(position=4200, best=6300)
    source = SkyCameraSource(sky, mount, focuser, view_w=a.width, view_h=a.height)
    solver = SimSolver(mount)
    target_xy = sky.targets[a.target]

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

    if a.loop:
        cfg.frames = a.frames if a.frames > 0 else 70      # stack limitado por ciclo
        names = ["M31", "M42", "M45"]
        k = 0
        while not session.stop:
            name = names[k % len(names)]
            k += 1
            print(f"\n########## CICLO {k}: alvo {name} ##########")
            focuser.move_to(4200)                          # desfoca p/ o autofoco atuar
            session.auto_find(sky.targets[name])
            if session.stop:
                break
            session.autofocus()
            if session.stop:
                break
            session.run_stack()
    else:
        print(f">> Alvo: {a.target} em {tuple(round(v) for v in target_xy)} (mundo)")
        session.run_autonomous(target_xy)

    if web is not None and cfg.frames != 0 and not a.loop:
        web.stop()


if __name__ == "__main__":
    main()
