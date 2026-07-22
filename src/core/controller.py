"""Painel de controle: um servidor que roda QUALQUER modo sob demanda (via botões da UI).

Monta o mundo simulado uma vez e, a cada comando `start:<modo>[:<alvo>]`, para o modo atual e
inicia o novo numa thread. Modos: stack, autofind, scheduler, mosaic, tracking, night. `stop` para.
Assim dá para **testar tudo pelo navegador**. Ver docs/19.
"""
from __future__ import annotations
import threading
import time

from .orchestrator import Session
from .state import State
from .scheduler import Scheduler, Target
from .mosaic import Mosaic
from .autonomous import AutonomousNight, Observation
from ..control.autofind_radec import close_loop_goto
from ..capture.sky import SkyModel, SkyCameraSource
from ..capture.satellite import SatelliteScene
from ..control.mount import SimMount
from ..control.focuser import SimFocuser
from ..control.solver import SimSolver
from ..control.filterwheel import SimFilterWheel, filter_for_target
from ..control.detector import YoloTensorRTDetector


class Controller:
    def __init__(self, cfg, hub=None):
        self.cfg = cfg
        self.hub = hub
        self.sky = SkyModel(n_stars=4000)
        self.mount = SimMount(cx=self.sky.targets["M31"][0], cy=self.sky.targets["M31"][1])
        self.focuser = SimFocuser(position=4200, best=6300)
        self.session = Session(cfg, hub=hub, mount=self.mount, focuser=self.focuser,
                               solver=SimSolver(self.mount), filterwheel=SimFilterWheel())
        # RA/DEC reais (graus) dos alvos, p/ o auto-find celeste (modo goto — T16)
        self.radec = {"M31": (10.68, 41.27), "M42": (83.82, -5.39), "M45": (56.87, 24.10)}
        self._q, self._lock, self._worker = [], threading.Lock(), None

    # -- fila de comandos (chamada pela UI via /cmd) ---------------------------
    def submit(self, cmd: str):
        with self._lock:
            self._q.append(cmd)

    def dispatch(self, cmd: str):
        if cmd == "stop":
            self.session.stop = True
        elif cmd.startswith("start:"):
            self._start(cmd[len("start:"):])

    def start(self):
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while True:
            with self._lock:
                cmds, self._q = self._q, []
            for c in cmds:
                self.dispatch(c)
            time.sleep(0.1)

    # -- troca de modo ---------------------------------------------------------
    def _start(self, spec: str):
        self.session.stop = True                         # encerra o modo atual
        w = self._worker
        for _ in range(40):                              # espera o worker MORRER (até ~8s)
            if not (w and w.is_alive()):
                break
            w.join(timeout=0.2)
        self.session.reset_state()                       # só então reinicia (evita órfão revivido)
        parts = spec.split(":")
        self._worker = threading.Thread(
            target=self._run_mode, args=(parts[0], parts[1] if len(parts) > 1 else None),
            daemon=True)
        self._worker.start()

    def _cam(self):
        return SkyCameraSource(self.sky, self.mount, self.focuser,
                               view_w=self.cfg.width, view_h=self.cfg.height)

    def _targets(self):
        meta = {"M31": (3, "galaxy"), "M42": (2, "nebula"), "M45": (1, "galaxy")}
        return [Target(n, self.sky.targets[n], frames=60, priority=p,
                       filter=filter_for_target(k)) for n, (p, k) in meta.items()]

    def _run_mode(self, mode, arg):
        s = self.session
        tgt = self.sky.targets.get(arg or "M31", self.sky.targets["M31"])
        try:
            if mode == "stack":
                self.mount.slew(*tgt); self.focuser.move_to(6300)
                s.source = self._cam(); s.run_stack(frames=0)
            elif mode == "autofind":
                self.focuser.move_to(4200)
                s.source = self._cam(); s.run_autonomous(tgt)
            elif mode == "goto":
                self._run_goto(arg or "M31")
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
        """RA/DEC do alvo: resolve no catálogo real (14k objetos); fallback nos alvos fixos."""
        try:
            from .catalog import find
            o = find(name)
            if o is not None:
                return (o.ra_deg, o.dec_deg)
        except Exception:
            pass
        return self.radec.get(name, self.radec["M31"])

    def _run_goto(self, name):
        """Modo GOTO celeste (T16): aponta em RA/DEC fechando slew→solve→sync, ao vivo no painel."""
        from ..control.mount import SimRaDecMount
        from ..control.solver import SimRaDecSolver
        s = self.session
        ra, dec = self._radec_for(name)
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
        s.stats.update(phase=("OK alvo centralizado" if ok else "nao convergiu"),
                       target=f"{name}: {err:.2f} arcmin", error_px=round(err, 2))
        if not s.stop:
            print(f"[goto] {'OK centralizado' if ok else 'X nao convergiu'} "
                  f"{err:.2f} arcmin em {iters} iters")
        s._set_state(State.STOPPED)
