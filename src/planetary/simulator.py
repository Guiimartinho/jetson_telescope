"""Simulador de planeta/Lua — desenvolve o pipeline lucky-imaging sem câmera.

Gera um disco (com escurecimento de bordo + feições de superfície e textura fina fixa) e, a
cada frame, aplica: deslocamento sub-pixel aleatório (tremor de montagem/atmosfera), borramento
gaussiano variável (seeing — uns frames saem nítidos, a maioria borrada) e ruído. Isso exercita
os três filtros: seleção (achar os nítidos), alinhamento (desfazer o tremor) e stack (baixar ruído).
"""
from __future__ import annotations
import numpy as np
import scipy.ndimage as ndi


class PlanetSimulator:
    def __init__(self, size: int = 160, radius: int = 52, kind: str = "jupiter",
                 seed: int = 0, jitter: float = 6.0, seeing=(0.6, 3.2),
                 noise: float = 2.0, color: bool = False):
        self.size, self.radius = size, radius
        self.jitter, self.seeing, self.noise = jitter, seeing, noise
        self.color = color
        self.rng = np.random.default_rng(seed)
        self.template = self._make_template(kind, seed)

    def _make_template(self, kind, seed):
        n = self.size
        yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
        cy = cx = n / 2.0
        r = np.hypot(yy - cy, xx - cx)
        disk = (r <= self.radius).astype(np.float32)
        limb = np.clip(1.0 - (r / self.radius) ** 2, 0, 1) ** 0.4      # bordo escurece
        img = disk * (0.45 + 0.55 * limb) * 190.0
        rng = np.random.default_rng(seed + 1)
        if kind == "jupiter":
            for _ in range(5):                                        # bandas horizontais
                yb = rng.uniform(cy - self.radius * 0.7, cy + self.radius * 0.7)
                wb = rng.uniform(3, 8)
                img -= disk * np.exp(-((yy - yb) ** 2) / (2 * wb ** 2)) * rng.uniform(20, 50)
            img += disk * np.exp(-(((yy - (cy + 10)) ** 2 + (xx - (cx + 18)) ** 2)
                                   / (2 * 7.0 ** 2))) * 45            # Grande Mancha
        else:                                                         # Lua/Mercúrio: crateras
            for _ in range(26):
                yb, xb, rc = rng.uniform(0, n), rng.uniform(0, n), rng.uniform(2, 7)
                img -= disk * np.exp(-(((yy - yb) ** 2 + (xx - xb) ** 2)
                                       / (2 * rc ** 2))) * rng.uniform(15, 45)
        img += disk * rng.normal(0, 6, (n, n)).astype(np.float32)     # textura fina FIXA
        return np.clip(img, 0, 255).astype(np.float32)

    def _tint(self, mono):
        """Mono → cor (HxWx3) com um leve matiz quente (Júpiter/Marte)."""
        return np.stack([mono * 1.0, mono * 0.85, mono * 0.7], axis=-1).astype(np.float32)

    def frame(self, i: int | None = None):
        """Um frame degradado + meta (shift real e sigma do seeing aplicados)."""
        dy = float(self.rng.uniform(-self.jitter, self.jitter))
        dx = float(self.rng.uniform(-self.jitter, self.jitter))
        sigma = float(self.rng.uniform(*self.seeing))
        f = ndi.shift(self.template, (dy, dx), order=1, mode="constant", cval=0.0)
        f = ndi.gaussian_filter(f, sigma)
        f = f + self.rng.normal(0, self.noise, f.shape)
        f = np.clip(f, 0, 255).astype(np.float32)
        if self.color:
            f = self._tint(f)
        return f, {"shift": (dy, dx), "sigma": sigma}

    def frames(self, n: int):
        """Lista de `n` frames (só as imagens)."""
        return [self.frame(i)[0] for i in range(n)]
