"""Painel de controle: um servidor que roda QUALQUER modo sob demanda (via botões da UI).

Monta o mundo simulado uma vez e, a cada comando `start:<modo>[:<alvo>]`, para o modo atual e
inicia o novo numa thread. Modos: stack, autofind, scheduler, mosaic, tracking, night. `stop` para.
Assim dá para **testar tudo pelo navegador**. Ver docs/19.
"""
from __future__ import annotations
import os
import threading
import time

from .orchestrator import Session
from .state import State
from .scheduler import Scheduler, Target
from .mosaic import Mosaic, panel_centers
from .autonomous import AutonomousNight, Observation
from ..control.autofind_radec import close_loop_goto
from ..control.polar_align import SimPolarAxis, polar_error
from ..capture.sky import SkyModel, SkyCameraSource
from ..capture.satellite import SatelliteScene
from ..control.mount import SimMount
from ..control.focuser import SimFocuser
from ..control.solver import SimSolver
from ..control.filterwheel import SimFilterWheel, filter_for_target
from ..control.detector import YoloTensorRTDetector


JOG_PX_S = {1: 15.0, 2: 90.0, 3: 450.0}      # as três velocidades do movimento manual (sim)
JOG_DIR = {"N": (0.0, -1.0), "S": (0.0, 1.0), "E": (1.0, 0.0), "W": (-1.0, 0.0)}
# estados em que um modo é dono da montagem: aí o movimento manual não entra (mover no meio
# de uma captura planetária estragaria a gravação)
_MOUNT_BUSY = ("SLEWING", "SOLVING", "FOCUSING", "STACKING", "SCHEDULING", "TRACKING", "CAPTURING")
# Captura planetária: quanto os quadros guardados (os mais nítidos) podem ocupar. O pedido vem em
# número de quadros, mas o que acaba a memória da Jetson são bytes: com quadros grandes, "metade
# de 3000" não cabe. O teto vale mais que o pedido.
PLANET_BUDGET_BYTES = 256 * 1024 * 1024


