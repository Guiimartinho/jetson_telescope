"""Aguçamento por WAVELETS à trous (starlet) — a técnica-rei do planetário.

Decompõe a imagem em camadas de detalhe por ESCALA (fina → grossa) e permite realçar cada
escala com um peso. É o que Registax/AstroSurface fazem para "revelar" as bandas de Júpiter,
crateras da Lua e detalhe atmosférico de Marte. Roda em GPU (ndimage do cupyx na Jetson).

à trous ("com buracos"): a cada nível i, suaviza com o kernel B3-spline DILATADO por 2^i; o
detalhe da escala i é (nível anterior − suavizado). Reconstrução = Σ detalhes + resíduo.
Com todos os pesos = 1 a reconstrução é EXATA (invariante testado). Pesos > 1 realçam a escala.
"""
from __future__ import annotations
import numpy as np

from ..backend import xp, to_device, asnumpy, HAS_CUPY

if HAS_CUPY:
    import cupyx.scipy.ndimage as _ndi
else:
    import scipy.ndimage as _ndi

_B3 = np.array([1, 4, 6, 4, 1], np.float32) / 16.0     # B3-spline (starlet)

# Pesos padrão por escala (fina→grossa): escala 0 (mais fina = ruído) segurada baixa;
# escalas médias (detalhe planetário real) realçadas; escala grossa neutra.
DEFAULT_WEIGHTS = (0.5, 1.6, 2.0, 1.5, 1.0)


def _dilated_kernel(step: int):
    """Kernel B3 com (step-1) zeros entre as taps → convolução 'à trous' na escala `step`."""
    if step == 1:
        return xp.asarray(_B3)
    k = xp.zeros((len(_B3) - 1) * step + 1, dtype=xp.float32)
    k[::step] = xp.asarray(_B3)
    return k


def _smooth(c, step):
    """Suavização separável (linhas e colunas) com o kernel dilatado, bordas espelhadas."""
    k = _dilated_kernel(step)
    c = _ndi.convolve1d(c, k, axis=0, mode="reflect")
    c = _ndi.convolve1d(c, k, axis=1, mode="reflect")
    return c


def atrous(plane, n_layers: int):
    """Transformada starlet de um plano 2D → (lista de detalhes por escala, resíduo).

    Devolve arrays no device (`xp`); use `backend.asnumpy` p/ trazer ao host."""
    c = to_device(plane).astype(xp.float32)
    details = []
    for i in range(n_layers):
        smooth = _smooth(c, 1 << i)          # dilatação 2^i
        details.append(c - smooth)
        c = smooth
    return details, c


def _sharpen_plane(plane, weights):
    details, residual = atrous(plane, len(weights))
    out = residual
    for wgt, d in zip(weights, details):
        out = out + xp.float32(wgt) * d
    return out


def wavelet_sharpen(image, weights=DEFAULT_WEIGHTS, clip: bool = True):
    """Aguça `image` (mono ou cor) realçando as escalas de wavelet. Preserva dtype de entrada.

    weights: peso por escala, da mais FINA à mais grossa. len(weights) = nº de escalas.
    clip: satura ao intervalo válido (evita estouro)."""
    arr = np.asarray(image)
    a = to_device(arr).astype(xp.float32)
    if a.ndim == 3:
        planes = [_sharpen_plane(a[..., c], weights) for c in range(a.shape[2])]
        out = xp.stack(planes, axis=-1)
    else:
        out = _sharpen_plane(a, weights)
    if clip:
        hi = 255.0 if float(arr.max() if arr.size else 0) <= 255.0 else float(arr.max())
        out = xp.clip(out, 0.0, hi)
    return asnumpy(out).astype(arr.dtype)
