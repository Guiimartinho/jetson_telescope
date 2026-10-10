"""Atualização do software pelo app.

A API fala com uma PORTA (`status`, `check`, `install`). Aqui está o adapter de MENTIRA,
`SimUpdater`: é com ele que a tela de atualizações do app é desenvolvida e testada. O de
verdade ainda não existe — o software chega à Jetson por cabo, do computador — e por isso, no
aparelho, a API responde `enabled: false`.

O contrato que o app espera de qualquer adapter:

  * `check` procura e `available` passa a dizer qual versão há (ou nada);
  * `install` baixa, instala e reinicia; `state` e `progress` contam o andamento;
  * se a instalação falhar, a versão ANTERIOR continua valendo, e `error` diz por quê.
"""
from __future__ import annotations

import threading
import time
from typing import Protocol, runtime_checkable

STATES = ("idle", "checking", "downloading", "installing", "restarting", "failed")


class UpdateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@runtime_checkable
class Updater(Protocol):
    """A porta: o que a API pede à atualização do aparelho. O que não dá para fazer agora
    levanta `UpdateError`."""

    def status(self) -> dict: ...
    def check(self) -> None: ...
    def install(self) -> None: ...


class SimUpdater:
    """Uma atualização de mentira: acha uma versão nova, instala em alguns segundos, reinicia."""

    def __init__(self, current: str, newer: str = "9.9.0",
                 notes=("Autofoco mais rápido", "Correções na noite autônoma"),
                 install_s: float = 6.0, clock=time.monotonic):
        self._lock = threading.Lock()
        self._clock = clock
        self.current, self.newer, self.notes = current, newer, list(notes)
        self.install_s = float(install_s)
        self.available: dict | None = None
        self.error: str | None = None
        self.fail_next = False                  # os testes ligam: a próxima instalação falha
        self._state, self._since = "idle", clock()

    def _tick(self) -> None:
        elapsed = self._clock() - self._since
        if self._state == "checking" and elapsed >= 1.0:
            self.available = None if self.current == self.newer else {
                "version": self.newer, "notes": list(self.notes)}
            self._state = "idle"
        elif self._state in ("downloading", "installing", "restarting"):
            if self.fail_next and elapsed >= self.install_s * 0.5:
                self.fail_next = False
                self._state, self.error = "failed", "install_failed"     # a versão de antes fica
            elif elapsed >= self.install_s + 1.5:
                self.current, self.available = self.newer, None
                self._state = "idle"
            elif elapsed >= self.install_s:
                self._state = "restarting"
            elif elapsed >= self.install_s * 0.4:
                self._state = "installing"

    def status(self) -> dict:
        with self._lock:
            self._tick()
            progress = None
            if self._state in ("downloading", "installing"):
                progress = round(min(1.0, (self._clock() - self._since) / self.install_s), 2)
            return {"enabled": True, "current": self.current, "available": self.available,
                    "state": self._state, "progress": progress, "error": self.error}

    def check(self) -> None:
        with self._lock:
            self._tick()
            if self._state not in ("idle", "failed"):
                raise UpdateError("busy", "já há uma atualização em andamento")
            self._state, self._since, self.error = "checking", self._clock(), None

    def install(self) -> None:
        with self._lock:
            self._tick()
            if self._state not in ("idle", "failed"):
                raise UpdateError("busy", "já há uma atualização em andamento")
            if self.available is None:
                raise UpdateError("nothing_to_install", "não há versão nova para instalar")
            self._state, self._since, self.error = "downloading", self._clock(), None
