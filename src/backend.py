"""Camada de abstração de backend de arrays (o coração da portabilidade).

Escreve-se o pipeline UMA única vez usando `xp`, e ele roda:
  - na Jetson Orin Nano:  xp = CuPy  -> operações na GPU (memória unificada LPDDR5)
  - no PC de desenvolvimento: xp = NumPy -> mesma lógica, na CPU

Assim o empilhamento e as métricas são desenvolvidos no notebook (Windows/Linux) e
implantados no Orin Nano Super sem alterar uma linha. Ver docs/02-arquitetura.md.

Na Jetson (JetPack 6.2 / CUDA 12.6):  pip install cupy-cuda12x
"""
from __future__ import annotations
import numpy as np

try:
    import cupy as _cp  # wheel aarch64 pronta no JetPack 6.2 (cupy-cuda12x)
    # Um toque simples só para confirmar que há CUDA de fato utilizável:
    _cp.zeros(1)
    xp = _cp
    HAS_CUPY = True
except Exception:                      # ImportError, ou CUDA ausente (PC de dev)
    _cp = None
    xp = np
    HAS_CUPY = False


def to_device(a) -> "xp.ndarray":
    """Move um array do host (NumPy) para o device (CuPy). No-op na CPU."""
    return xp.asarray(a)


def asnumpy(a) -> np.ndarray:
    """Traz um array do device (CuPy) para o host (NumPy). No-op se já for NumPy."""
    if HAS_CUPY and isinstance(a, _cp.ndarray):
        return _cp.asnumpy(a)
    return np.asarray(a)


def sync() -> None:
    """Sincroniza a GPU — necessário para medir tempo de forma honesta. No-op na CPU."""
    if HAS_CUPY:
        _cp.cuda.runtime.deviceSynchronize()


def backend_name() -> str:
    if HAS_CUPY:
        try:
            props = _cp.cuda.runtime.getDeviceProperties(0)
            return f"CuPy/GPU ({props['name'].decode()})"
        except Exception:
            return "CuPy/GPU"
    return "NumPy/CPU (modo desenvolvimento)"
