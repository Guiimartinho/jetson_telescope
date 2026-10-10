"""Trabalhos: cada comando longo do app (apontar, empilhar...) vira um trabalho acompanhável.

Dois problemas que isto resolve:

  * QUEDA DE SINAL. O app reenvia o comando; o mesmo `id` devolve o mesmo trabalho, sem
    executar de novo — a montagem não se mexe duas vezes.
  * "E AÍ, TERMINOU?". O Controller publica o estado com a etiqueta do comando que o gerou
    (`job`) e, no fim, como terminou (`outcome`). Aqui isso vira o ciclo de vida do trabalho:

        accepted -> running -> done | failed | stopped
"""
from __future__ import annotations

import copy
import secrets
import threading
from collections import OrderedDict
from typing import Callable

# estado do Controller -> nome da etapa na API
_STEP = {"SLEWING": "slew", "SOLVING": "solve", "FOCUSING": "focus", "STACKING": "stack",
         "SCHEDULING": "schedule", "TRACKING": "track", "PREVIEW": "preview",
         "CAPTURING": "capture"}
_FAILURES = {"not_converged": "not_converged", "focus_failed": "focus_failed",
             "polar_failed": "polar_failed", "error": "internal"}
_OPEN = ("accepted", "running")


class JobBook:
    def __init__(self, keep: int = 64):
        self._lock = threading.Lock()
        self._by_cmd: OrderedDict[str, dict] = OrderedDict()
        self._keep, self._n = keep, 0
        self._boot = secrets.token_hex(2)        # ids não se repetem depois de reiniciar
        self._current: dict | None = None

    def run(self, cmd_id: str, kind: str, action: Callable[[str], None],
            target: str | None = None) -> dict:
        """Registra o comando e o executa uma única vez. `action` recebe o id do trabalho, que
        vai junto ao Controller como etiqueta."""
        with self._lock:
            known = self._by_cmd.get(cmd_id)
            if known is not None:
                return copy.deepcopy(known)
            self._n += 1
            job = {"job": f"j-{self._boot}-{self._n}", "kind": kind, "state": "accepted",
                   "target": target, "steps": [], "error": None}
            self._by_cmd[cmd_id] = job
            while len(self._by_cmd) > self._keep:
                self._by_cmd.popitem(last=False)
            cur = self._current
            if kind == "stop":
                job["state"] = "done"            # parar é imediato; quem muda é o trabalho parado
                if cur is not None and cur["state"] in _OPEN:
                    cur["stopping"] = True
            else:
                if cur is not None and cur["state"] in _OPEN:
                    self._finish(cur, "stopped")     # um comando novo interrompe o anterior
                self._current = job
            snapshot = _public(job)
        action(job["job"])
        return snapshot

    def known(self, cmd_id: str) -> dict | None:
        """O trabalho que este comando já gerou, ou None. Serve a quem precisa conferir algo
        ANTES de aceitar um comando novo sem recusar o reenvio de um que já está rodando."""
        with self._lock:
            job = self._by_cmd.get(cmd_id)
            return None if job is None else _public(job)

    def observe(self, stats: dict) -> dict | None:
        """Avança o trabalho atual pelo estado que o Controller publicou e o devolve."""
        with self._lock:
            job = self._current
            if job is None:
                return None
            if job["state"] in _OPEN and stats.get("job") == job["job"]:
                outcome = stats.get("outcome") or ""
                step = _STEP.get(stats.get("state") or "")
                if outcome:                                  # o Controller disse como terminou
                    if job.get("stopping") or outcome == "stopped":
                        self._finish(job, "stopped")
                    elif outcome in _FAILURES:
                        self._finish(job, "failed", _FAILURES[outcome])
                    else:
                        self._finish(job, "done")
                elif step:
                    job["state"] = "running"
                    steps = job["steps"]
                    if not steps or steps[-1]["name"] != step:
                        for s in steps:
                            s["state"] = "done"
                        steps.append({"name": step, "state": "running"})
            return _public(job)

    @property
    def current(self) -> dict | None:
        with self._lock:
            return None if self._current is None else _public(self._current)

    @staticmethod
    def _finish(job: dict, state: str, error: str | None = None) -> None:
        job["state"], job["error"] = state, error
        for s in job["steps"]:
            if s["state"] == "running":
                s["state"] = "done" if state == "done" else state


def _public(job: dict) -> dict:
    out = copy.deepcopy(job)
    out.pop("stopping", None)
    return out
