"""Testes da máquina de estados da sessão (arquitetura recomendada — docs/11)."""
import pytest

from src.core.state import State, SessionStateMachine, InvalidTransition


def test_happy_path_autonomous():
    sm = SessionStateMachine()
    for st in (State.SLEWING, State.SOLVING, State.FOCUSING, State.STACKING):
        sm.to(st)
    assert sm.state is State.STACKING
    assert sm.history[0] is State.IDLE


def test_loop_cycle_stacking_back_to_slewing():
    sm = SessionStateMachine(State.STACKING)
    sm.to(State.SLEWING)                  # próximo alvo no modo loop
    assert sm.state is State.SLEWING


def test_cannot_stack_right_after_blind_slew():
    """Invariante de segurança: SLEWING -> STACKING é proibido (tem que resolver antes)."""
    sm = SessionStateMachine(State.SLEWING)
    with pytest.raises(InvalidTransition):
        sm.to(State.STACKING)


def test_stopped_is_terminal():
    sm = SessionStateMachine(State.STACKING)
    sm.to(State.STOPPED)
    for st in State:
        if st is State.STOPPED:
            continue
        with pytest.raises(InvalidTransition):
            sm.to(st)


def test_error_reachable_and_recoverable():
    sm = SessionStateMachine(State.SOLVING)
    sm.to(State.ERROR)
    sm.to(State.IDLE)                     # recuperação
    assert sm.state is State.IDLE


def test_can_predicts_transition():
    sm = SessionStateMachine(State.SLEWING)
    assert sm.can(State.SOLVING) is True
    assert sm.can(State.STACKING) is False


def test_label_is_human_readable():
    assert State.STACKING.label == "empilhando"
    assert SessionStateMachine().label == "pronto"
