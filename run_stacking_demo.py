#!/usr/bin/env python3
"""Demo da Fase 1 — Live Stacking acelerado, com simulador (SEM câmera).

Roda todo o pipeline de céu profundo de ponta a ponta:
    simulador -> ring buffer -> portão de qualidade (FWHM) -> registro -> LiveStacker

Detecta o backend automaticamente:
    - Orin Nano Super (CuPy)  -> acumulador na GPU
    - PC de desenvolvimento (NumPy) -> mesma lógica, na CPU

Saídas em ./output:
    single_frame.png  (um único sub, ruidoso)
    stack_final.png   (integrado — SNR muito melhor)
    stack_XXXX.png    (progresso do empilhamento)

Uso:
    python run_stacking_demo.py                       # padrões (1600x1200, 150 frames)
    python run_stacking_demo.py --frames 300 --stars 80
    python run_stacking_demo.py --width 3840 --height 2160   # 4K (ideal na Jetson/GPU)

Ver docs/03-pipeline-software.md e docs/07-demo-fase1.md.
"""
from __future__ import annotations
import argparse
import os
import time

from src.backend import backend_name, sync, asnumpy
from src.capture.simulator import StarFieldSimulator, SimConfig
from src.capture.ring_buffer import RingBuffer
from src.gpu.quality import QualityConfig, assess
from src.gpu.registration import register
from src.gpu.stacker import LiveStacker
from src.util.imageio import save_png, robust_std


def main():
    ap = argparse.ArgumentParser(description="Demo de Live Stacking (Fase 1)")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--frames", type=int, default=150)
    ap.add_argument("--stars", type=int, default=60)
    ap.add_argument("--bad-frac", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--save-every", type=int, default=25)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    print(f"Backend: {backend_name()}")
    print(f"Frames: {args.frames}  |  Resolucao: {args.width}x{args.height}  |  Estrelas: {args.stars}\n")

    sim = StarFieldSimulator(SimConfig(width=args.width, height=args.height,
                                       n_stars=args.stars, bad_frac=args.bad_frac,
                                       seed=args.seed))
    ring = RingBuffer(slots=8, shape=(args.height, args.width))
    qcfg = QualityConfig()

    stacker = None
    ref_stars = None
    ref_shape = (args.height, args.width)
    first_single = None
    accepted = rejected = 0
    add_time = 0.0

    t0 = time.time()
    for i in range(args.frames):
        buf = ring.acquire()
        gray, meta = sim.frame(i, out=buf)

        q = assess(gray, qcfg)
        if not q["accepted"]:
            rejected += 1
            print(f"[{i:03d}] REJEITADO ({q['reason']:<15}) "
                  f"n_estrelas={q['n_stars']:2d} FWHM={q['fwhm']:.2f} [verdade: {meta['kind']}]")
            continue

        if ref_stars is None:                       # 1o frame bom = referencial
            ref_stars = q["stars"]
            stacker = LiveStacker(*ref_shape)
            warped, mask = gray.astype("float32"), None
        else:
            warped, mask, M = register(gray, q["stars"], ref_stars, ref_shape)
            if warped is None:
                rejected += 1
                print(f"[{i:03d}] REJEITADO (alinhamento falhou)")
                continue

        ta = time.time()
        stacker.add(warped, q["weight"], mask)
        sync()
        add_time += time.time() - ta
        accepted += 1

        if first_single is None:
            first_single = asnumpy(warped).copy()

        print(f"[{i:03d}] ok  n_estrelas={q['n_stars']:2d} FWHM={q['fwhm']:.2f} "
              f"peso={q['weight']:.3f}  (empilhados={accepted})")

        if accepted % args.save_every == 0:
            save_png(os.path.join(args.out, f"stack_{accepted:04d}.png"), stacker.result())

    elapsed = time.time() - t0

    # ---- Saídas e métrica de ganho de SNR ------------------------------------
    if stacker is None or first_single is None:
        print("\nNenhum frame aceito — ajuste os parâmetros do simulador/qualidade.")
        return

    final = stacker.result()
    save_png(os.path.join(args.out, "single_frame.png"), first_single)
    save_png(os.path.join(args.out, "stack_final.png"), final)

    noise_single = robust_std(first_single)
    noise_stack = robust_std(final)
    ratio = noise_single / max(noise_stack, 1e-6)

    print("\n" + "=" * 64)
    print(f"Aceitos: {accepted}   Rejeitados: {rejected}   "
          f"(taxa de rejeicao {100*rejected/max(args.frames,1):.0f}%)")
    print(f"Ruido de fundo — 1 frame: {noise_single:8.3f}   "
          f"stack: {noise_stack:8.3f}")
    print(f"Ganho de SNR: {ratio:5.2f}x   (esperado ~raiz(N) = {accepted**0.5:.2f}x)")
    print(f"Tempo total: {elapsed:.2f}s   |   media add()/frame: "
          f"{1000*add_time/max(accepted,1):.2f} ms")
    print(f"Imagens salvas em: {os.path.abspath(args.out)}")
    print("=" * 64)


if __name__ == "__main__":
    main()
