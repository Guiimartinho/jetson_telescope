"""Orquestrador da sessão (Fases 1 e 2).

Fase 1: laço de live stacking (fonte → FWHM → registro → stacker → live view).
Fase 2: adiciona a autonomia — AUTO-FIND (slew→solve→corrige→centraliza) e AUTOFOCO,
antes do laço de stacking, sem tocar no núcleo. Componentes de controle (mount/focuser/
solver) são INJETADOS: SimMount/SimFocuser/SimSolver no PC; INDI/ASTAP na Jetson.
Ver docs/08-reusar-vs-construir.md.
"""
from __future__ import annotations
import os
import time

import numpy as np

from ..backend import backend_name, asnumpy, sync
from ..capture.source import build_source
from ..capture.ring_buffer import RingBuffer
from ..gpu import debayer as _debayer
from ..gpu.calibration import Calibrator
from ..gpu.quality import assess
from ..gpu.registration import estimate_transform, warp, HAS_ASTROALIGN
from ..gpu.stacker import LiveStacker
from ..control.autofocus import AutoFocuser
from ..util.imageio import save_png, encode_jpeg, robust_std
from ..io.fits_io import save_fits, WcsInfo, HAS_ASTROPY
from .config import SessionConfig
from .state import State, SessionStateMachine


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        return 0.299 * frame[..., 0] + 0.587 * frame[..., 1] + 0.114 * frame[..., 2]
    return frame


