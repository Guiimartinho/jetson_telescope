"""T11 — cena com um objeto em MOVIMENTO (satélite/ISS) sobre o campo estelar.

O objeto se move no céu (mundo); a câmera renderiza a janela apontada pela montagem. O laço
de rastreamento (Session.track) move a montagem para manter o objeto centralizado. Fonte de
frames p/ demonstrar a Fase 4 sem hardware. Ver docs/18.
"""
from __future__ import annotations
import numpy as np

from .source import FrameSource
from .sky import SkyModel


class SatelliteScene(FrameSource):
    is_color = False

    def __init__(self, sky: SkyModel, mount, obj0, vel, view_w=1024, view_h=768,
                 obj_flux=45000.0, obj_sigma=1.7, star_sigma=1.4, bg=100.0,
                 read_noise=3.0, seed=13):
        self.sky, self.mount = sky, mount
        self.obj0, self.vel = obj0, vel
        self.vw, self.vh = view_w, view_h
        self.of, self.os = obj_flux, obj_sigma
        self.ss, self.bg, self.rn = star_sigma, bg, read_noise
        self.rng = np.random.default_rng(seed)
        self.t = 0

    def obj_world(self):
        return (self.obj0[0] + self.vel[0] * self.t,
                self.obj0[1] + self.vel[1] * self.t)

    def read(self, out=None):
        cx, cy, rot = self.mount.pointing()
        frame = self.sky.render(cx, cy, rot, self.ss, self.vw, self.vh,
                                self.bg, self.rn, self.rng, out=out)
        ox, oy = self.obj_world()
        sx, sy = ox - cx + self.vw / 2.0, oy - cy + self.vh / 2.0     # posição na tela
        self._plant(frame, sx, sy)
        self.t += 1
        return frame, dict(obj_screen=(sx, sy), obj_world=(ox, oy))

    def _plant(self, img, x, y):
        s = self.os
        r = int(np.ceil(3.5 * s))
        h, w = img.shape
        x0, x1 = max(0, int(x) - r), min(w, int(x) + r + 1)
        y0, y1 = max(0, int(y) - r), min(h, int(y) + r + 1)
        if x1 <= x0 or y1 <= y0:
            return
        gx = np.exp(-((np.arange(x0, x1) - x) ** 2) / (2 * s * s))
        gy = np.exp(-((np.arange(y0, y1) - y) ** 2) / (2 * s * s))
        img[y0:y1, x0:x1] += (self.of / (2 * np.pi * s * s)) * np.outer(gy, gx)
