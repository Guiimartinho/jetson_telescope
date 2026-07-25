#!/usr/bin/env python3
"""Console de campo — a UI de produto (Live/Atlas/Pro), estilo DWARF + ASIAIR.

    py -3.11 run_console.py            # abre em http://localhost:8080

Roda ao lado do painel (8000) e do estúdio (8010). Usa o mesmo Controller/FrameHub, o catálogo
real (Atlas) e o render (imagens). Servido pela própria Orin — no campo, via WiFi, sem internet.
Ver docs/33.
"""
from __future__ import annotations
import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.core.config import SessionConfig
from src.core.controller import Controller
from src.server.webview import FrameHub
from src.server.console import ConsoleServer


def main():
    ap = argparse.ArgumentParser(description="Console de campo do telescopio (Live/Atlas/Pro)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = acessivel na rede (celular)")
    a = ap.parse_args()

    cfg = SessionConfig(web=True, enhance=True)
    hub = FrameHub()
    ctrl = Controller(cfg, hub=hub)
    ctrl.start()
    srv = ConsoleServer(hub, host=a.host, port=a.port, on_command=ctrl.submit)
    srv.start()
    print(f">> Console de campo: http://localhost:{a.port}  (Live / Atlas / Pro)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> encerrando console")


if __name__ == "__main__":
    main()
