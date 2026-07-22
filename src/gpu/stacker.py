"""Live Stacking incremental por média ponderada — 100% em VRAM (float32).

Mantém no device dois acumuladores residentes por toda a sessão:
    _sum  = Σ (peso_i · mask_i · frame_i)
    _wsum = Σ (peso_i · mask_i)
A imagem integrada é _sum / _wsum. É O(1) por frame, maximiza o alcance dinâmico
(float32) e faz lucky imaging (frames melhores pesam mais). Ver docs/03-pipeline-software.md §A.

Suporta mono (H,W) e cor (H,W,3) — o mesmo código serve simulador e câmera colorida.
`xp` é CuPy na Jetson (GPU) ou NumPy no PC de dev.
"""
from __future__ import annotations
from ..backend import xp, to_device


class LiveStacker:
    def __init__(self):
        self._sum = None       # (H,W) ou (H,W,C), alocado no 1º frame
        self._wsum = None      # (H,W) — peso espacial acumulado
        self.n = 0

    def _alloc(self, frame):
        h, w = frame.shape[:2]
        self._sum = xp.zeros_like(frame, dtype=xp.float32)
        self._wsum = xp.zeros((h, w), dtype=xp.float32)

    def add(self, frame, weight: float, mask=None) -> None:
        """frame/mask já ALINHADOS ao referencial. Aceita NumPy ou CuPy."""
        f = to_device(frame).astype(xp.float32)
        if self._sum is None:
            self._alloc(f)
        w = xp.float32(weight)
        if mask is None:
            self._sum += w * f
            self._wsum += w
        else:
            m = to_device(mask).astype(xp.float32)
            self._wsum += w * m
            wm = (w * m)
            self._sum += (wm[..., None] * f) if f.ndim == 3 else (wm * f)
        self.n += 1

    def result(self):
        """Imagem integrada atual (float32, no device). Evita divisão por zero."""
        if self._sum is None:
            return None
        wsum = xp.maximum(self._wsum, xp.float32(1e-6))
        return self._sum / (wsum[..., None] if self._sum.ndim == 3 else wsum)

    def reset(self) -> None:
        self._sum = None
        self._wsum = None
        self.n = 0
