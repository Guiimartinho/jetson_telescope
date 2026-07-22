"""Lucky imaging — mede a nitidez de cada frame e fica com os melhores.

A atmosfera (seeing) muda a cada instante: alguns frames saem nítidos, a maioria borrada.
Graduamos cada frame pela variância do Laplaciano (nitidez global — reusa `gpu/quality`) e
ficamos com os top N% mais nítidos. Frames mais nítidos também PESAM mais no empilhamento.
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy
from ..gpu.quality import laplacian_variance


def sharpness(frame, presmooth: float = 1.0) -> float:
    """Nitidez de um frame (variância do Laplaciano). Mono ou cor (usa a luminância).

    `presmooth` (sigma) borra de leve ANTES de medir: sem isso, com ruído forte a métrica
    seleciona os frames mais RUIDOSOS (o ruído infla o Laplaciano), não os mais nítidos —
    então mediríamos ruído, não detalhe. Suavizar mata o ruído e deixa a ESTRUTURA (bandas,
    crateras) dominar a métrica. É o que AutoStakkert! faz. presmooth=0 desliga."""
    a = asnumpy(frame)
    g = a.mean(2) if a.ndim == 3 else a
    g = g.astype(np.float32)
    if presmooth > 0:
        g = cv2.GaussianBlur(g, (0, 0), presmooth)
    return laplacian_variance(g)


def grade(frames) -> np.ndarray:
    """Vetor de nitidez (um valor por frame), na ordem de entrada."""
    return np.array([sharpness(f) for f in frames], dtype=np.float64)


def select_best(scores, keep: float = 0.3, min_keep: int = 1) -> np.ndarray:
    """Índices dos top `keep` (fração 0..1) frames mais nítidos, em ordem crescente de índice.

    `keep`=0.3 → melhores 30%. Garante ao menos `min_keep`. Índices ordenados p/ leitura estável."""
    scores = np.asarray(scores, dtype=np.float64)
    n = len(scores)
    if n == 0:
        return np.empty((0,), dtype=int)
    k = int(round(n * float(keep)))
    k = max(min_keep, min(n, k))
    best = np.argsort(scores)[::-1][:k]        # mais nítidos primeiro
    return np.sort(best)
