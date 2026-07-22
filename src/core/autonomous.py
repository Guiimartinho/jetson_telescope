"""T12 — Modo autônomo noturno: amarra TUDO numa sessão sem operador.

Para cada observação: escolhe o filtro (auto por tipo) → se for mosaico usa `Mosaic`, senão o
`Scheduler` (auto-find → autofoco → calibração → stack → FITS/WCS → enhance) → telemetria + resumo.
É o produto: agendador + calibração + filtros + mosaico + FITS + pós-processo + persistência juntos.
Ver docs/19.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field

from .scheduler import Scheduler, Target
from .mosaic import Mosaic
from .session_store import save_session
from ..control.filterwheel import filter_for_target


@dataclass
class Observation:
    name: str
    xy: tuple
    frames: int = 60
    kind: str = "galaxy"                 # galaxy/nebula/... → filtro automático
    filter: str = None                   # sobrepõe o filtro automático
    mosaic: tuple = (1, 1)               # (linhas, colunas); >1 = mosaico
    priority: int = 0


class AutonomousNight:
    def __init__(self, session, telemetry=None, do_autofocus: bool = True):
        self.session = session
        self.telemetry = telemetry
        self.do_autofocus = do_autofocus

    def _tlog(self, **f):
        if self.telemetry:
            self.telemetry.log(**f)

    def run(self, observations):
        obs = sorted(observations, key=lambda o: -o.priority)
        results = []
        self._tlog(event="night_start", n=len(obs))
        print(f"\n########## NOITE AUTÔNOMA — {len(obs)} observação(ões) ##########")

        for o in obs:
            if self.session.stop:
                break
            filt = o.filter or filter_for_target(o.kind)
            self._tlog(event="obs_start", target=o.name, filter=filt, mosaic=list(o.mosaic))
            if self.session.filterwheel is not None:
                self.session.set_filter(filt)

            if o.mosaic[0] * o.mosaic[1] > 1:
                out = Mosaic(self.session, do_autofocus=self.do_autofocus).run(
                    o.xy, rows=o.mosaic[0], cols=o.mosaic[1], frames_per_panel=o.frames)
                r = dict(name=o.name, kind="mosaic", filter=filt,
                         panels=len(out["fits"]), stitched=out["stitched"])
            else:
                out = Scheduler(self.session, do_autofocus=self.do_autofocus).run(
                    [Target(o.name, o.xy, frames=o.frames, filter=filt)])
                d = out["results"][0] if out["results"] else {}
                r = dict(name=o.name, kind="single", filter=filt, status=d.get("status"),
                         accepted=d.get("accepted"), snr=d.get("snr"))
            results.append(r)
            self._tlog(event="obs_done", **r)

        summary = dict(count=len(results), observations=results)
        save_session(os.path.join(self.session.cfg.out_dir, "night_summary.json"), summary)
        self._tlog(event="night_end", done=len(results))
        print("\n########## NOITE CONCLUÍDA ##########")
        for r in results:
            print(f"  {r['name']:8s} {r['kind']:6s} filtro={r['filter']}")
        return summary
