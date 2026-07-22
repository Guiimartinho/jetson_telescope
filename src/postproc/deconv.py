"""T19 — Deconvolução (Richardson-Lucy) + denoise: as alavancas que passam a DWARF (docs/23).

Deconvolução recupera detalhe/nitidez desfeito pela atmosfera+óptica (a PSF), algo que a DWARF NÃO
faz ao vivo. Estimamos a PSF pelas estrelas (gaussiana ~FWHM) e rodamos R-L na LUMINÂNCIA (sharpen
sem amplificar ruído de cor), reaplicando o ganho aos canais. FOSS puro (scipy FFT). Na Jetson isto
migra para cuCIM/Cosmic-Clarity→TensorRT (mais rápido e com modelo IA). Denoise: GraXpert se instalado,
senão um denoise clássico (bilateral). Ver docs/25.
"""
from __future__ import annotations
import numpy as np
from scipy.signal import fftconvolve


def gaussian_psf(sigma: float, radius: int | None = None) -> np.ndarray:
    r = radius if radius is not None else max(2, int(round(3 * sigma)))
    ax = np.arange(-r, r + 1)
    xx, yy = np.meshgrid(ax, ax)
    k = np.exp(-(xx * xx + yy * yy) / (2.0 * sigma * sigma))
    return (k / k.sum()).astype(np.float32)


def richardson_lucy(img: np.ndarray, psf: np.ndarray, iterations: int = 12) -> np.ndarray:
    """Deconvolução R-L de uma imagem 2D (float). PSF normalizada. Não-negativa."""
    img = np.maximum(np.asarray(img, np.float32), 0.0)
    psf = psf / psf.sum()
    mirror = psf[::-1, ::-1]
    est = np.full_like(img, float(img.mean()) + 1e-6)
    for _ in range(int(iterations)):
        conv = fftconvolve(est, psf, mode="same")
        est *= fftconvolve(img / (conv + 1e-6), mirror, mode="same")
        est = np.clip(est, 0.0, None)
    return est


def deconvolve_rgb(rgb: np.ndarray, iterations: int = 12, sigma: float = 1.4,
                   max_gain: float = 2.2) -> np.ndarray:
    """Deconvolve a LUMINÂNCIA e reaplica o ganho aos 3 canais (sharpen sem ruído de cor).

    rgb: HxWx3 (qualquer escala). iterations=0 → no-op. `max_gain` limita o realce p/ não estourar."""
    if iterations <= 0:
        return rgb
    rgb = np.asarray(rgb, np.float32)
    lum = rgb.mean(2) + 1e-6
    dec = richardson_lucy(lum, gaussian_psf(sigma), iterations)
    ratio = np.clip(dec / lum, 1.0 / max_gain, max_gain)   # ganho de nitidez, limitado
    return np.clip(rgb * ratio[..., None], 0, None)


def denoise_luminance(rgb_u8: np.ndarray, amount: float) -> np.ndarray:
    """Denoise de luminância clássico (bilateral) — preserva bordas. amount 0-1.

    Placeholder do denoise IA: na Jetson, GraXpert (ONNX→TensorRT) substitui isto com muito mais
    qualidade. Aqui garante um denoise real e rápido sem dependência extra."""
    import cv2
    if amount <= 0:
        return rgb_u8
    d = int(3 + amount * 6) | 1
    return cv2.bilateralFilter(rgb_u8, d, 40 * amount + 10, 40 * amount + 10)
