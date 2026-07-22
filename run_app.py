#!/usr/bin/env python3
"""Painel de controle COMPLETO — testar todos os modos pelo navegador.

Abra http://localhost:8000 e use os botões: Empilhar, Auto-find, Agendador, Mosaico, Rastrear,
Noite (e Parar). Cada modo roda ao vivo; o painel mostra fase/estado/SNR/erro. Ver docs/19.
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
from src.server.webview import FrameHub, WebView


def main():
    ap = argparse.ArgumentParser(description="Painel de controle do telescopio (todos os modos)")
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=768)
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    cfg = SessionConfig(width=a.width, height=a.height, web=True, port=a.port, enhance=True)
    hub = FrameHub()
    ctrl = Controller(cfg, hub=hub)
    ctrl.start()
    web = WebView(hub, host=cfg.host, port=cfg.port, on_command=ctrl.submit)
    web.start()
    print(f">> Painel de controle: http://localhost:{cfg.port}")
    print(">> Botoes: Empilhar / Auto-find / Agendador / Mosaico / Rastrear / Noite / Parar\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> encerrando painel")


if __name__ == "__main__":
    main()
