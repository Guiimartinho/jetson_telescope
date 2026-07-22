"""Ring buffer de frames em memória PRÉ-ALOCADA.

Aloca UMA vez N buffers do tamanho do frame e os reaproveita em rodízio, evitando
alocação por frame — que fragmentaria a memória e criaria pausas de GC/alocador na
Jetson. Espelha o "único ponto de entrada na memória unificada" de docs/02-arquitetura.md.

Nesta versão MVP o uso é síncrono (um produtor = simulador/câmera, um consumidor =
pipeline). A versão com threads produtor/consumidor é o refinamento da Fase 1.1.
"""
from __future__ import annotations
import numpy as np


class RingBuffer:
    def __init__(self, slots: int, shape, dtype=np.float32):
        self.slots = [np.empty(shape, dtype) for _ in range(slots)]
        self._i = -1

    def acquire(self) -> np.ndarray:
        """Devolve o próximo buffer do rodízio, pronto para ser preenchido."""
        self._i = (self._i + 1) % len(self.slots)
        return self.slots[self._i]
