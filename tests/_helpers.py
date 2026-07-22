"""Utilitários compartilhados pelos testes: plantar estrelas sintéticas."""
from __future__ import annotations
import numpy as np


def plant_star(img, x, y, flux=5000.0, sigma=1.4):
    """Adiciona uma estrela (PSF gaussiana) em (x,y) na imagem, in-place."""
    h, w = img.shape
    r = int(np.ceil(3.5 * sigma))
    x0, x1 = max(0, int(x) - r), min(w, int(x) + r + 1)
    y0, y1 = max(0, int(y) - r), min(h, int(y) + r + 1)
    if x1 <= x0 or y1 <= y0:
        return img
    gx = np.exp(-((np.arange(x0, x1) - x) ** 2) / (2 * sigma * sigma))
    gy = np.exp(-((np.arange(y0, y1) - y) ** 2) / (2 * sigma * sigma))
    img[y0:y1, x0:x1] += (flux / (2 * np.pi * sigma * sigma)) * np.outer(gy, gx)
    return img


def star_field(w=400, h=300, n=20, flux=5000.0, sigma=1.4, bg=100.0, noise=0.0, seed=0):
    """Campo estelar sintético + posições verdadeiras (Nx2)."""
    rng = np.random.default_rng(seed)
    img = np.full((h, w), bg, np.float32)
    pos = rng.uniform([30, 30], [w - 30, h - 30], size=(n, 2))
    for x, y in pos:
        plant_star(img, x, y, flux, sigma)
    if noise > 0:
        img += rng.normal(0, noise, img.shape).astype(np.float32)
    return img, pos.astype(np.float32)
