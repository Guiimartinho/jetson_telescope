"""T3 — Roda de filtros: port + adapters (sim/INDI) + seleção por tipo de alvo.

Galáxias (broadband) → L-Pro; nebulosas em emissão → L-eXtreme; padrão → VIS.
No hardware: driver INDI da roda (ou gaveta). Ver docs/17.
"""
from __future__ import annotations


# tipo de alvo → filtro recomendado (ver docs/01 §óptica/filtros)
FILTER_FOR_KIND = {
    "galaxy": "L-Pro",       # broadband (Andrômeda etc.)
    "nebula": "L-eXtreme",   # dual-band Hα+OIII (emissão)
    "lunar": "VIS",
    "planetary": "VIS",
}


def filter_for_target(kind: str, default: str = "VIS") -> str:
    return FILTER_FOR_KIND.get(kind, default)


class FilterWheel:
    def names(self):               # -> list[str]
        raise NotImplementedError

    def current(self) -> str:
        raise NotImplementedError

    def set(self, name: str):
        raise NotImplementedError


class SimFilterWheel(FilterWheel):
    def __init__(self, names=("VIS", "L-Pro", "L-eXtreme"), start="VIS"):
        self._names = list(names)
        if start not in self._names:
            raise ValueError(f"filtro inicial {start!r} não está na roda {self._names}")
        self._cur = start

    def names(self):
        return list(self._names)

    def current(self):
        return self._cur

    def set(self, name):
        if name not in self._names:
            raise ValueError(f"filtro {name!r} não está na roda {self._names}")
        self._cur = name
        return name


class IndiFilterWheel(FilterWheel):
    """Roda de filtros via INDI usando o IndiClient puro-Python (PC de dev E Jetson).

    Lê os nomes em FILTER_NAME (FILTER_NAME_1..N) e troca via FILTER_SLOT (1-based). Valida contra
    indi_simulator_wheel; no bring-up troque `device` para o driver real. Ver docs/20.
    """
    SLOT, SLOT_ELEM = "FILTER_SLOT", "FILTER_SLOT_VALUE"

    def __init__(self, device="Filter Simulator", host="localhost", port=7624,
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
        cli.wait_vector(self.device, self.SLOT, timeout=self._connect_timeout)
        self._connected = True
        return self

    def _ensure(self):
        if not self._connected:
            self.connect()

    def names(self):
        self._ensure()
        p = self.client.get(self.device, "FILTER_NAME")
        if p is None:
            return []
        # ordena por sufixo numérico (FILTER_NAME_1, _2, ...)
        return [p.elements[k] for k in sorted(p.elements, key=lambda k: int(k.rsplit("_", 1)[-1]))]

    def current(self):
        self._ensure()
        slot = self.client.value(self.device, self.SLOT, self.SLOT_ELEM)
        names = self.names()
        idx = int(round(slot)) - 1 if slot is not None else -1
        return names[idx] if 0 <= idx < len(names) else None

    def set(self, name, timeout=30.0):
        self._ensure()
        names = self.names()
        if name not in names:
            raise ValueError(f"filtro {name!r} não está na roda {names}")
        self.client.send_number(self.device, self.SLOT, {self.SLOT_ELEM: names.index(name) + 1})
        self.client.wait_state(self.device, self.SLOT, "Ok", timeout=timeout)
        return name

    def close(self):
        if self._own_client:
            self.client.close()
