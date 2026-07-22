"""Portão de qualidade (lucky imaging): detecção de estrelas, FWHM e nitidez.

Rejeita frames borrados (seeing) ou com nuvem ANTES do registro caro, e pondera os
bons pela qualidade (peso ~ 1/FWHM²). Ver docs/03-pipeline-software.md §B.

Métricas rodam sobre a versão NumPy da luminância (poucas estrelas → custo baixo).
A parte pesada por pixel (o acumulador) fica na GPU, em src/gpu/stacker.py.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import cv2

from ..backend import asnumpy

try:                                  # laplaciano na GPU (cupyx)
    import cupyx.scipy.ndimage as _cndi
    from ..backend import xp as _xp, HAS_CUPY as _GPU_LAP
except Exception:
    _GPU_LAP = False


@dataclass
class QualityConfig:
    k_sigma: float = 6.0        # limiar de detecção = mediana + k·sigma_robusto
    max_stars: int = 60
    min_stars: int = 8          # menos que isto (ex.: nuvem) → rejeita
    max_fwhm_px: float = 5.0    # acima disto (ex.: seeing ruim) → rejeita
    fwhm_window: int = 10       # meia-janela p/ medir FWHM (acomoda estrelas gordas)


def laplacian_variance(gray) -> float:
    """Nitidez global barata (variância do Laplaciano). Cai com desfoque/nuvem.
    Usa GPU (cupyx) quando disponível; senão cv2 (CPU)."""
    if _GPU_LAP:
        g = _xp.asarray(gray, dtype=_xp.float32)
        return float(_xp.var(_cndi.laplace(g)))
    g = asnumpy(gray).astype(np.float32)
    return float(cv2.Laplacian(g, cv2.CV_32F, ksize=3).var())


def detect_stars(gray, cfg: QualityConfig):
    """Detecta estrelas via limiar robusto + componentes conexas.
    Retorna (centroides Nx2 em (x,y), fluxos N), ordenados por brilho decrescente."""
    g = asnumpy(gray)
    med = np.median(g)
    mad = np.median(np.abs(g - med)) + 1e-6
    std = 1.4826 * mad                        # sigma robusto (imune a estrelas)
    thr = med + cfg.k_sigma * std
    mask = (g > thr).astype(np.uint8)

    n, _, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
    pts, flux = [], []
    for lbl in range(1, n):                   # 0 = fundo
        if stats[lbl, cv2.CC_STAT_AREA] < 2:
            continue
        x, y = stats[lbl, cv2.CC_STAT_LEFT], stats[lbl, cv2.CC_STAT_TOP]
        w, h = stats[lbl, cv2.CC_STAT_WIDTH], stats[lbl, cv2.CC_STAT_HEIGHT]
        pts.append(centroids[lbl])
        flux.append(float((g[y:y + h, x:x + w] - med).clip(0).sum()))
    if not pts:
        return np.empty((0, 2), np.float32), np.empty((0,), np.float32)
    pts = np.asarray(pts, np.float32)
    flux = np.asarray(flux, np.float32)
    order = np.argsort(flux)[::-1][:cfg.max_stars]
    return pts[order], flux[order]


def measure_fwhm(gray, stars, cfg: QualityConfig, max_use: int = 40) -> float:
    """FWHM mediano (px) pelo método da ÁREA a meia-altura (robusto a ruído).

    Para cada estrela: subtrai o fundo local (anel de borda da janela), suaviza para
    domar picos de ruído, conta os pixels acima de 50% do pico (a região a meia-altura)
    e converte a área nesse diâmetro equivalente: FWHM = 2·√(área/π).
    Muito mais estável que o 2º momento sobre a janela inteira (que inflava com ruído).
    """
    g = asnumpy(gray).astype(np.float32)
    H, W = g.shape
    half = cfg.fwhm_window
    vals = []
    for x, y in stars[:max_use]:
        xi, yi = int(round(x)), int(round(y))
        if xi - half < 0 or xi + half >= W or yi - half < 0 or yi + half >= H:
            continue
        win = g[yi - half:yi + half + 1, xi - half:xi + half + 1]
        border = np.concatenate([win[0, :], win[-1, :], win[1:-1, 0], win[1:-1, -1]])
        sub = cv2.GaussianBlur(win - np.median(border), (3, 3), 0)
        peak = float(sub.max())
        if peak <= 0:
            continue
        area = int((sub > 0.5 * peak).sum())
        if area <= 0:
            continue
        vals.append(2.0 * np.sqrt(area / np.pi))
    return float(np.median(vals)) if vals else float("inf")


def assess(gray, cfg: QualityConfig):
    """Avalia um frame. Retorna dict com aceite/rejeição, métricas e peso p/ o stacker."""
    stars, _ = detect_stars(gray, cfg)
    n = len(stars)
    fwhm = measure_fwhm(gray, stars, cfg) if n >= cfg.min_stars else float("inf")
    sharp = laplacian_variance(gray)
    accepted = (n >= cfg.min_stars) and (fwhm <= cfg.max_fwhm_px)
    weight = 1.0 / (fwhm * fwhm) if accepted else 0.0
    reason = "" if accepted else ("poucas estrelas" if n < cfg.min_stars else "FWHM alto")
    return dict(accepted=accepted, n_stars=n, fwhm=fwhm, sharpness=sharp,
                weight=weight, reason=reason, stars=stars)
