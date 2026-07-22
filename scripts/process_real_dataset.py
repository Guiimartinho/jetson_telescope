#!/usr/bin/env python3
"""Processa um conjunto de subs REAIS (OSC) em uma imagem colorida final — prova o pipeline
em dados de verdade e gera a "foto bonita" (T15+). Ex.: dataset Siril M8/M20 (ASI2600MC).

Fluxo (o mesmo do telescópio, offline): carrega lights FITS -> subtrai master-dark ->
debayer (Bayer->RGB) -> registra por estrelas (astroalign) -> empilha média float32 ->
neutraliza fundo + balanço de cor -> stretch asinh -> salva PNG (+ FITS linear).

Uso:
  py -3.11 scripts/process_real_dataset.py --lights DIR [--darks DIR] [--bayer RGGB]
           [--out output/m8m20.png] [--bin 2] [--max N]
"""
from __future__ import annotations
import argparse
import glob
import os
import sys

import numpy as np
import cv2

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.gpu.debayer import debayer                       # noqa: E402

try:
    import astroalign as aa
    HAS_AA = True
except Exception:
    HAS_AA = False


def _load(path):
    from astropy.io import fits
    with fits.open(path) as h:
        data = np.asarray(h[0].data, dtype=np.float32)
        hdr = h[0].header
    return data, hdr


def _master(files, label):
    if not files:
        return None
    acc = None
    for f in files:
        d, _ = _load(f)
        acc = d if acc is None else acc + d
    m = acc / len(files)
    print(f"  master-{label}: {len(files)} frames, mediana {np.median(m):.0f}")
    return m


from src.gpu.calibration import remove_hot_pixels as _remove_hotpix   # noqa: E402


def _bin2(img, n):
    if n <= 1:
        return img
    h, w = img.shape[:2]
    h, w = h - h % n, w - w % n
    img = img[:h, :w]
    if img.ndim == 2:
        return img.reshape(h // n, n, w // n, n).mean((1, 3))
    return img.reshape(h // n, n, w // n, n, 3).mean((1, 3))


def _autostretch(rgb):
    """Neutraliza o fundo por canal, balanceia a cor e aplica stretch asinh. rgb float32 HxWx3."""
    out = rgb.astype(np.float32).copy()
    # 1) fundo por canal -> preto neutro (remove poluição luminosa)
    for c in range(3):
        ch = out[..., c]
        bg = np.median(ch)
        out[..., c] = np.clip(ch - bg, 0, None)
    # 2) balanço de cor: iguala o ponto alto (99.5%) dos 3 canais
    highs = [np.percentile(out[..., c], 99.5) + 1e-6 for c in range(3)]
    ref = max(highs)
    for c in range(3):
        out[..., c] *= ref / highs[c]
    # 3) stretch asinh (realça a nebulosa fraca sem estourar as estrelas)
    hi = np.percentile(out, 99.7) + 1e-6
    x = out / hi
    a = 12.0
    stretched = np.arcsinh(a * x) / np.arcsinh(a)
    return np.clip(stretched, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lights", required=True)
    ap.add_argument("--darks", default=None)
    ap.add_argument("--bayer", default=None, help="RGGB/BGGR/GRBG/GBRG (senão usa o header)")
    ap.add_argument("--out", default="output/real_stack.png")
    ap.add_argument("--bin", type=int, default=1)
    ap.add_argument("--max", type=int, default=0, help="limita nº de lights (0=todos)")
    ap.add_argument("--mono", action="store_true", help="dado mono (sem debayer)")
    a = ap.parse_args()

    lights = sorted(glob.glob(os.path.join(a.lights, "*.fit*")))
    if a.max:
        lights = lights[:a.max]
    if not lights:
        raise SystemExit(f"nenhum FITS em {a.lights}")
    darks = sorted(glob.glob(os.path.join(a.darks, "*.fit*"))) if a.darks else []
    print(f"lights: {len(lights)} | darks: {len(darks)}")

    master_dark = _master(darks, "dark")

    # cor (debayer) vs mono: usa --bayer, senão BAYERPAT do header; sem nada (ou --mono) = mono
    _, hdr0 = _load(lights[0])
    bp = (a.bayer or (hdr0.get("BAYERPAT") or "")).strip()
    mono = a.mono or not bp
    pattern = bp or "RGGB"
    print(f"modo: {'MONO' if mono else 'cor (' + pattern + ')'}  | "
          f"dims {hdr0.get('NAXIS1')}x{hdr0.get('NAXIS2')}")

    ref_gray = ref_shape = None
    acc = None
    n = 0
    for i, path in enumerate(lights):
        raw, _ = _load(path)
        if master_dark is not None and master_dark.shape == raw.shape:
            raw = np.clip(raw - master_dark, 0, None)           # calibra (dark)
        else:
            raw = _remove_hotpix(raw)                           # sem dark: tira hot pixels
        rgb = np.repeat(raw[..., None], 3, axis=2) if mono else debayer(raw, pattern)
        rgb = _bin2(rgb, a.bin)
        gray = rgb.mean(2)
        if ref_gray is None:
            ref_gray, ref_shape = gray, rgb.shape
            reg = rgb
        else:
            try:
                T, _ = aa.find_transform(gray, ref_gray)       # registro por estrelas reais
                reg = np.dstack([aa.apply_transform(T, rgb[..., c], ref_gray)[0]
                                 for c in range(3)])
            except Exception as e:
                print(f"  [{i:02d}] registro falhou ({e}); pulando")
                continue
        acc = reg.astype(np.float32) if acc is None else acc + reg
        n += 1
        print(f"  [{i:02d}] {os.path.basename(path)} empilhado ({n})", flush=True)

    if n == 0:
        raise SystemExit("nada empilhado")
    stack = acc / n
    print(f"empilhados {n} lights. Aplicando stretch...")

    final = (_autostretch(stack) * 255).astype(np.uint8)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    cv2.imwrite(a.out, cv2.cvtColor(final, cv2.COLOR_RGB2BGR))
    print(f"OK -> {a.out}  ({final.shape[1]}x{final.shape[0]})")

    # também salva o linear em FITS (para reprocesso)
    try:
        from astropy.io import fits
        fits.PrimaryHDU(np.moveaxis(stack, 2, 0).astype(np.float32)).writeto(
            os.path.splitext(a.out)[0] + "_linear.fits", overwrite=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
