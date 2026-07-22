"""Modo Sistema Solar — Lua, planetas e Sol (lucky imaging de alta cadência).

Disciplina DIFERENTE do céu profundo (`src/gpu`): em vez de exposições longas alinhadas por
estrelas, capturamos milhares de frames curtos, ficamos com os mais nítidos (a atmosfera —
seeing — borra a maioria), alinhamos pela SUPERFÍCIE (correlação de fase, não há estrelas),
empilhamos e aguçamos com wavelets. É o pipeline por trás de AutoStakkert!/Registax, mas
aberto e em GPU (`xp` = CuPy na Jetson). Ver docs/30-modo-planetario.md.

Filtros (Pipes & Filters):
    grade  → nitidez por frame (Laplaciano)           [lucky.py]
    select → fica com os top N% mais nítidos           [lucky.py]
    align  → correlação de fase (deslocamento subpixel) [align.py]
    stack  → média ponderada em VRAM (reusa LiveStacker)[stack.py]
    sharpen→ wavelets à trous (multi-escala)            [wavelets.py]
"""
from __future__ import annotations

from .lucky import sharpness, grade, select_best
from .align import estimate_shift, align_to
from .wavelets import wavelet_sharpen
from .stack import lucky_stack, LuckyResult

__all__ = ["sharpness", "grade", "select_best", "estimate_shift", "align_to",
           "wavelet_sharpen", "lucky_stack", "LuckyResult"]
