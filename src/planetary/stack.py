"""Empilhamento lucky-imaging — junta os filtros num resultado (Lua/planetas).

Pipeline: grade (nitidez) → select (top N%) → align (correlação de fase à referência mais
nítida) → stack (média ponderada em VRAM, reusa `gpu/stacker.LiveStacker`) → sharpen (wavelets
opcional). Frames mais nítidos pesam mais. Tudo em `xp` (GPU na Jetson, NumPy no PC/CI).
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

from ..backend import asnumpy
from ..gpu.stacker import LiveStacker
from .lucky import grade, select_best
from .align import align_to
from .wavelets import wavelet_sharpen, DEFAULT_WEIGHTS


@dataclass
class LuckyResult:
    image: np.ndarray            # imagem final (float32, host)
    used: int                    # nº de frames empilhados
    total: int                   # nº de frames recebidos
    ref: int                     # índice do frame de referência (o mais nítido)
    scores: np.ndarray           # nitidez de cada frame de entrada
    shifts: list                 # (dy,dx) estimado por frame usado


def lucky_stack(frames, keep: float = 0.3, align: bool = True,
                sharpen=DEFAULT_WEIGHTS, min_keep: int = 1) -> LuckyResult:
    """Empilha os melhores frames com alinhamento por superfície e aguçamento wavelet.

    frames: sequência de arrays (mono HxW ou cor HxWx3), mesma forma.
    keep: fração dos mais nítidos a usar (0.3 = 30%). align: alinha por correlação de fase.
    sharpen: pesos de wavelet (None/[] desliga). → LuckyResult."""
    frames = list(frames)
    n = len(frames)
    if n == 0:
        raise ValueError("lucky_stack: nenhum frame")

    scores = grade(frames)
    idx = select_best(scores, keep=keep, min_keep=min_keep)
    ref_i = int(np.argmax(scores))            # o mais nítido é a referência de alinhamento
    ref = frames[ref_i]

    stacker = LiveStacker()
    shifts = []
    for i in idx:
        f = frames[int(i)]
        if align:
            aligned, mask, sh = align_to(f, ref)
        else:
            aligned, mask, sh = f, None, (0.0, 0.0)
        stacker.add(aligned, weight=float(scores[i]), mask=mask)
        shifts.append(sh)

    out = asnumpy(stacker.result()).astype(np.float32)
    if sharpen is not None and len(sharpen) > 0:
        out = wavelet_sharpen(out, weights=sharpen, clip=True).astype(np.float32)

    return LuckyResult(image=out, used=len(idx), total=n, ref=ref_i,
                       scores=scores, shifts=shifts)
