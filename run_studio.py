#!/usr/bin/env python3
"""Estúdio de Processamento — escolha o alvo e ajuste a imagem REAL ao vivo (produto estilo DWARF).

    py -3.11 run_studio.py            # abre em http://localhost:8010

Precisa do stack linear em data/stacks/ (gerado por scripts/process_real_dataset.py). Ver docs/24.
"""
from __future__ import annotations
import argparse
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.server.studio import StudioServer, CATALOG


def main():
    ap = argparse.ArgumentParser(description="Estudio de processamento do telescopio")
    ap.add_argument("--port", type=int, default=8010)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = acessivel na rede (celular)")
    ap.add_argument("--preview", type=int, default=1000, help="lado max do preview (px) — 1000 = ajuste fluido")
    a = ap.parse_args()

    srv = StudioServer(host=a.host, port=a.port, preview_max=a.preview)
    srv.start()
    print(f">> Estudio: http://localhost:{a.port}")
    print(f">> Alvos: {', '.join(m['name'] for m in CATALOG.values())}")
    print(">> Escolha o alvo, ajuste os controles e baixe em alta resolucao.\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> encerrando estudio")


if __name__ == "__main__":
    main()
