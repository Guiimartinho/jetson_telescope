"""Stretch (esticamento não-linear) e gravação de imagem.

O RAW/integrado é linear e quase todo preto: a estrutura fraca só aparece com um
stretch não-linear (é onde a nebulosa "surge"). Usa recorte por percentil + asinh.
Ver docs/06-aceleracao-e-tecnicas.md §A (técnica #8).
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy


def autostretch(img, black_pct: float = 30.0, white_pct: float = 99.6,
                asinh_strength: float = 12.0) -> np.ndarray:
    """Converte imagem linear (float) em 8-bit visível, realçando o sinal fraco."""
    g = asnumpy(img).astype(np.float32)
    lo = np.percentile(g, black_pct)
    hi = np.percentile(g, white_pct)
    x = np.clip((g - lo) / max(hi - lo, 1e-6), 0.0, 1.0)
    if asinh_strength > 0:
        x = np.arcsinh(x * asinh_strength) / np.arcsinh(asinh_strength)
    return (x * 255.0).astype(np.uint8)


def save_png(path: str, img, stretch: bool = True) -> None:
    out = autostretch(img) if stretch else asnumpy(img).astype(np.uint8)
    cv2.imwrite(path, out)


def robust_std(img) -> float:
    """Ruído de fundo robusto (MAD->sigma). Métrica limpa para medir o ganho de SNR."""
    g = asnumpy(img).ravel()
    med = np.median(g)
    return float(1.4826 * np.median(np.abs(g - med)))


def encode_jpeg(img, stretch: bool = True, quality: int = 85) -> bytes:
    """Imagem linear (mono ou RGB) → JPEG esticado, pronto para o live view web."""
    out = autostretch(img) if stretch else asnumpy(img).astype(np.uint8)
    if out.ndim == 3:                       # RGB -> BGR (convenção do OpenCV)
        out = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""
