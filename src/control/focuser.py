"""Focalizador — abstração unificada (simulado e real via INDI/ZWO EAF).

O SimFocuser tem uma posição de foco ótima OCULTA (`best`); o algoritmo de autofoco não
a conhece — só mede o FWHM e converge até ela. No hardware: `indi_asi_focuser` (ZWO EAF).
Ver docs/03-pipeline-software.md §D e docs/08.
"""
from __future__ import annotations
import numpy as np


class Focuser:
    def position(self) -> int:
        raise NotImplementedError

    def move_to(self, pos):
        raise NotImplementedError

    def move_by(self, delta):
        self.move_to(self.position() + delta)


class SimFocuser(Focuser):
    def __init__(self, position=4200, best=6300, lo=0, hi=10000):
        self._pos = int(position)
        self.best = int(best)          # oculto do algoritmo (é o "foco crítico")
        self.lo, self.hi = lo, hi

    def position(self):
        return self._pos

    def move_to(self, pos):
        self._pos = int(np.clip(pos, self.lo, self.hi))


class IndiFocuser(Focuser):
    """Focalizador via INDI usando o IndiClient puro-Python (PC de dev E Jetson).

    Move ABS_FOCUS_POSITION/FOCUS_ABSOLUTE_POSITION e espera o vetor voltar a Ok. Valida contra
    indi_simulator_focus; no bring-up troque `device` para "ASI EAF". Ver docs/20.
    """
    VEC = "ABS_FOCUS_POSITION"
    ELEM = "FOCUS_ABSOLUTE_POSITION"

    def __init__(self, device="Focuser Simulator", host="localhost", port=7624,
                 client=None, connect_timeout=10.0):
        from ..io.indi_client import IndiClient
        self.device = device
        self._own_client = client is None
        self.client = client or IndiClient(host, port).connect()
        self._connect_timeout = connect_timeout
        self._connected = False

    def connect(self):
        cli = self.client
        cli.get_properties(self.device)
        cli.connect_device(self.device, timeout=self._connect_timeout)
        cli.wait_vector(self.device, self.VEC, timeout=self._connect_timeout)
        self._connected = True
        return self

    def _ensure(self):
        if not self._connected:
            self.connect()

    def position(self):
        self._ensure()
        v = self.client.value(self.device, self.VEC, self.ELEM)
        return int(round(v)) if v is not None else 0

    def move_to(self, pos, timeout=60.0):
        self._ensure()
        self.client.send_number(self.device, self.VEC, {self.ELEM: int(pos)})
        self.client.wait_state(self.device, self.VEC, "Ok", timeout=timeout)
        return self.position()

    def close(self):
        if self._own_client:
            self.client.close()
