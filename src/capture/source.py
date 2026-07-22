"""Fonte de frames — abstração que unifica simulador e câmera real.

O orquestrador não sabe (nem precisa saber) de onde vêm os frames. Isso permite
desenvolver todo o pipeline com o simulador no PC e, na Jetson, trocar por uma câmera
INDI sem mudar o resto. Ver docs/08-reusar-vs-construir.md.
"""
from __future__ import annotations
import numpy as np

from .simulator import StarFieldSimulator, SimConfig


class FrameSource:
    """Interface comum. `read()` devolve (frame_float32, meta:dict)."""
    is_color = False
    bayer = "RGGB"

    def read(self, out: np.ndarray | None = None):
        raise NotImplementedError

    def close(self):
        pass


class SimulatorSource(FrameSource):
    """Fonte sintética (mono) — desenvolve o pipeline sem câmera."""
    is_color = False

    def __init__(self, cfg: SimConfig | None = None):
        self.sim = StarFieldSimulator(cfg)
        self.i = 0

    def read(self, out=None):
        f, meta = self.sim.frame(self.i, out=out)
        self.i += 1
        return f, meta


def build_source(kind: str, sim_cfg: SimConfig | None = None, **indi_kw) -> FrameSource:
    """Fábrica. kind='sim' → simulador; kind='indi' → câmera via INDI (IndiClient puro-Python)."""
    if kind == "sim":
        return SimulatorSource(sim_cfg)
    if kind == "indi":
        from .indi_source import IndiCameraSource   # import tardio (só na Jetson)
        return IndiCameraSource(**indi_kw)
    raise ValueError(f"fonte desconhecida: {kind!r} (use 'sim' ou 'indi')")