class Session:
    def __init__(self, cfg: SessionConfig, hub=None, source=None,
                 mount=None, focuser=None, solver=None, calibrator=None, filterwheel=None):
        self.cfg = cfg
        self.hub = hub
        self.source = source
        self.mount = mount
        self.focuser = focuser
        self.solver = solver
        self.calibrator = calibrator
        self.filterwheel = filterwheel
        self.last_solution = None          # (cx, cy, rot) do último plate solve (p/ WCS)
        self.stop = False
        self.sm = SessionStateMachine()
        self.stats = dict(backend=backend_name(), reuse_astroalign=HAS_ASTROALIGN,
                          phase=State.IDLE.label, state=State.IDLE.name,
                          accepted=0, rejected=0, fwhm=0.0, snr=0.0,
                          error_px=0.0, focus_pos=0,
                          target="", queue_done=0, queue_total=0, filter="")

    # ------------------------------------------------------------------ infra
    def _set_state(self, st: State):
        self.sm.to(st)
        self.stats.update(phase=st.label, state=st.name)
        self._publish()          # empurra o estado novo pro hub -> o painel atualiza na hora
                                 # (sem isso, /stats fica preso no ultimo frame empilhado)

    def set_filter(self, name: str):
        if self.filterwheel is not None:
            self.filterwheel.set(name)
            self.stats.update(filter=name)
            print(f"[filtro] -> {name}")

    def _poll_commands(self):
        """Consome comandos vindos da UI web (ex.: 'stop')."""
        if self.hub is not None:
            for c in self.hub.pop_commands():
                if c == "stop":
                    print("\n[web] comando 'parar' recebido")
                    self.stop = True

    def reset_state(self):
        """Reinicia a máquina de estados e as métricas para um novo modo (usado pelo painel).
        STOPPED é terminal, então trocar de modo exige uma máquina nova."""
        self.sm = SessionStateMachine()
        self.stop = False
        self.last_solution = None
        self.stats.update(phase=State.IDLE.label, state=State.IDLE.name,
                          accepted=0, rejected=0, snr=0.0, error_px=0.0, err_unit="px",
                          target="", queue_done=0, queue_total=0)
        self._publish()          # reflete o IDLE no painel imediatamente

    def _get_source(self):
        if self.source is None:
            # garante que o simulador tem as mesmas dimensões do pipeline
            self.cfg.sim.width, self.cfg.sim.height = self.cfg.width, self.cfg.height
            self.source = build_source(self.cfg.source, sim_cfg=self.cfg.sim,
                                       device=self.cfg.indi_device,
                                       exposure_s=self.cfg.indi_exposure_s,
                                       gain=self.cfg.indi_gain)
        return self.source

    def _publish(self, image=None):
        if self.hub is None:
            return
        self.hub.update(encode_jpeg(image) if image is not None else b"", self.stats)

    def _build_wcs(self):
        """WcsInfo a partir do último plate solve (mapeia o mundo do sim → RA/DEC plausível).
        No hardware, o AstapSolver dá RA/DEC reais → WcsInfo direto."""
        sol = self.last_solution
        sky = getattr(self.source, "sky", None)
        if sol is None or sky is None:
            return None
        cx, cy, rot = sol
        ra = (cx / sky.world_w) * 360.0 % 360.0
        dec = max(-89.0, min(89.0, (cy / sky.world_h - 0.5) * 120.0))
        return WcsInfo(ra_deg=ra, dec_deg=dec, pixscale_arcsec=2.9, rotation_deg=float(rot))

    # -------------------------------------------------------------- FASE 2 (A)
    def auto_find(self, target_xy, tol_px=8.0, max_iters=12) -> bool:
        """Laço de plate solving: aponta, resolve, corrige, repete até centralizar."""
        src = self._get_source()
        tx, ty = target_xy
        if self.mount is not None:
            self._set_state(State.SLEWING)
            self.mount.slew(tx, ty)                     # GOTO 'bruto' (erra)
        self._set_state(State.SOLVING)
        print(f"\n[auto-find] alvo em ({tx:.0f},{ty:.0f}) - iniciando laco slew->solve->corrige")
        for it in range(max_iters):
            self._poll_commands()
            if self.stop:
                self._set_state(State.STOPPED)
                return False
            frame, _ = src.read()
            sol = self.solver.solve(frame) if self.solver is not None else None
            if sol is None:
                continue
            self.last_solution = sol                    # guarda p/ o WCS do FITS
            ex, ey = sol[0] - tx, sol[1] - ty
            err = float(np.hypot(ex, ey))
            self.stats.update(iter=it + 1, error_px=round(err, 1))
            self._publish(frame)
            print(f"[auto-find] iter {it+1:2d}: erro = {err:6.1f} px")
            if err <= tol_px:
                print(f"[auto-find] OK alvo centralizado (erro {err:.1f} px)")
                return True
            if self.mount is not None:
                self.mount.nudge(-ex, -ey)              # correção fina
            if self.hub is not None:
                time.sleep(0.25)                        # ritmo p/ ver ao vivo (só com live view)
        print("[auto-find] X nao convergiu")
        return False

    # -------------------------------------------------------------- FASE 2 (D)
    def autofocus(self):
        if self.focuser is None:
            return
        src = self._get_source()
        self._set_state(State.FOCUSING)
        print("\n[autofoco] varrendo o focalizador…")

        def _prog(pos, fwhm, frame):
            self.stats.update(focus_pos=int(pos),
                              fwhm=round(fwhm, 2) if np.isfinite(fwhm) else 0.0)
            self._publish(frame)
            print(f"[autofoco] pos={pos:5d}  FWHM={fwhm:.2f}")
            if self.hub is not None:
                time.sleep(0.18)                        # ritmo p/ ver ao vivo (só com live view)

        af = AutoFocuser(src, self.focuser, self.cfg.quality)
        best, achieved, _ = af.run(progress=_prog, should_stop=lambda: self.stop)
        self.stats.update(focus_pos=int(best),
                          fwhm=round(achieved, 2) if np.isfinite(achieved) else 0.0)
        print(f"[autofoco] OK foco critico em {best} (FWHM {achieved:.2f})")

    # ----------------------------------------------------------- laço de stack
    def run_stack(self, frames=None, label=""):
        cfg = self.cfg
        n_frames = cfg.frames if frames is None else frames
        tag = label or "final"
        os.makedirs(cfg.out_dir, exist_ok=True)
        src = self._get_source()
        ring = RingBuffer(slots=8, shape=(cfg.height, cfg.width))
        calib = self.calibrator or Calibrator()
        stacker = LiveStacker()
        ref_stars = ref_shape = first_single = None
        accepted = rejected = 0
        add_time = 0.0
        self._set_state(State.STACKING)
        print(f"\n[stack] backend {backend_name()} · registro "
              f"{'astroalign' if HAS_ASTROALIGN else 'cv2'} · "
              f"{n_frames or 'live (Ctrl+C)'} frames"
              f"{f' · alvo {label}' if label else ''}\n")

        i = 0
        t0 = time.time()
        while not self.stop and (n_frames == 0 or i < n_frames):
            self._poll_commands()
            if self.stop:
                break
            raw, _ = src.read(out=ring.acquire())
            frame = _debayer.debayer(raw, src.bayer) if getattr(src, "is_color", False) else raw
            frame = calib.apply(frame)                 # calibra e FICA na GPU (xp)
            gray = asnumpy(_to_gray(frame))            # baixa só o cinza (1×) p/ detecção CPU

            q = assess(gray, cfg.quality)
            if not q["accepted"]:
                rejected += 1
                self.stats.update(rejected=rejected)
                self._publish()
                i += 1
                continue

            if ref_stars is None:
                ref_stars, ref_shape = q["stars"], frame.shape
                warped, mask = frame, None
            else:
                M = estimate_transform(q["stars"], ref_stars)
                if M is None:
                    rejected += 1
                    self.stats.update(rejected=rejected)
                    self._publish()
                    i += 1
                    continue
                warped, mask = warp(frame, M, ref_shape)

            ta = time.time()
            stacker.add(warped, q["weight"], mask)
            sync()
            add_time += time.time() - ta
            accepted += 1
            if first_single is None:
                first_single = asnumpy(warped).copy()

            result = stacker.result()
            snr = robust_std(first_single) / max(robust_std(result), 1e-6)
            self.stats.update(accepted=accepted, rejected=rejected,
                              fwhm=round(q["fwhm"], 2), snr=round(snr, 2))
            self._publish(result)
            if accepted % cfg.save_every == 0:
                save_png(os.path.join(cfg.out_dir, f"stack_{tag}_{accepted:04d}.png"), result)
            i += 1

        elapsed = time.time() - t0
        if stacker.n and first_single is not None:
            final = stacker.result()
            save_png(os.path.join(cfg.out_dir, f"single_{tag}.png"), first_single)
            save_png(os.path.join(cfg.out_dir, f"stack_{tag}.png"), final)
            if HAS_ASTROPY:
                try:
                    from datetime import datetime, timezone
                    save_fits(os.path.join(cfg.out_dir, f"stack_{tag}.fits"), final,
                              wcs=self._build_wcs(),
                              meta={"OBJECT": (label or "campo")[:8], "IMAGETYP": "LIGHT",
                                    "NCOMBINE": accepted, "STACKCNT": accepted, "BACKEND": "GPU",
                                    "DATE-OBS": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                except Exception as e:                  # FITS é opcional; não derruba a sessão
                    print(f"[fits] aviso: {e}")
            snr = robust_std(first_single) / max(robust_std(final), 1e-6)
            print("\n" + "=" * 60)
            print(f"Aceitos {accepted} · Rejeitados {rejected} · "
                  f"Ganho de SNR {snr:.2f}x (~raiz(N)={accepted**0.5:.2f}x)")
            print(f"add()/frame {1000*add_time/max(accepted,1):.2f} ms · total {elapsed:.1f}s")
            print("=" * 60)
            if cfg.enhance:                            # T2 — pós-processo no frame final
                from ..postproc.enhance import enhance
                enhanced = enhance(final)
                save_png(os.path.join(cfg.out_dir, f"stack_{tag}_enh.png"), enhanced)
                self.stats.update(phase="realce final (remove gradiente)")
                self._publish(enhanced)                # mostra a imagem TRATADA no live view
            from .session_store import save_session     # T6 — resumo da sessão
            from datetime import datetime, timezone
            save_session(os.path.join(cfg.out_dir, f"session_{tag}.json"),
                         {"target": label or "campo", "accepted": accepted, "rejected": rejected,
                          "snr": round(snr, 3), "backend": backend_name(),
                          "filter": self.stats.get("filter", ""),
                          "when": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        # run_stack é bloco reutilizável (scheduler/mosaico chamam por alvo): NÃO força estado
        # terminal aqui. Quem encerra o modo (Controller._run_mode) é que evita o painel congelado.
        if self.stop and self.sm.state is not State.STOPPED:
            self._set_state(State.STOPPED)
        return self.stats

    # alias de compatibilidade (Fase 1)
    def run(self):
        return self.run_stack()

    # -------------------------------------------------- sequência autônoma completa
    def run_autonomous(self, target_xy):
        """AUTO-FIND → AUTOFOCO → LIVE STACK, tudo encadeado (como o DWARF faz)."""
        print(f"\n>>> SESSÃO AUTÔNOMA — alvo {target_xy}")
        ok = self.auto_find(target_xy)
        if self.stop:
            return self.stats
        if not ok:
            self._set_state(State.ERROR)
            print(">>> auto-find falhou — sessão abortada")
            return self.stats
        self.autofocus()
        if self.stop:
            return self.stats
        return self.run_stack()

    # -------------------------------------------------- FASE 4: rastreamento IA
    def track(self, source, detector, frames=200):
        """T10 — laço de rastreamento em tempo real: detecta o objeto, estima sua velocidade e
        corrige a montagem por **feed-forward** para mantê-lo centralizado. Retorna erros (px)."""
        self._set_state(State.TRACKING)
        ccx, ccy = self.cfg.width / 2.0, self.cfg.height / 2.0
        prev_world = None
        errors = []
        print(f"\n[tracking] rastreando objeto ({frames} frames)")
        for _ in range(frames):
            self._poll_commands()
            if self.stop:
                break
            frame, _ = source.read()
            det = detector.detect(frame)
            if det is None:
                self._publish(frame)
                continue
            mx, my, _ = self.mount.pointing()
            ex, ey = det[0] - ccx, det[1] - ccy
            errors.append(float(np.hypot(ex, ey)))
            obj_world = (det[0] - ccx + mx, det[1] - ccy + my)   # reconstrói pos do objeto
            vwx = vwy = 0.0
            if prev_world is not None:
                vwx, vwy = obj_world[0] - prev_world[0], obj_world[1] - prev_world[1]
            prev_world = obj_world
            self.mount.nudge(ex + vwx, ey + vwy)                 # proporcional + feed-forward
            self.stats.update(error_px=round(errors[-1], 1), target="objeto")
            self._publish(frame)
            if self.hub is not None:
                time.sleep(0.03)
        if errors:
            tail = errors[len(errors) // 2:]
            print(f"[tracking] erro médio (2ª metade): {sum(tail)/len(tail):.1f} px")
        if self.stop and self.sm.state is not State.STOPPED:
            self._set_state(State.STOPPED)
        return errors
