"""Remoção de estrelas — REUSO do StarNet++ (CLI) se instalado, fallback morfológico próprio.

Separar a nebulosa das estrelas permite esticar/realçar o gás sem estourar as estrelas (e recombinar
depois) — técnica que deixa a imagem "classe portfólio". O StarNet++ (rede neural) é o padrão; se não
estiver instalado, usamos uma abertura morfológica que remove pontos pequenos (estrelas) preservando a
estrutura difusa (nebulosa) — aproximação clássica, sem IA. Ver docs/29.
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import numpy as np
import cv2


def starnet_available(cmd: str = "starnet++"):
    """Caminho do executável do StarNet, se instalado (várias grafias comuns)."""
    for name in (cmd, "starnet2", "StarNetv2CLI", "starnet++_v2"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _to_u8_rgb(image):
    a = np.asarray(image)
    if a.dtype == np.uint8:
        return (a if a.ndim == 3 else np.repeat(a[..., None], 3, 2)), None
    f = a.astype(np.float32)
    lo, hi = float(f.min()), float(f.max())
    u8 = np.clip((f - lo) / max(hi - lo, 1e-6) * 255, 0, 255).astype(np.uint8)
    if u8.ndim == 2:
        u8 = np.repeat(u8[..., None], 3, 2)
    return u8, (lo, hi)


def _classic_starless(u8_rgb, ksize: int = 7):
    """Fallback sem IA: abertura morfológica remove pontos < ksize (estrelas), mantém a nebulosa."""
    k = np.ones((ksize, ksize), np.uint8)
    opened = cv2.morphologyEx(u8_rgb, cv2.MORPH_OPEN, k)
    # suaviza a transição para não deixar buracos duros onde havia estrela
    return cv2.medianBlur(opened, 3)


def remove_stars(image, cmd: str = "starnet++", stride: int = 16):
    """Devolve a imagem SEM estrelas (mesma forma/escala). StarNet++ se disponível; senão morfológico.

    image: HxWx3 (ou HxW), uint8 ou float. O StarNet++ opera em TIFF 16-bit."""
    u8, scale = _to_u8_rgb(image)
    exe = starnet_available(cmd)
    starless_u8 = None
    if exe:
        try:
            with tempfile.TemporaryDirectory() as d:
                src, dst = os.path.join(d, "in.tif"), os.path.join(d, "out.tif")
                cv2.imwrite(src, cv2.cvtColor(u8, cv2.COLOR_RGB2BGR))
                subprocess.run([exe, src, dst, str(stride)], capture_output=True, timeout=600)
                if os.path.exists(dst):
                    starless_u8 = cv2.cvtColor(cv2.imread(dst), cv2.COLOR_BGR2RGB)
        except Exception:
            starless_u8 = None
    if starless_u8 is None:
        starless_u8 = _classic_starless(u8)

    if scale is None:                                  # entrada era uint8 -> devolve uint8
        return starless_u8
    lo, hi = scale                                     # entrada era float -> volta à escala original
    out = starless_u8.astype(np.float32) / 255.0 * (hi - lo) + lo
    return out if np.asarray(image).ndim == 3 else out.mean(2)
