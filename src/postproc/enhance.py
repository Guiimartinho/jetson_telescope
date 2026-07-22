"""T2 — Pós-processo do frame integrado: remoção de gradiente + denoise.

REUSAR: **GraXpert** (CLI/ONNX→TensorRT na Jetson) para denoise IA quando disponível.
Fallback embutido (sem GraXpert): remoção de gradiente por estimativa de fundo suave — passo
astro comum, real e testável. Aplicado uma vez no frame FINAL (nunca por sub). Ver docs/17.
"""
from __future__ import annotations
import shutil
import numpy as np
import cv2

from ..backend import asnumpy


def graxpert_available() -> bool:
    return shutil.which("graxpert") is not None


def remove_gradient(image, downscale: int = 8, sigma: float = 3.0):
    """Remove gradiente de fundo (poluição luminosa/vinheta residual) preservando estrelas.

    Estima o fundo de baixa frequência (downscale → blur → upscale) e subtrai, mantendo o
    nível médio. Estrelas (alta frequência) somem no downscale e são preservadas."""
    g = asnumpy(image).astype(np.float32)
    h, w = g.shape[:2]
    sw, sh = max(w // downscale, 4), max(h // downscale, 4)
    small = cv2.resize(g, (sw, sh), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigmaX=sigma)
    bg = cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC)
    out = g - bg + float(np.median(bg))
    return np.clip(out, 0, None)


def _graxpert(image, cmd: str):
    """Chama o GraXpert por CLI (reuso). Escafold — validar flags no bring-up."""
    import os
    import subprocess
    from ..io.fits_io import save_fits, load_fits, HAS_ASTROPY
    if not HAS_ASTROPY:
        return None
    tmp = os.path.join(os.getcwd(), "_graxpert_in.fits")
    save_fits(tmp, image)
    try:
        subprocess.run(["graxpert", "-cli", "-cmd", cmd, tmp], capture_output=True, timeout=600)
        out = tmp.replace(".fits", "_GraXpert.fits")
        if os.path.exists(out):
            data, _ = load_fits(out)
            return data
    except Exception:
        pass
    return None


def enhance(image, gradient: bool = True, denoise: bool = False):
    """Pós-processa o frame integrado. Usa GraXpert p/ denoise se instalado; senão fallback."""
    out = asnumpy(image).astype(np.float32)
    if denoise and graxpert_available():
        r = _graxpert(out, "denoising")
        if r is not None:
            out = r
    if gradient:
        if graxpert_available() and denoise:            # GraXpert já cuida do fundo
            pass
        else:
            out = remove_gradient(out)
    return out
