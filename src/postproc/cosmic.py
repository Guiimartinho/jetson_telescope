"""Remoção de raios cósmicos e pixels quentes — REUSO do astroscrappy (L.A.Cosmic), fallback próprio.

O astroscrappy é o padrão maduro da área (algoritmo L.A.Cosmic de van Dokkum) para detectar e limpar
spikes (raios cósmicos, hot/cold pixels) sem tocar nas estrelas. Sem darks, isto evita o "walking
noise" (docs/27) de forma bem mais robusta que a mediana simples. Se o astroscrappy não estiver
instalado, cai no nosso método de mediana local (`gpu.calibration.remove_hot_pixels`). Ver docs/29.
"""
from __future__ import annotations
import numpy as np

from ..gpu.calibration import remove_hot_pixels

try:
    import astroscrappy
    HAS_ASTROSCRAPPY = True
except Exception:
    HAS_ASTROSCRAPPY = False


def astroscrappy_available() -> bool:
    return HAS_ASTROSCRAPPY


def clean_cosmics(raw, sigclip: float = 5.0, objlim: float = 8.0, gain: float = 1.0,
                  readnoise: float = 6.5, prefer_astroscrappy: bool = True):
    """Devolve o frame limpo (float32). Usa L.A.Cosmic (astroscrappy) se disponível; senão a
    mediana local. Parâmetros conservadores (sigclip/objlim altos) para PRESERVAR estrelas.

    Trabalha em 2D (RAW Bayer ou mono). `objlim` alto protege objetos reais (estrelas) de serem
    confundidos com raios cósmicos."""
    a = np.asarray(raw, dtype=np.float32)
    if prefer_astroscrappy and HAS_ASTROSCRAPPY:
        try:
            _mask, cleaned = astroscrappy.detect_cosmics(
                a, sigclip=sigclip, sigfrac=0.3, objlim=objlim, gain=gain,
                readnoise=readnoise, cleantype="medmask", verbose=False)
            return np.asarray(cleaned, dtype=np.float32)
        except Exception:
            pass                                       # qualquer erro -> fallback robusto
    return remove_hot_pixels(a)