class Controller:
    def __init__(self, cfg, hub=None):
        self.cfg = cfg
        self.hub = hub
        self.sky = SkyModel(n_stars=4000)
        self.mount = SimMount(cx=self.sky.targets["M31"][0], cy=self.sky.targets["M31"][1])
        self.focuser = SimFocuser(position=4200, best=6300)
        self.session = Session(cfg, hub=hub, mount=self.mount, focuser=self.focuser,
                               solver=SimSolver(self.mount), filterwheel=SimFilterWheel())
        # O plano da noite vem de fora (a API guarda a fila): () -> lista de itens.
        self.plan_provider = None
        # A latitude do lugar também (é o celular quem a traz): () -> graus. O alinhamento
        # polar precisa dela para saber onde o polo fica no céu.
        self.latitude_provider = None
        self.polar_axis = SimPolarAxis()                 # a montagem de mentira, desalinhada
        # Movimento manual: (direção, velocidade, prazo, último passo). Tem PRAZO: se quem
        # comanda sumir (sinal caiu com o dedo no botão), a montagem para sozinha.
        self._jog = None
        self._mount_ctl = {"parked": False, "tracking": True}
        self._drift0 = self.mount.drift
        self._idle_cam = None
        self.session.stats.update(focus_pos=int(self.focuser.position()),
                                  focus_range=[int(self.focuser.lo), int(self.focuser.hi)],
                                  mount_ctl=dict(self._mount_ctl, jog=None))
        # Publica o estado inicial (IDLE + backend real). Sem isso o hub fica vazio até o
        # primeiro modo rodar, e as UIs caem no padrão "CPU" com o pipeline em GPU.
        self.session._publish()
        # RA/DEC reais (graus) dos alvos, p/ o auto-find celeste (modo goto — T16)
        self.radec = {"M31": (10.68, 41.27), "M42": (83.82, -5.39), "M45": (56.87, 24.10)}
        self._q, self._lock, self._worker = [], threading.Lock(), None

    # -- fila de comandos (chamada pela UI via /cmd) ---------------------------
    def submit(self, cmd: str, tag: str | None = None):
        """Enfileira um comando. `tag` identifica o comando (a API manda o id do trabalho):
        o estado publicado passa a dizer de qual comando ele é."""
        with self._lock:
            self._q.append((cmd, tag))

    def dispatch(self, cmd: str, tag: str | None = None):
        if cmd == "stop":
            self.session.stop = True
            self._halt_jog()                             # PARAR vale para o movimento manual
        elif cmd == "skip":
            self.session.skip = True                     # pula o alvo atual do plano
        elif cmd.startswith("start:"):
            self._start(cmd[len("start:"):], tag)
        elif cmd.startswith("focus:"):
            self._focus_cmd(cmd.split(":")[1:])
        elif cmd.startswith("mount:"):
            self._mount_cmd(cmd.split(":")[1:])
        elif cmd.startswith("polar:"):
            self._polar_cmd(cmd.split(":")[1:])

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _drain(self):
        with self._lock:
            cmds, self._q = self._q, []
        for cmd, tag in cmds:
            self.dispatch(cmd, tag)

    def _loop(self):
        while True:
            self._drain()
            self._jog_step(time.monotonic())
            time.sleep(0.1)

    # -- foco e montagem à mão -------------------------------------------------
    def _working(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _refresh_frame(self):
        """Parado, ninguém publica quadros: depois de mexer à mão (montagem, foco), tira um
        para a tela mostrar o resultado. Com um modo rodando, é ele quem publica."""
        if self._working():
            self.session._publish()
            return
        try:
            if self._idle_cam is None:
                self._idle_cam = SkyCameraSource(self.sky, self.mount, self.focuser,
                                                 view_w=self.cfg.width, view_h=self.cfg.height,
                                                 bad_frac=0.0)
            frame, _ = self._idle_cam.read()
            self.session._publish(frame)
        except Exception as e:
            print(f"[controller] sem quadro novo: {e}")
            self.session._publish()

    def _focus_cmd(self, parts):
        """`focus:move:<passos>` ou `focus:goto:<posição>`. Durante o autofoco quem manda no
        focalizador é ele: o comando manual é ignorado."""
        if self.session.sm.state is State.FOCUSING or len(parts) != 2:
            return
        try:
            value = int(parts[1])
        except ValueError:
            return
        if parts[0] == "move":
            self.focuser.move_by(value)
        elif parts[0] == "goto":
            self.focuser.move_to(value)
        else:
            return
        self.session.stats.update(focus_pos=int(self.focuser.position()))
        self._refresh_frame()

    def _publish_mount(self):
        jog = self._jog[0] if self._jog else None
        self.session.stats.update(mount_ctl=dict(self._mount_ctl, jog=jog))

    def _halt_jog(self):
        if self._jog is not None:
            self._jog = None
            self._publish_mount()
            self.session._publish()

    def _mount_cmd(self, parts):
        """Montagem à mão (simulada): `jog:<N|S|E|W>:<1-3>[:<prazo_ms>]`, `halt`, `park`,
        `unpark`, `home`, `tracking:<on|off>`."""
        what = parts[0] if parts else ""
        ctl = self._mount_ctl
        if what == "jog" and len(parts) >= 3:
            busy = self._working() and self.session.sm.state.name in _MOUNT_BUSY
            try:
                rate, hold = int(parts[2]), (int(parts[3]) if len(parts) > 3 else 800)
            except ValueError:
                return
            if busy or ctl["parked"] or parts[1] not in JOG_DIR or rate not in JOG_PX_S:
                return
            now = time.monotonic()
            self._jog = (parts[1], rate, now + min(max(hold, 100), 2000) / 1000.0, now)
        elif what == "halt":
            self._jog = None
        elif what in ("park", "home"):
            self._jog = None
            if self._working() and self.session.sm.state.name in _MOUNT_BUSY:
                return                                   # com um modo usando a montagem, não
            x, y = self.sky.world_w / 2.0, self.sky.world_h * (0.12 if what == "park" else 0.5)
            self.mount.cx, self.mount.cy = float(x), float(y)
            ctl.update(parked=(what == "park"))
            if what == "park":
                self._set_tracking(False)
        elif what == "unpark":
            ctl.update(parked=False)
            self._set_tracking(True)
        elif what == "tracking" and len(parts) == 2 and parts[1] in ("on", "off"):
            if not ctl["parked"]:
                self._set_tracking(parts[1] == "on")
        else:
            return
        self._publish_mount()
        self._refresh_frame()

    def _set_tracking(self, on: bool):
        """Sem rastreio o céu escorrega pelo campo: no simulador, a deriva cresce."""
        self._mount_ctl["tracking"] = bool(on)
        self.mount.drift = self._drift0 if on else self._drift0 * 30.0

    def _jog_step(self, now: float) -> bool:
        """Um passo do movimento manual; devolve se ainda está andando. Passou do prazo sem o
        comando ser renovado: para."""
        jog = self._jog
        if jog is None:
            return False
        direction, rate, deadline, last = jog
        if now >= deadline:
            self._halt_jog()
            return False
        dt = min(max(now - last, 0.0), 0.3)
        dx, dy = JOG_DIR[direction]
        step = JOG_PX_S[rate] * dt
        mx, my = self.cfg.width / 2.0, self.cfg.height / 2.0
        self.mount.cx = float(min(max(self.mount.cx + dx * step, mx), self.sky.world_w - mx))
        self.mount.cy = float(min(max(self.mount.cy + dy * step, my), self.sky.world_h - my))
        self._jog = (direction, rate, deadline, now)
        self._publish_mount()
        self._refresh_frame()
        return True

    # -- troca de modo ---------------------------------------------------------
    def _start(self, spec: str, tag: str | None = None):
        self.session.stop = True                         # encerra o modo atual
        w = self._worker
        for _ in range(40):                              # espera o worker MORRER (até ~8s)
            if not (w and w.is_alive()):
                break
            w.join(timeout=0.2)
        self.session.stats["job"] = tag                  # de qual comando é o estado a seguir
        parts = spec.split(":")
        self._jog = None                                 # um modo novo encerra o movimento manual
        if parts[0] not in ("preview", "focus") and self._mount_ctl["parked"]:
            self._mount_ctl["parked"] = False            # apontar tira a montagem do repouso
            self._set_tracking(True)
        self._publish_mount()
        self.session.stats["planet"] = None              # a captura planetária é de um modo só
        self.session.reset_state()                       # só então reinicia (evita órfão revivido)
        self._worker = threading.Thread(
            target=self._run_mode, args=(parts[0], parts[1] if len(parts) > 1 else None, tag),
            daemon=True)
        self._worker.start()

    def _cam(self):
        return SkyCameraSource(self.sky, self.mount, self.focuser,
                               view_w=self.cfg.width, view_h=self.cfg.height)

    def _targets(self):
        meta = {"M31": (3, "galaxy"), "M42": (2, "nebula"), "M45": (1, "galaxy")}
        return [Target(n, self.sky.targets[n], frames=60, priority=p,
                       filter=filter_for_target(k)) for n, (p, k) in meta.items()]

    def _xy_for(self, name):
        """Onde o alvo fica no céu SIMULADO. Os três alvos do simulador têm lugar marcado; os
        demais ganham um campo próprio a partir das coordenadas reais (o inverso da conta que
        o `Session._build_wcs` faz), para alvos diferentes não mostrarem o mesmo céu."""
        if name in self.sky.targets:
            return self.sky.targets[name]
        try:
            from .catalog import find
            o = find(name)
        except Exception:
            o = None
        if o is None:
            return self.sky.targets["M31"]
        mx, my = self.cfg.width / 2.0, self.cfg.height / 2.0
        x = (o.ra_deg % 360.0) / 360.0 * self.sky.world_w
        y = (max(-60.0, min(60.0, o.dec_deg)) / 120.0 + 0.5) * self.sky.world_h
        return (float(min(max(x, mx), self.sky.world_w - mx)),
                float(min(max(y, my), self.sky.world_h - my)))

    def _run_plan(self):
        """O plano da noite (app): percorre a fila NA ORDEM em que o dono a deixou, e conta o
        que aconteceu com cada item — é o que a tela "noite em andamento" mostra. Falha num
        alvo não derruba a noite; `skip` pula o alvo atual; `stop` encerra tudo.

        Item: {"id", "target", "frames" (0 = até pular), "type", "mosaic": [linhas, colunas],
        "skip": motivo para nem tentar (ou None)}.
        """
        s = self.session
        items = list(self.plan_provider() if self.plan_provider else [])
        report = [{"id": it.get("id"), "target": it.get("target", ""), "status": "pending",
                   "accepted": 0, "snr": 0.0, "reason": ""} for it in items]
        total = len(items)

        def publish(i=None, **fields):
            nonlocal report
            if i is not None:                             # lista NOVA: o hub guarda cópia rasa
                report = report[:i] + [dict(report[i], **fields)] + report[i + 1:]
            s.stats.update(plan=report)
            s._publish()

        s.source = self._cam()
        s.stats.update(queue_done=0, queue_total=total)
        publish()
        done = 0
        for i, it in enumerate(items):
            if s.stop:
                break
            if it.get("skip"):                           # já se sabe que não dá (ex.: não sobe)
                done += 1
                publish(i, status="skipped", reason=str(it["skip"]))
                continue
            s.skip = False
            s._set_state(State.SCHEDULING)
            name = str(it.get("target") or "")
            s.stats.update(target=name, queue_done=done, queue_total=total,
                           accepted=0, rejected=0, snr=0.0)
            publish(i, status="running")
            if s.filterwheel is not None:
                s.set_filter(filter_for_target(it.get("type") or "galaxy"))
            rows, cols = (max(1, int(v)) for v in (list(it.get("mosaic") or ()) + [1, 1])[:2])
            cx, cy = self._xy_for(name)
            panels = (panel_centers(cx, cy, rows, cols, 300) if rows * cols > 1
                      else [(name, (cx, cy))])
            accepted, snr, status, reason = 0, 0.0, "done", ""
            for panel, xy in panels:
                if s.stop or s.skip:
                    break
                if not s.auto_find(xy):
                    if not (s.stop or s.skip):
                        status, reason = "failed", "not_found"
                    break
                s.autofocus()
                if s.stop or s.skip:
                    break
                label = name if len(panels) == 1 else f"{name}_{panel}"
                st = s.run_stack(frames=int(it.get("frames") or 0), label=label)
                accepted += int(st.get("accepted") or 0)
                snr = float(st.get("snr") or 0.0)
            if s.stop:
                status, reason = "stopped", ""
            elif s.skip:
                status, reason = "skipped", "user"
            if status != "stopped":
                done += 1
            publish(i, status=status, reason=reason, accepted=accepted, snr=snr)
            if not s.stop and s.sm.state is not State.SCHEDULING:
                s._set_state(State.SCHEDULING)
        s.skip = False
        s.stats.update(queue_done=done, queue_total=total)
        if not s.stop and s.sm.state is not State.IDLE:      # plano vazio já está em IDLE
            s._set_state(State.IDLE)

    # -- alinhamento polar e captura planetária (simulados) ----------------------
    def _polar_cmd(self, parts):
        """`polar:adjust:<altitude>:<azimute>` (minutos de arco): os parafusos da montagem de
        mentira. A última medida deixa de valer: é preciso medir de novo."""
        if len(parts) != 3 or parts[0] != "adjust":
            return
        try:
            d_alt, d_az = float(parts[1]), float(parts[2])
        except ValueError:
            return
        if not (abs(d_alt) <= 600 and abs(d_az) <= 600):  # também barra NaN
            return
        self.polar_axis.adjust(d_alt, d_az)
        last = self.session.stats.get("polar")
        if last:
            self.session.stats.update(polar=dict(last, stale=True))
            self.session._publish()

    def _run_polar(self):
        """Alinhamento polar por três pontos: gira a ascensão reta, reconhece o céu em cada
        parada e mede o quanto o eixo da montagem erra o polo (`control/polar_align`). Aqui a
        montagem é a de mentira; com a real, muda só de onde vêm os três campos."""
        s = self.session
        axis = self.polar_axis
        if self.latitude_provider is not None:
            axis.lat = float(self.latitude_provider())
        s.source = self._cam()
        points, total = [], 3
        s.stats.update(target="alinhamento polar",
                       polar={"step": 0, "points": total, "measured": False})
        for i, rotation in enumerate((0.0, 45.0, 90.0)):
            if s.stop:
                return
            s._set_state(State.SLEWING)                  # gira só a ascensão reta
            s._pace(0.8)
            if s.stop:
                return
            s._set_state(State.SOLVING)
            frame, _ = s.source.read()
            points.append(axis.solve(rotation))
            s.stats.update(polar={"step": i + 1, "points": total, "measured": False})
            s._publish(frame)
            s._pace(0.6)
        error = polar_error(points, axis.lat)
        if error is None:
            s.stats.update(outcome="polar_failed",
                           polar={"step": total, "points": total, "measured": False})
        else:
            s.stats.update(polar=dict(error.as_dict(), step=total, points=total, measured=True,
                                      stale=False, lat=round(axis.lat, 2)))
        s._publish()
        s._set_state(State.STOPPED)                      # mediu: a montagem fica parada, como no goto

    def _run_planetary(self, arg):
        """Captura planetária (lucky imaging), no simulador: grava muitos quadros curtos, fica
        com os mais nítidos CONFORME CHEGAM (o vídeo inteiro não cabe na memória da Jetson),
        alinha, empilha e aguça. `arg`: "corpo|quadros|percentual[|ra|dec]"; com as coordenadas,
        aponta e centraliza antes."""
        import heapq

        import cv2
        import numpy as np

        from ..planetary.lucky import sharpness
        from ..planetary.simulator import PlanetSimulator
        from ..planetary.stack import lucky_stack
        from ..util.imageio import encode_jpeg
        s = self.session
        parts = (arg or "jupiter").split("|")
        body = parts[0] or "jupiter"
        total = max(10, min(int(parts[1]) if len(parts) > 1 else 300, 5000))
        keep = max(1, min(int(parts[2]) if len(parts) > 2 else 15, 100)) / 100.0
        if len(parts) > 4 and not self._run_goto(f"@{parts[3]},{parts[4]}", final=False, label=body):
            return
        kind = "moon" if body in ("moon", "mercury") else "jupiter"
        sim = PlanetSimulator(size=240, radius=100 if kind == "moon" else 84, kind=kind, seed=7,
                              jitter=6.0, seeing=(0.5, 3.4), noise=5.0, color=True)
        want = max(1, round(total * keep))
        best = []                                        # os `want` mais nítidos até agora

        def publish(image, **fields):
            s.stats.update(planet=dict(s.stats.get("planet") or {}, **fields))
            if self.hub is not None:
                self.hub.update(encode_jpeg(image, stretch=False), s.stats)

        s._set_state(State.CAPTURING)
        s.stats.update(target=body, accepted=0, rejected=0,
                       planet={"body": body, "frames": 0, "total": total, "kept": 0,
                               "keep": keep, "done": False})
        for i in range(1, total + 1):
            if s.stop:
                return
            frame, _ = sim.frame()
            if i == 1:                                   # só agora se sabe o tamanho de um quadro
                want = max(1, min(want, PLANET_BUDGET_BYTES // max(int(frame.nbytes), 1)))
            score = float(sharpness(frame))
            if len(best) < want:
                heapq.heappush(best, (score, i, frame))  # o índice desempata: nunca compara imagens
            elif score > best[0][0]:
                heapq.heapreplace(best, (score, i, frame))
            if i % 5 == 0 or i == total:
                publish(frame, frames=i, kept=len(best))
            if self.hub is not None and s.pace:
                time.sleep(0.01)                         # o ritmo de uma câmera rápida
        s._set_state(State.STACKING)
        result = lucky_stack([f for _, _, f in sorted(best, key=lambda t: t[1])], keep=1.0)
        if s.stop:                                       # pararam enquanto empilhava: o resultado
            return                                       # não é mais deste comando, nada é gravado
        final = np.clip(result.image, 0, 255).astype(np.uint8)
        os.makedirs(self.cfg.out_dir, exist_ok=True)
        cv2.imwrite(os.path.join(self.cfg.out_dir, f"planet_{body}.png"),
                    cv2.cvtColor(final, cv2.COLOR_RGB2BGR) if final.ndim == 3 else final)
        s.stats.update(accepted=result.used, rejected=total - result.used)
        publish(final, frames=total, kept=result.used, done=True)
        s._set_state(State.IDLE)

    def _run_mode(self, mode, arg, tag=None):
        s = self.session
        tgt = self._xy_for(arg or "M31")
        try:
            if mode == "stack":
                self.mount.slew(*tgt); self.focuser.move_to(6300)
                s.source = self._cam(); s.run_stack(frames=0)
            elif mode == "autofind":
                self.focuser.move_to(4200)
                s.source = self._cam(); s.run_autonomous(tgt)
            elif mode == "goto":
                self._run_goto(arg or "M31")
            elif mode == "observe":
                # A "noite rápida" do app: aponta, centraliza e empilha — um comando só, para
                # a sequência seguir na Jetson mesmo que o celular perca o sinal. Só empilha
                # se o alvo foi centralizado.
                if self._run_goto(arg or "M31", final=False):
                    self.mount.slew(*tgt); self.focuser.move_to(6300)
                    s.stats.update(target=arg or "M31")
                    s.run_stack(frames=0)
            elif mode == "preview":
                # A câmera ao vivo, sem apontar e sem empilhar: é a tela de enquadrar e focar.
                s.source = self._cam(); s.run_preview()
            elif mode == "focus":
                s.source = self._cam()
                if not s.autofocus() and not s.stop:
                    s.stats.update(outcome="focus_failed")
            elif mode == "plan":
                self._run_plan()
            elif mode == "polar":
                self._run_polar()
            elif mode == "planetary":
                self._run_planetary(arg)
            elif mode == "realdata":
                self._run_realdata()
            elif mode == "scheduler":
                s.source = self._cam(); Scheduler(s).run(self._targets())
            elif mode == "mosaic":
                s.source = self._cam(); Mosaic(s).run(tgt, rows=2, cols=2, frames_per_panel=40)
            elif mode == "tracking":
                self.mount.cx, self.mount.cy, self.mount.rot = 3000.0, 2200.0, 0.0
                scene = SatelliteScene(self.sky, self.mount, obj0=(3000.0, 2200.0), vel=(4.0, 2.0),
                                       view_w=self.cfg.width, view_h=self.cfg.height)
                s.track(scene, YoloTensorRTDetector(), frames=10 ** 9)
            elif mode == "night":
                s.source = self._cam()
                AutonomousNight(s).run([
                    Observation("M31", self.sky.targets["M31"], 40, "galaxy", priority=3),
                    Observation("M42", self.sky.targets["M42"], 40, "nebula", priority=2)])
        except Exception as e:
            print(f"[controller] erro no modo {mode!r}: {e}")
            if s.stats.get("job") == tag:                # um modo órfão não marca o seguinte como falho
                s.stats.update(outcome="error")
                s._publish()                             # o estado pode nem ter saído de IDLE
        finally:
            # rede de seguranca: nenhum modo deixa o painel preso num estado nao-terminal
            if s.sm.state not in (State.STOPPED, State.IDLE):
                order = (State.STOPPED, State.IDLE) if s.stop else (State.IDLE, State.STOPPED)
                for target in order:
                    try:
                        s._set_state(target)
                        break
                    except Exception:
                        continue
            # como terminou — é o que avisa quem acompanha o comando (a API) de que acabou.
            # Só se o estado ainda é deste comando: um modo órfão não encerra o seguinte.
            if s.stats.get("job") == tag:
                if not s.stats.get("outcome"):
                    s.stats["outcome"] = "stopped" if s.stop else "ok"
                s._publish()

    def _run_realdata(self):
        """Roda o PIPELINE REAL sobre uma FOTO REAL (M67), mostrando cada etapa (T15).

        Encadeia na foto real as MESMAS peças que rodarão na Andrômeda com a câmera:
        foco (FWHM) -> detecção/registro/lucky-imaging -> empilhamento -> realce final."""
        import os
        from ..capture.real_source import RealFitsSource
        from ..gpu.quality import detect_stars, measure_fwhm
        from ..backend import asnumpy, backend_name
        s = self.session
        path = os.path.join(os.path.dirname(__file__), "..", "..",
                            "tests", "data", "real_starfield_m67.fits")
        if not os.path.exists(path):
            s.stats.update(phase="foto real ausente (rode scripts/fetch_real_data.py)")
            s._publish()
            s._set_state(State.STOPPED)
            return
        src = RealFitsSource(path, view_w=self.cfg.width, view_h=self.cfg.height)
        s.source = src
        old_fwhm = s.cfg.quality.max_fwhm_px
        old_enh = s.cfg.enhance
        s.cfg.quality.max_fwhm_px = 22.0                 # PSF real do M67 ~10px (o sim usa 5)
        s.cfg.enhance = True                             # realce final ligado
        s.stats.update(target="M67 (foto real)")
        try:
            # 1) FOCO — mede o FWHM na foto REAL (a mesma métrica do autofoco), na GPU
            s._set_state(State.FOCUSING)
            frame0, _ = src.read()
            g0 = asnumpy(frame0)
            stars, _ = detect_stars(g0, s.cfg.quality)
            fwhm = measure_fwhm(g0, stars, s.cfg.quality)
            s.stats.update(phase=f"foco: {len(stars)} estrelas reais, FWHM {fwhm:.1f}px [{backend_name()}]",
                           fwhm=round(fwhm, 2))
            s._publish(frame0)
            time.sleep(1.2)
            # 2+3+4) detecção -> registro -> lucky-imaging -> empilhamento -> realce (run_stack)
            s.run_stack(frames=30, label="M67_real")
            if not s.stop:
                s.stats.update(target=f"M67 REAL - {int(s.stats.get('accepted', 0))} subs empilhadas")
                s._publish()
        finally:
            s.cfg.quality.max_fwhm_px = old_fwhm
            s.cfg.enhance = old_enh

    def _radec_for(self, name):
        """RA/DEC do alvo: resolve no catálogo real (14k objetos); fallback nos alvos fixos.
        `@ra,dec` (graus) aponta direto para coordenadas, sem passar pelo catálogo."""
        if name.startswith("@"):
            ra, dec = (float(v) for v in name[1:].split(","))
            return (ra % 360.0, max(-90.0, min(90.0, dec)))
        try:
            from .catalog import find
            o = find(name)
            if o is not None:
                return (o.ra_deg, o.dec_deg)
        except Exception:
            pass
        return self.radec.get(name, self.radec["M31"])

    def _run_goto(self, name, final=True, label=None) -> bool:
        """Modo GOTO celeste (T16): aponta em RA/DEC fechando slew→solve→sync, ao vivo no painel.

        Devolve True se centralizou. `final=False`: é só a primeira parte de uma sequência
        (modo `observe`) — se deu certo, NÃO encerra: quem chamou segue para o empilhamento.
        `label`: o nome a mostrar quando `name` são coordenadas (a Lua, um planeta)."""
        from ..control.mount import SimRaDecMount
        from ..control.solver import SimRaDecSolver
        s = self.session
        ra, dec = self._radec_for(name)
        name = label or name
        rmount = SimRaDecMount(ra_deg=ra, dec_deg=dec, goto_err_arcmin=16.0)
        rsolver = SimRaDecSolver(rmount)
        s.source = self._cam()                       # campo estelar p/ o live view

        def on_state(st):
            s._set_state(State.SLEWING if st == "SLEWING" else State.SOLVING)
            time.sleep(0.6)                          # deixa a transição visível na UI

        def progress(i, err, wcs, frame):
            s.stats.update(target=f"{name} (RA/DEC)", error_px=round(err, 2), err_unit="arcmin")
            s._publish(frame)
            time.sleep(0.6)

        ok, err, iters = close_loop_goto(rmount, rsolver, (ra, dec), source=s.source,
                                         tol_arcmin=1.0, max_iters=8,
                                         on_state=on_state, progress=progress,
                                         should_stop=lambda: s.stop)
        centered = ok and not s.stop
        s.stats.update(phase=("OK alvo centralizado" if ok else "nao convergiu"),
                       target=f"{name}: {err:.2f} arcmin", error_px=round(err, 2))
        if not s.stop:
            print(f"[goto] {'OK centralizado' if ok else 'X nao convergiu'} "
                  f"{err:.2f} arcmin em {iters} iters")
        if final or not centered:
            s.stats.update(outcome=("stopped" if s.stop else "ok" if ok else "not_converged"))
            s._set_state(State.STOPPED)
        return centered
