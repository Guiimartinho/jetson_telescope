"""Simulador de campo estelar — permite desenvolver TODO o pipeline SEM câmera.

Gera frames mono float32 realistas, com os mesmos defeitos do céu real, para que o
portão de qualidade (FWHM) e o registro sejam exercitados de verdade:

  - N estrelas em posições subpixel, PSF gaussiana (sigma controla o FWHM/seeing)
  - ruído de fóton (Poisson) + ruído de leitura (gaussiano)
  - deriva (translação) e leve rotação de campo por frame (montagem imperfeita)
  - frames "ruins" ocasionais:
        * seeing ruim  -> PSF borrada (sigma grande)  -> alto FWHM -> rejeitado
        * nuvem        -> queda de sinal + fundo alto  -> poucas estrelas -> rejeitado

O objetivo pedagógico: ver o live stacking melhorar o SNR (~raiz(N)) e a rejeição de
frames funcionando na bancada, no seu Orin Nano Super, antes de gastar com câmera.
Ver docs/03-pipeline-software.md e docs/06-aceleracao-e-tecnicas.md.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np


@dataclass
class SimConfig:
    width: int = 1600
    height: int = 1200
    n_stars: int = 60
    seed: int = 42
    background: float = 100.0        # nível de fundo do céu (ADU)
    read_noise: float = 3.0          # ruído de leitura (ADU rms)
    psf_sigma: float = 1.4           # sigma da PSF em frames bons (FWHM ~ 3.3 px)
    psf_jitter: float = 0.25         # variação de seeing frame-a-frame (realismo)
    drift_px_per_frame: float = 0.06 # deriva lenta da montagem (px/frame, por eixo)
    rot_deg_per_frame: float = 0.01  # rotação de campo por frame (montagem altaz)
    jitter_px: float = 0.15          # tremor aleatório por frame
    bad_frac: float = 0.15           # fração de frames ruins
    blur_sigma: float = 3.6          # PSF de um frame de seeing ruim (FWHM ~ 8.5 px)
    cloud_signal: float = 0.15       # multiplicador de sinal num frame com nuvem
    cloud_bg_boost: float = 4.0      # aumento de fundo num frame com nuvem
    # --- artefatos calibráveis (padrão OFF; ligados p/ testar/demonstrar calibração) ---
    bias: float = 0.0                # offset de bias (ADU) — removido por dark/bias
    dark_current: float = 0.0        # corrente de escuro (ADU/frame) — removida por dark
    hot_pixel_frac: float = 0.0      # fração de pixels quentes — removidos por dark
    hot_pixel_level: float = 8000.0  # amplitude dos pixels quentes
    vignette: float = 0.0            # queda radial (0=sem; 0.4=cantos a ~60%) — corrigida por flat
    flat_level: float = 20000.0      # nível de iluminação do frame de flat


class StarFieldSimulator:
    """Fonte de frames sintéticos. Interface espelha uma câmera: `frame(i)`."""

    def __init__(self, cfg: SimConfig | None = None):
        self.cfg = cfg or SimConfig()
        c = self.cfg
        self.rng = np.random.default_rng(c.seed)
        # Catálogo de estrelas no referencial (frame 0): posições + fluxos.
        margin = 40
        self.x0 = self.rng.uniform(margin, c.width - margin, c.n_stars)
        self.y0 = self.rng.uniform(margin, c.height - margin, c.n_stars)
        # Distribuição de brilho tipo lei de potência: poucas brilhantes, muitas fracas.
        u = self.rng.uniform(0, 1, c.n_stars)
        self.flux = 400.0 + 12000.0 * (u ** 3)   # ADU integrados por estrela
        self.cx, self.cy = c.width / 2.0, c.height / 2.0

        # --- artefatos fixos do sensor (consistentes entre light e frames de calibração) ---
        self._vmap = None                        # mapa de vinheta (multiplicativo)
        if c.vignette > 0:
            yy, xx = np.mgrid[0:c.height, 0:c.width]
            r = np.sqrt((xx - self.cx) ** 2 + (yy - self.cy) ** 2)
            rmax = np.sqrt(self.cx ** 2 + self.cy ** 2)
            self._vmap = (1.0 - c.vignette * (r / rmax) ** 2).astype(np.float32)
        self._hot = None                         # mapa aditivo de pixels quentes
        if c.hot_pixel_frac > 0:
            self._hot = np.zeros((c.height, c.width), np.float32)
            n_hot = max(1, int(c.hot_pixel_frac * c.height * c.width))
            hy = self.rng.integers(0, c.height, n_hot)
            hx = self.rng.integers(0, c.width, n_hot)
            self._hot[hy, hx] = c.hot_pixel_level * self.rng.uniform(0.5, 1.0, n_hot)

    # -- geometria: para onde as estrelas vão no frame i (deriva + rotação) -----
    def _positions(self, i: int):
        c = self.cfg
        theta = np.deg2rad(c.rot_deg_per_frame * i)
        dx = c.drift_px_per_frame * i + self.rng.normal(0, c.jitter_px)
        dy = 0.5 * c.drift_px_per_frame * i + self.rng.normal(0, c.jitter_px)
        cos, sin = np.cos(theta), np.sin(theta)
        xr = cos * (self.x0 - self.cx) - sin * (self.y0 - self.cy) + self.cx + dx
        yr = sin * (self.x0 - self.cx) + cos * (self.y0 - self.cy) + self.cy + dy
        return xr, yr, (dx, dy, np.rad2deg(theta))

    # -- render de uma PSF gaussiana por estrela, em janelas locais (barato) ----
    def _render(self, xs, ys, flux, sigma, background, out):
        c = self.cfg
        out.fill(background)
        H, W = out.shape
        r = int(np.ceil(3.5 * sigma))
        norm = flux / (2.0 * np.pi * sigma * sigma)   # normaliza o pico da gaussiana
        for x, y, f in zip(xs, ys, norm):
            x0, x1 = max(0, int(x) - r), min(W, int(x) + r + 1)
            y0, y1 = max(0, int(y) - r), min(H, int(y) + r + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            gx = np.exp(-((np.arange(x0, x1) - x) ** 2) / (2 * sigma * sigma))
            gy = np.exp(-((np.arange(y0, y1) - y) ** 2) / (2 * sigma * sigma))
            out[y0:y1, x0:x1] += f * np.outer(gy, gx)
        return out

    def frame(self, i: int, out: np.ndarray | None = None):
        """Gera o frame i. Retorna (img_float32, meta).

        `out`: buffer pré-alocado opcional (padrão do ring buffer, evita alocar).
        """
        c = self.cfg
        if out is None:
            out = np.empty((c.height, c.width), np.float32)

        xs, ys, geom = self._positions(i)

        # Decide se este frame é "ruim" (e de que tipo).
        kind = "good"
        sigma = max(0.6, c.psf_sigma + self.rng.normal(0, c.psf_jitter))
        flux = self.flux.copy()
        bg = c.background
        if self.rng.uniform() < c.bad_frac:
            if self.rng.uniform() < 0.5:
                kind, sigma = "blur", c.blur_sigma      # seeing ruim
            else:
                kind = "cloud"                           # nuvem
                flux = flux * c.cloud_signal
                bg = c.background * c.cloud_bg_boost

        self._render(xs, ys, flux, sigma, bg, out)   # sky + estrelas (elétrons)

        # Vinheta (multiplica o sinal de luz) + corrente de escuro (antes do Poisson).
        if self._vmap is not None:
            out *= self._vmap
        if c.dark_current > 0:
            out += c.dark_current
        np.clip(out, 0, None, out=out)
        out[:] = self.rng.poisson(out).astype(np.float32)

        # Pixels quentes + bias (defeitos/offset, após o Poisson) + ruído de leitura.
        if self._hot is not None:
            out += self._hot
        if c.bias > 0:
            out += c.bias
        out += self.rng.normal(0.0, c.read_noise, out.shape).astype(np.float32)

        meta = dict(kind=kind, sigma=float(sigma), drift=geom[:2], rot_deg=geom[2])
        return out, meta

    # ----- frames de calibração (mesmos artefatos fixos do sensor) -------------
    def _blank(self):
        return np.zeros((self.cfg.height, self.cfg.width), np.float32)

    def bias_frame(self):
        """Exposição ~zero: só bias + ruído de leitura."""
        f = self._blank()
        f += self.cfg.bias
        f += self.rng.normal(0.0, self.cfg.read_noise, f.shape).astype(np.float32)
        return f

    def dark_frame(self):
        """Obturador fechado: bias + corrente de escuro + pixels quentes (sem luz/vinheta)."""
        f = self._blank()
        if self.cfg.dark_current > 0:
            f += self.cfg.dark_current
        f[:] = self.rng.poisson(np.clip(f, 0, None)).astype(np.float32)
        if self._hot is not None:
            f += self._hot
        f += self.cfg.bias
        f += self.rng.normal(0.0, self.cfg.read_noise, f.shape).astype(np.float32)
        return f

    def flat_frame(self):
        """Campo uniforme: iluminação constante × vinheta + bias (sem estrelas)."""
        f = np.full((self.cfg.height, self.cfg.width), self.cfg.flat_level, np.float32)
        if self._vmap is not None:
            f *= self._vmap
        f[:] = self.rng.poisson(np.clip(f, 0, None)).astype(np.float32)
        f += self.cfg.bias
        f += self.rng.normal(0.0, self.cfg.read_noise, f.shape).astype(np.float32)
        return f
