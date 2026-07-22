#!/usr/bin/env python3
"""Modo Sistema Solar (Lua/Planetas) — demo do pipeline lucky-imaging.

    py -3.11 run_planetary.py --kind jupiter --frames 200 --keep 0.15

Gera frames simulados (câmera planetária degradada por seeing/tremor/ruído), roda o pipeline
completo (grade → seleção dos mais nítidos → alinhamento por correlação de fase → média
ponderada em VRAM → wavelets) e salva um comparativo. Na Jetson roda em GPU (CuPy). Trocar o
simulador por uma `FrameSource` de câmera (V4L2/INDI alta cadência) dá o modo real. Ver docs/30.
"""
from __future__ import annotations
import argparse
import sys
import time

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.backend import backend_name
from src.planetary.simulator import PlanetSimulator
from src.planetary.stack import lucky_stack
from src.planetary.lucky import grade


def main():
    ap = argparse.ArgumentParser(description="Demo lucky imaging (Lua/planetas)")
    ap.add_argument("--kind", choices=["jupiter", "moon"], default="jupiter")
    ap.add_argument("--frames", type=int, default=200, help="frames capturados")
    ap.add_argument("--keep", type=float, default=0.15, help="fração dos mais nítidos (0..1)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="planetary.png", help="PNG de saída (cru | processado)")
    ap.add_argument("--no-wavelets", action="store_true")
    a = ap.parse_args()

    print(f">> backend: {backend_name()}")
    sim = PlanetSimulator(size=240, radius=84, kind=a.kind, seed=a.seed,
                          jitter=9.0, seeing=(0.5, 3.6), noise=6.0, color=True)
    print(f">> capturando {a.frames} frames de {a.kind}...")
    frames = sim.frames(a.frames)

    t = time.time()
    wl = None if a.no_wavelets else (0.5, 1.7, 2.2, 1.5, 1.0)
    res = lucky_stack(frames, keep=a.keep, sharpen=wl)
    dt = time.time() - t

    g = grade(frames)
    print(f">> usados {res.used}/{res.total} (top {a.keep*100:.0f}%), "
          f"referência #{res.ref}, {dt*1000:.0f} ms")
    print(f">> nitidez: pior {g.min():.0f} | melhor {g.max():.0f}")

    try:
        import cv2
        worst = np.clip(frames[int(np.argmin(g))], 0, 255).astype(np.uint8)
        best = np.clip(res.image, 0, 255).astype(np.uint8)
        sep = np.full((worst.shape[0], 6, 3), (40, 40, 40), np.uint8)
        panel = np.hstack([worst, sep, best])
        cv2.imwrite(a.out, cv2.cvtColor(panel, cv2.COLOR_RGB2BGR))
        print(f">> salvo {a.out}  (esq = 1 frame cru | dir = {res.used} frames + wavelets)")
    except Exception as e:
        print(f">> (sem cv2 p/ salvar PNG: {e})")


if __name__ == "__main__":
    main()
