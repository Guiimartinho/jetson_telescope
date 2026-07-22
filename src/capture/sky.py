"""Modelo de céu apontável + câmera — para demonstrar AUTO-FIND e autofoco SEM hardware.

O "céu" é um catálogo fixo de estrelas em coordenadas de MUNDO (px). A câmera renderiza
a janela para onde a montagem aponta (cx,cy,rot), com a PSF dependendo da posição do
focalizador (para o autofoco funcionar). Alvos nomeados (M31/M42/M45) são pequenos
aglomerados brilhantes — quando o alvo está centralizado, aparece no meio do frame.
Ver docs/08-reusar-vs-construir.md §2 (o laço slew→solve→corrige).
"""
from __future__ import annotations
import numpy as np

from .source import FrameSource


class SkyModel:
    def __init__(self, world_w=6000, world_h=4500, n_stars=1300, seed=7):
        rng = np.random.default_rng(seed)
        self.world_w, self.world_h = world_w, world_h
        sx = rng.uniform(0, world_w, n_stars)
        sy = rng.uniform(0, world_h, n_stars)
        flux = 300.0 + 9000.0 * rng.uniform(0, 1, n_stars) ** 3
        # Alvos nomeados = aglomerados brilhantes em posições conhecidas do mundo.
        self.targets = {}
        layout = {"M31": (0.26, 0.30), "M42": (0.70, 0.64), "M45": (0.48, 0.80)}
        ex, ey, ef = [], [], []
        for name, (fx, fy) in layout.items():
            wx, wy = fx * world_w, fy * world_h
            self.targets[name] = (wx, wy)
            ex += list(rng.normal(wx, 22, 14))
            ey += list(rng.normal(wy, 22, 14))
            ef += list(6000.0 + 5000.0 * rng.uniform(0, 1, 14))
        self.sx = np.concatenate([sx, ex])
        self.sy = np.concatenate([sy, ey])
        self.flux = np.concatenate([flux, ef])

    def render(self, cx, cy, rot_deg, sigma, view_w, view_h, bg, read_noise, rng, out=None):
        """Renderiza a janela centrada em (cx,cy) do mundo, rotacionada por rot_deg."""
        if out is None:
            out = np.empty((view_h, view_w), np.float32)
        out.fill(bg)
        th = np.deg2rad(rot_deg)
        cos, sin = np.cos(th), np.sin(th)
        dx, dy = self.sx - cx, self.sy - cy
        vx = cos * dx + sin * dy + view_w / 2.0        # mundo → coords da janela
        vy = -sin * dx + cos * dy + view_h / 2.0
        m = (vx > -8) & (vx < view_w + 8) & (vy > -8) & (vy < view_h + 8)
        r = int(np.ceil(3.5 * sigma))
        norm = self.flux[m] / (2.0 * np.pi * sigma * sigma)
        for x, y, f in zip(vx[m], vy[m], norm):
            x0, x1 = max(0, int(x) - r), min(view_w, int(x) + r + 1)
            y0, y1 = max(0, int(y) - r), min(view_h, int(y) + r + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            gx = np.exp(-((np.arange(x0, x1) - x) ** 2) / (2 * sigma * sigma))
            gy = np.exp(-((np.arange(y0, y1) - y) ** 2) / (2 * sigma * sigma))
            out[y0:y1, x0:x1] += f * np.outer(gy, gx)
        np.clip(out, 0, None, out=out)
        out[:] = rng.poisson(out).astype(np.float32)
        out += rng.normal(0.0, read_noise, out.shape).astype(np.float32)
        return out


class SkyCameraSource(FrameSource):
    """Câmera apontável: renderiza para onde a montagem aponta, com foco variável."""
    is_color = False

    def __init__(self, sky: SkyModel, mount, focuser=None, view_w=1024, view_h=768,
                 base_sigma=1.4, focus_k=6.0, focus_span=6000.0, bg=100.0,
                 read_noise=3.0, bad_frac=0.12, blur_sigma=3.6, seed=11):
        self.sky, self.mount, self.focuser = sky, mount, focuser
        self.vw, self.vh = view_w, view_h
        self.base, self.k, self.span = base_sigma, focus_k, focus_span
        self.bg, self.rn = bg, read_noise
        self.bad, self.blur = bad_frac, blur_sigma
        self.rng = np.random.default_rng(seed)

    def _sigma(self):
        if self.focuser is None:
            return self.base
        return self.base + self.k * abs(self.focuser.position() - self.focuser.best) / self.span

    def read(self, out=None):
        if hasattr(self.mount, "tick"):
            self.mount.tick()                          # deriva de tracking (1×/frame)
        cx, cy, rot = self.mount.pointing()
        sigma, kind = self._sigma(), "good"
        if self.rng.uniform() < self.bad:
            if self.rng.uniform() < 0.5:
                sigma, kind = max(sigma, self.blur), "blur"
            else:
                kind = "cloud"
        bg = self.bg * (4.0 if kind == "cloud" else 1.0)
        frame = self.sky.render(cx, cy, rot, sigma, self.vw, self.vh, bg, self.rn,
                                self.rng, out=out)
        return frame, dict(kind=kind, pointing=(cx, cy, rot))
