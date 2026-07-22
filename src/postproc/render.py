"""Motor de RENDER de produto — transforma o stack LINEAR (float32) numa imagem bonita,
com dezenas de controles ajustáveis ao vivo (o "one-click optimization" da DWARF, mas aberto).

Opera sempre sobre os dados LINEARES (não sobre JPG) → preserva dynamic range. Cada controle é um
passo do pipeline de realce: gradiente → fundo neutro → balanço de cor → stretch asinh → gamma →
redução de estrela → nitidez → denoise de croma → saturação. Rápido (cv2) para ajuste interativo.
Na Jetson, os passos pesados (denoise/deconv) migram para cuCIM/GraXpert→TensorRT. Ver docs/24.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np
import cv2

from .enhance import remove_gradient
from .deconv import deconvolve_rgb, denoise_luminance


@dataclass
class RenderParams:
    black: float = 0.0           # ponto preto (0-1) — corta o fundo
    stretch: float = 10.0        # força do asinh (1-30) — realça o fraco
    white: float = 99.7          # ponto branco (percentil) — 99-100
    gamma: float = 1.0           # 0.5-2.5
    saturation: float = 1.8      # 0-3 (a cor correta de OSC é sutil; precisa de saturação)
    scnr: float = 1.0            # 0-1 — remove o green cast do sensor OSC (SCNR — T18)
    r_gain: float = 1.1          # trim de cor manual — leve Hα (vermelho) por padrão
    g_gain: float = 1.0
    b_gain: float = 1.0
    bg_percentile: float = 30.0  # percentil do céu por canal (neutraliza o fundo sem comer a nebulosa)
    remove_grad: bool = False    # extração de gradiente OFF por padrão (não comer a nebulosa difusa)
    denoise: float = 0.35        # 0-1 — denoise de croma (tira ruído de cor)
    ldenoise: float = 0.0        # 0-1 — denoise de luminância (bilateral; IA/GraXpert na Jetson)
    star_reduce: float = 0.0     # 0-1 — encolhe estrelas (destaca a nebulosa)
    sharpen: float = 0.12        # 0-1 — nitidez (unsharp / deconv-lite)
    deconv: float = 0.0          # 0-25 — deconvolução Richardson-Lucy (recupera detalhe — T19)

    @staticmethod
    def from_query(q: dict) -> "RenderParams":
        p = RenderParams()
        for k, v in q.items():
            if not hasattr(p, k):
                continue
            cur = getattr(p, k)
            try:
                setattr(p, k, (str(v).lower() in ("1", "true", "on")) if isinstance(cur, bool)
                        else type(cur)(v))
            except (ValueError, TypeError):
                pass
        return p

    def as_dict(self):
        return asdict(self)


def render(linear, p: RenderParams | None = None, max_side: int | None = None) -> np.ndarray:
    """linear: stack HxWx3 float32 (linear). Retorna RGB uint8 pronto para exibir.

    Pipeline de cor correto para OSC (T18): fundo neutro (percentil do céu por canal) → SCNR
    (remove o green cast) → trim manual R/G/B. O debayer correto (src/gpu/debayer) já evita o
    artefato de cor na captura."""
    p = p or RenderParams()
    img = np.asarray(linear, dtype=np.float32)
    if img.ndim == 2:
        img = np.repeat(img[..., None], 3, axis=2)
    img = img.copy()

    if max_side:                                   # preview mais leve p/ ajuste interativo
        h, w = img.shape[:2]
        s = max_side / max(h, w)
        if s < 1.0:
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)

    if p.remove_grad:                              # 1) remove gradiente (GENTIL: só o gradiente
        for c in range(3):                         #    de céu muito suave, sem comer a nebulosa)
            img[..., c] = remove_gradient(img[..., c], downscale=32, sigma=6.0)

    for c in range(3):                             # 2) fundo do céu -> neutro (percentil BAIXO por
        sky = np.percentile(img[..., c], p.bg_percentile)   #    canal — não come a nebulosa difusa)
        img[..., c] = np.clip(img[..., c] - sky, 0, None)

    if p.scnr > 0:                                 # 3) SCNR: remove o excesso de verde do OSC
        neutral = (img[..., 0] + img[..., 2]) * 0.5
        img[..., 1] -= p.scnr * np.clip(img[..., 1] - neutral, 0, None)

    img[..., 0] *= p.r_gain                        # 4) trim de cor manual (leve Hα por padrão)
    img[..., 1] *= p.g_gain
    img[..., 2] *= p.b_gain

    if p.deconv > 0:                               # 5) deconvolução R-L na luminância (T19)
        img = deconvolve_rgb(img, iterations=int(round(p.deconv)), sigma=1.5)

    hi = np.percentile(img, p.white) + 1e-6        # 6) normaliza + ponto preto + asinh
    x = np.clip(img / hi, 0, None)
    x = np.clip((x - p.black) / (1.0 - p.black + 1e-6), 0, None)
    out = np.arcsinh(p.stretch * x) / np.arcsinh(p.stretch)
    out = np.clip(out, 0, 1)
    if abs(p.gamma - 1.0) > 1e-3:
        out = np.power(out, 1.0 / max(p.gamma, 1e-3))

    u8 = (out * 255).astype(np.uint8)              # RGB 8-bit
    if p.star_reduce > 0:                          # 5) reduz estrelas (morfologia leve)
        opened = cv2.morphologyEx(u8, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        u8 = cv2.addWeighted(u8, 1 - p.star_reduce, opened, p.star_reduce, 0)
    if p.sharpen > 0:                              # 7) nitidez (unsharp mask)
        blur = cv2.GaussianBlur(u8, (0, 0), 1.6)
        u8 = cv2.addWeighted(u8, 1 + p.sharpen, blur, -p.sharpen, 0)
    if p.ldenoise > 0:                             # 8) denoise de luminância (bilateral; IA na Jetson)
        u8 = denoise_luminance(u8, p.ldenoise)

    lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB).astype(np.float32)   # 7) croma: denoise + saturação
    if p.denoise > 0:
        k = int(3 + p.denoise * 8) | 1
        lab[..., 1] = cv2.GaussianBlur(lab[..., 1], (k, k), 0)
        lab[..., 2] = cv2.GaussianBlur(lab[..., 2], (k, k), 0)
    if abs(p.saturation - 1.0) > 1e-3:
        lab[..., 1] = np.clip((lab[..., 1] - 128) * p.saturation + 128, 0, 255)
        lab[..., 2] = np.clip((lab[..., 2] - 128) * p.saturation + 128, 0, 255)
    return cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)


# presets de "1 clique" (como o app da DWARF, mas ajustáveis)
PRESETS = {
    "natural":    RenderParams(),
    "vivido":     RenderParams(stretch=13.0, saturation=2.3, sharpen=0.28, denoise=0.45),
    "H-alpha":    RenderParams(stretch=14.0, saturation=2.6, r_gain=1.45, b_gain=0.95,
                               sharpen=0.2, denoise=0.5),   # realça o vermelho da emissão
    "nebulosa":   RenderParams(stretch=15.0, saturation=2.7, star_reduce=0.35, r_gain=1.2, denoise=0.5),
    "suave":      RenderParams(stretch=8.0, saturation=1.5, sharpen=0.05, denoise=0.6, black=0.02),
}
