"""Calibração completa (bias / dark / flat) — remove ruído de padrão fixo, pixels quentes
e vinheta, na GPU (float32 na VRAM).

Redução padrão (estilo ccdproc), simplificada para o pipeline em tempo real:
    calibrado = clip(light − master_dark, 0) / master_flat_normalizado
onde  master_flat_normalizado = (mean(flats) − master_bias) / mean(...)  (média ≈ 1).

- **master_dark** remove bias + corrente de escuro + pixels quentes.
- **master_flat** corrige vinheta + poeira (resposta do sistema óptico).
- **master_bias** é usado quando não há dark, e para calibrar o flat.

Os masters ficam residentes na VRAM. Ver docs/13-calibracao.md e docs/08 (reuso ccdproc no FITS offline).
"""
from __future__ import annotations
import numpy as np
from ..backend import xp, to_device, asnumpy


def _to_f32(a):
    return to_device(a).astype(xp.float32) if a is not None else None


def remove_hot_pixels(raw, k: float = 6.0, floor: float = 60.0):
    """Remove pixels quentes (spikes de 1px) substituindo pela mediana local 3x3.

    Essencial quando NÃO há darks: senão, ao registrar frames, os hot pixels (fixos no sensor)
    viram trilhas coloridas ('walking noise'). Robusto: um pixel é 'quente' se excede a mediana
    local por mais que `max(floor, k·MAD)`. Trabalha em 2D (RAW Bayer ou mono). Ver docs/27."""
    import cv2
    a = asnumpy(raw)
    med = cv2.medianBlur(a.astype(np.uint16), 3)
    diff = a.astype(np.int32) - med.astype(np.int32)
    sigma = 1.4826 * np.median(np.abs(diff)) + 1e-6
    hot = diff > max(floor, k * sigma)
    return np.where(hot, med, a).astype(np.float32)


class Calibrator:
    def __init__(self, master_bias=None, master_dark=None, master_flat=None):
        self.bias = _to_f32(master_bias)
        self.dark = _to_f32(master_dark)
        self.flat = _to_f32(master_flat)      # já NORMALIZADO (média ≈ 1)

    def apply(self, frame):
        """Aplica a calibração a um frame de luz. Retorna float32 no device."""
        f = to_device(frame).astype(xp.float32)
        if self.dark is not None and self.dark.shape == f.shape:
            f = f - self.dark                 # remove bias + dark + pixels quentes
        elif self.bias is not None and self.bias.shape == f.shape:
            f = f - self.bias
        f = xp.clip(f, 0, None)
        if self.flat is not None and self.flat.shape == f.shape:
            f = f / xp.maximum(self.flat, xp.float32(1e-3))   # corrige vinheta/poeira
        return f

    # ----- construção dos masters ---------------------------------------------
    @staticmethod
    def build_master(frames):
        """Master por média (para bias ou dark). Combina em float32 na VRAM."""
        acc = None
        n = 0
        for fr in frames:
            d = to_device(fr).astype(xp.float32)
            acc = d if acc is None else acc + d
            n += 1
        return acc / n if n else None

    # alias de compatibilidade
    build_master_dark = build_master

    @staticmethod
    def build_master_flat(flat_frames, master_bias=None):
        """Master flat NORMALIZADO (média ≈ 1): (mean(flats) − bias) / mean(...)."""
        m = Calibrator.build_master(flat_frames)
        if m is None:
            return None
        if master_bias is not None:
            m = m - to_device(master_bias).astype(xp.float32)
        m = xp.clip(m, xp.float32(1e-3), None)
        return m / float(asnumpy(m.mean()))

    @classmethod
    def from_frames(cls, dark=None, flat=None, bias=None):
        """Conveniência: constrói todos os masters a partir de conjuntos de frames."""
        mb = cls.build_master(bias) if bias else None
        md = cls.build_master(dark) if dark else None
        mf = cls.build_master_flat(flat, mb) if flat else None
        return cls(master_bias=mb, master_dark=md, master_flat=mf)
