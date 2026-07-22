"""Agendador multi-alvo (Plan mode) — sessão autônoma que percorre uma fila de alvos.

Para cada alvo (por prioridade, se visível): auto-find → autofoco → stack por N frames →
próximo. É o que um smart telescope faz a noite toda. Compõe os métodos do Session; a
máquina de estados ganha o estado SCHEDULING entre alvos. **Falha em um alvo NÃO derruba a
sessão** — registra e pula para o próximo. Ver docs/12-fase3-agendador.md.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Union

from .state import State


@dataclass
class Target:
    name: str
    xy: tuple                        # (mundo) no sim; (RA, DEC) no hardware
    frames: int = 60                 # orçamento de integração (frames)
    priority: int = 0                # maior = primeiro
    visible: Union[Callable[[], bool], bool] = True   # restrição (altitude/tempo no HW)
    filter: str = None               # filtro a usar (ex.: 'L-Pro', 'L-eXtreme')

    def is_visible(self) -> bool:
        return self.visible() if callable(self.visible) else bool(self.visible)


class Scheduler:
    """Orquestra uma fila de alvos sobre um Session já montado."""

    def __init__(self, session, do_autofocus: bool = True):
        self.session = session
        self.do_autofocus = do_autofocus

    def run(self, targets):
        s = self.session
        s._set_state(State.SCHEDULING)
        ordered = sorted(targets, key=lambda t: -t.priority)
        visible = [t for t in ordered if t.is_visible()]
        skipped = [t.name for t in ordered if not t.is_visible()]
        results = []
        total = len(visible)
        print(f"\n===== AGENDADOR: {total} alvo(s) na fila "
              f"(pulados por visibilidade: {skipped or '—'}) =====")

        for i, t in enumerate(visible):
            if s.stop:
                break
            s._set_state(State.SCHEDULING)
            s.stats.update(target=t.name, queue_done=i, queue_total=total)
            if t.filter and s.filterwheel is not None:
                s.set_filter(t.filter)
            print(f"\n----- [{i+1}/{total}] {t.name} (prioridade {t.priority}) -----")

            if not s.auto_find(t.xy):
                s._set_state(State.SCHEDULING)          # find falhou → pula o alvo
                results.append(dict(name=t.name, status="falha-autofind"))
                continue
            if self.do_autofocus:
                s.autofocus()
            st = s.run_stack(frames=t.frames, label=t.name)
            results.append(dict(name=t.name, status="ok",
                                accepted=st["accepted"], snr=st["snr"]))

        s.stats.update(queue_done=total)
        if not s.stop:
            s._set_state(State.IDLE)

        print("\n===== AGENDA CONCLUÍDA =====")
        for r in results:
            extra = (f" · {r['accepted']} frames · SNR {r['snr']}x"
                     if r["status"] == "ok" else "")
            print(f"  {r['name']:8s} {r['status']}{extra}")
        return dict(results=results, skipped=skipped)
