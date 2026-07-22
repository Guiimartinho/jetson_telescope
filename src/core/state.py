"""Máquina de estados explícita da sessão (arquitetura recomendada — docs/11).

Torna o fluxo autônomo robusto e testável: estados nomeados + transições válidas.
Invariante-chave de segurança: **não se empilha direto após um slew cego** — de SLEWING
só se sai para SOLVING (tem que resolver/centralizar antes). STOPPED é terminal.
"""
from __future__ import annotations
from enum import Enum


class State(Enum):
    IDLE = "pronto"
    SLEWING = "apontando"
    SOLVING = "procurando alvo"
    FOCUSING = "focando"
    STACKING = "empilhando"
    SCHEDULING = "agendando"
    TRACKING = "rastreando"
    ERROR = "erro"
    STOPPED = "encerrado"

    @property
    def label(self) -> str:
        return self.value


# Transições permitidas (destinos válidos a partir de cada estado).
# Invariante de segurança preservado: SLEWING nunca vai direto p/ STACKING (tem que SOLVING).
_TRANSITIONS = {
    State.IDLE:       {State.SLEWING, State.SOLVING, State.FOCUSING, State.STACKING,
                       State.SCHEDULING, State.TRACKING, State.STOPPED, State.ERROR},
    State.SLEWING:    {State.SOLVING, State.SCHEDULING, State.ERROR, State.STOPPED},
    State.SOLVING:    {State.SOLVING, State.FOCUSING, State.STACKING, State.SLEWING,
                       State.SCHEDULING, State.TRACKING, State.ERROR, State.STOPPED},
    State.FOCUSING:   {State.STACKING, State.SOLVING, State.SCHEDULING, State.IDLE,
                       State.ERROR, State.STOPPED},
    State.STACKING:   {State.IDLE, State.SLEWING, State.FOCUSING, State.SCHEDULING,
                       State.TRACKING, State.ERROR, State.STOPPED},
    State.SCHEDULING: {State.SCHEDULING, State.SLEWING, State.TRACKING, State.IDLE,
                       State.ERROR, State.STOPPED},
    State.TRACKING:   {State.TRACKING, State.IDLE, State.SLEWING, State.ERROR, State.STOPPED},
    State.ERROR:      {State.IDLE, State.SCHEDULING, State.STOPPED},
    State.STOPPED:    set(),                    # terminal
}


class InvalidTransition(RuntimeError):
    pass


class SessionStateMachine:
    def __init__(self, state: State = State.IDLE):
        self.state = state
        self.history = [state]

    def can(self, target: State) -> bool:
        return target in _TRANSITIONS[self.state]

    def to(self, target: State) -> State:
        if not self.can(target):
            raise InvalidTransition(
                f"transição inválida: {self.state.name} -> {target.name}")
        self.state = target
        self.history.append(target)
        return target

    @property
    def label(self) -> str:
        return self.state.label
