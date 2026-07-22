"""Fonte de frames a partir de uma FOTO ASTRONÔMICA REAL (T15/T16 — tornar o dado real VISÍVEL).

Carrega um FITS real (ex.: o campo de M67) e, a cada `read()`, devolve uma "sub" realista: a mesma
cena com **deriva de tracking** (translação+rotação pequenas) e **ruído de leitura** — exatamente o
que a câmera entregaria. Assim o pipeline (registro por estrelas reais → lucky imaging → empilhamento)
roda sobre DADOS REAIS ao vivo no painel, não sobre o céu sintético. Ver docs/21.
"""
from __future__ import annotations
import numpy as np

from .source import FrameSource


class RealFitsSource(FrameSource):
    is_color = False
    bayer = "RGGB"

    def __init__(self, path, view_w=1024, view_h=768, drift_px=2.2, jitter_px=0.5,
                 read_noise=45.0, seed=1):
        from astropy.io import fits
        with fits.open(path) as h:
            base = np.asarray(h[0].data, dtype=np.float32)
        self.bg = float(np.median(base))
        # encaixa a imagem real (centrada) num canvas do tamanho do pipeline; resto = fundo do céu
        canvas = np.full((view_h, view_w), self.bg, np.float32)
        bh, bw = base.shape
        oy, ox = max(0, (view_h - bh) // 2), max(0, (view_w - bw) // 2)
        ey, ex = min(view_h, oy + bh), min(view_w, ox + bw)
        canvas[oy:ey, ox:ex] = base[:ey - oy, :ex - ox]
        self.canvas = canvas
        self.view_w, self.view_h = view_w, view_h
        self.drift, self.jitter, self.noise = drift_px, jitter_px, read_noise
        self.rng = np.random.default_rng(seed)
        self.i = 0

    def read(self, out=None):
        import cv2
        # deriva acumulada (tracking imperfeito) + jitter/rotação aleatórios por frame
        dx = self.drift * self.i * 0.12 + self.rng.normal(0, self.jitter)
        dy = -self.drift * self.i * 0.08 + self.rng.normal(0, self.jitter)
        ang = 0.015 * self.i + self.rng.normal(0, 0.02)
        M = cv2.getRotationMatrix2D((self.view_w / 2, self.view_h / 2), ang, 1.0)
        M[0, 2] += dx
        M[1, 2] += dy
        frame = cv2.warpAffine(self.canvas, M, (self.view_w, self.view_h),
                               flags=cv2.INTER_LINEAR, borderValue=self.bg)
        frame = frame + self.rng.normal(0.0, self.noise, frame.shape).astype(np.float32)
        self.i += 1
        if out is not None and out.shape == frame.shape:
            out[...] = frame
            frame = out
        return frame, dict(kind="real", frame=self.i)
