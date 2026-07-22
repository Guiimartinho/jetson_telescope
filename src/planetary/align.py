"""Alinhamento por CORRELAÇÃO DE FASE (superfície) — Lua e planetas.

Céu profundo alinha por estrelas (`gpu/registration`); Lua/planetas não têm estrelas no campo,
então alinhamos pela própria superfície. A correlação de fase acha o deslocamento (dy,dx) entre
dois frames via FFT — barato, robusto a diferença de brilho e 100% GPU (`xp.fft` = CuPy na Jetson).

Convenção: `estimate_shift(ref, frame)` devolve (dy,dx) tal que `frame` está deslocado de `ref`
por (+dy,+dx) — i.e. frame(r,c) ≈ ref(r-dy, c-dx). `align_to(frame, ref)` desfaz isso (desloca o
frame por -dy,-dx) e devolve (aligned, mask). Deslocamento subpixel por ajuste parabólico do pico.
"""
from __future__ import annotations
import numpy as np

from ..backend import xp, to_device, asnumpy, HAS_CUPY

if HAS_CUPY:                              # ndimage na GPU (deslocamento subpixel)
    import cupyx.scipy.ndimage as _ndi
else:
    import scipy.ndimage as _ndi


def _lum(a):
    """Luminância float32 no device (mono passa direto; cor vira média dos canais)."""
    a = to_device(a).astype(xp.float32)
    return a.mean(2) if a.ndim == 3 else a


def _hann2d(h, w):
    """Janela de Hann 2D — atenua as bordas p/ não vazar frequência falsa na FFT."""
    return xp.outer(xp.hanning(h), xp.hanning(w)).astype(xp.float32)


def _parabolic(c, i, n):
    """Refino subpixel: ajusta uma parábola no pico e nos 2 vizinhos (com wraparound)."""
    im1 = float(c[(i - 1) % n]); i0 = float(c[i]); ip1 = float(c[(i + 1) % n])
    den = im1 - 2.0 * i0 + ip1
    return 0.0 if den == 0 else float(np.clip(0.5 * (im1 - ip1) / den, -1.0, 1.0))


def estimate_shift(ref, frame, window: bool = True):
    """(dy,dx) subpixel do deslocamento de `frame` em relação a `ref`, via correlação de fase."""
    a, b = _lum(ref), _lum(frame)
    h, w = a.shape
    if window:
        win = _hann2d(h, w)
        a = a * win
        b = b * win
    Fa = xp.fft.fft2(a)
    Fb = xp.fft.fft2(b)
    R = Fa * xp.conj(Fb)
    R = R / (xp.abs(R) + 1e-12)                       # cross-power spectrum normalizado
    corr = xp.real(xp.fft.ifft2(R))
    idx = int(xp.argmax(corr))
    py, px = idx // w, idx % w
    # eixos p/ o refino parabólico (linha e coluna que passam pelo pico)
    col = corr[:, px]
    row = corr[py, :]
    sy = py + _parabolic(col, py, h)
    sx = px + _parabolic(row, px, w)
    # traz p/ o intervalo com sinal [-n/2, n/2) (wraparound da FFT)
    if sy > h / 2:
        sy -= h
    if sx > w / 2:
        sx -= w
    # o pico da correlação cruzada fica em -deslocamento; negamos p/ devolver o
    # deslocamento REAL de `frame` em relação a `ref` (frame(r,c) ≈ ref(r-dy, c-dx)).
    return float(-sy), float(-sx)


def shift_image(frame, dy: float, dx: float, order: int = 1):
    """Desloca `frame` por (dy,dx) (subpixel) e devolve (deslocado, mask de validade).

    Usa ndimage.shift (GPU via cupyx quando disponível). `mask`=1 onde o pixel é real,
    0 nas bordas que entraram vazias — o LiveStacker usa isso p/ não contaminar a média."""
    f = to_device(frame).astype(xp.float32)
    sh = (dy, dx, 0) if f.ndim == 3 else (dy, dx)
    out = _ndi.shift(f, sh, order=order, mode="constant", cval=0.0)
    ones = xp.ones(f.shape[:2], xp.float32)
    mask = _ndi.shift(ones, (dy, dx), order=0, mode="constant", cval=0.0)
    return asnumpy(out), asnumpy(mask)              # host: interopera com NumPy/stacker/testes


def align_to(frame, ref, window: bool = True, order: int = 1):
    """Alinha `frame` à `ref` (estima o deslocamento e o desfaz). → (aligned, mask, (dy,dx))."""
    dy, dx = estimate_shift(ref, frame, window=window)
    aligned, mask = shift_image(frame, -dy, -dx, order=order)
    return aligned, mask, (dy, dx)
