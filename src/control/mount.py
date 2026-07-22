"""Montagem — abstração que unifica montagem simulada e real (INDI).

REUSO no hardware: a AM3N/AM5N fala LX200 via `indi_lx200am5`; o IndiMount abaixo é
o adaptador. A SimMount modela uma montagem imperfeita: o GOTO erra por ~centenas de
px (erro mecânico) — é isso que o plate solving corrige em malha fechada. Também deriva
devagar (tracking imperfeito) para o live stacking ter o que alinhar.
Ver docs/08-reusar-vs-construir.md §2.
"""
from __future__ import annotations
import numpy as np


class Mount:
    def pointing(self):                 # -> (cx, cy, rot_deg)
        raise NotImplementedError

    def slew(self, cx, cy):             # aponta para um alvo (com erro, no sim)
        raise NotImplementedError

    def nudge(self, dcx, dcy):          # correção fina (do plate solving)
        raise NotImplementedError

    def connect(self):
        pass

    def close(self):
        pass


class SimMount(Mount):
    def __init__(self, cx=3000.0, cy=2200.0, rot=0.0, goto_err_px=170.0,
                 nudge_residual_px=4.0, drift_px=0.05, drift_rot_deg=0.008, seed=3):
        self.cx, self.cy, self.rot = cx, cy, rot
        self.goto_err = goto_err_px
        self.nudge_res = nudge_residual_px
        self.drift, self.drot = drift_px, drift_rot_deg
        self.rng = np.random.default_rng(seed)

    def tick(self):
        """Avança a deriva de tracking (1× por frame capturado)."""
        self.cx += self.drift
        self.cy += 0.5 * self.drift
        self.rot += self.drot

    def pointing(self):
        return (self.cx, self.cy, self.rot)

    def slew(self, cx, cy):
        """GOTO 'bruto': aponta perto do alvo, mas erra por erro mecânico."""
        self.cx = cx + self.rng.normal(0, self.goto_err)
        self.cy = cy + self.rng.normal(0, self.goto_err)
        self.rot += self.rng.normal(0, 0.3)

    def nudge(self, dcx, dcy):
        """Correção fina do laço de plate solving (com pequeno resíduo mecânico)."""
        self.cx += dcx + self.rng.normal(0, self.nudge_res)
        self.cy += dcy + self.rng.normal(0, self.nudge_res)


class SimRaDecMount:
    """Montagem SIMULADA em RA/DEC (graus) — dublê para validar o auto-find celeste (T16).

    Modela uma montagem com **erro de apontamento sistemático**: ela ACHA que aponta para o
    comando (`model`), mas de fato aponta com um offset (`err`) + ruído mecânico (`true`). O plate
    solve revela o `true`; o `sync` ensina o offset à montagem, corrigindo os GOTOs seguintes —
    exatamente o laço slew→solve→sync do céu real. Análogo celeste da SimMount. Ver docs/22.
    """
    def __init__(self, ra_deg=10.68, dec_deg=41.27, goto_err_arcmin=14.0,
                 noise_arcmin=0.25, seed=7):
        e = goto_err_arcmin / 60.0
        self.true_ra, self.true_dec = ra_deg, dec_deg
        self.model_ra, self.model_dec = ra_deg, dec_deg
        self.err_ra, self.err_dec = e, -0.7 * e          # offset sistemático (graus)
        self.noise = noise_arcmin / 60.0
        self.rng = np.random.default_rng(seed)

    def goto(self, ra_deg, dec_deg):
        """GOTO 'bruto': mira em (ra,dec) mas cai deslocado pelo erro do modelo + ruído."""
        self.model_ra, self.model_dec = ra_deg, dec_deg
        self.true_ra = ra_deg + self.err_ra + self.rng.normal(0, self.noise)
        self.true_dec = dec_deg + self.err_dec + self.rng.normal(0, self.noise)
        return self.position()

    def sync(self, ra_deg, dec_deg):
        """Ensina à montagem onde ela REALMENTE está (do plate solve) → corrige o offset."""
        self.err_ra -= (ra_deg - self.model_ra)
        self.err_dec -= (dec_deg - self.model_dec)
        self.model_ra, self.model_dec = ra_deg, dec_deg

    def position(self):
        return (self.model_ra, self.model_dec)


class IndiMount(Mount):
    """Montagem real via INDI usando o IndiClient puro-Python (PC de dev E Jetson).

    A montagem REAL trabalha em RA (horas) / DEC (graus) via EQUATORIAL_EOD_COORD, não nos
    pixels do simulador. Por isso a interface nativa é `slew_radec/sync_radec/get_radec`; os
    métodos em pixels do port (`slew/nudge/pointing`) não se aplicam ao hardware — no céu real
    quem fecha a malha é o plate solve em RA/DEC (Milestone F). Valida contra indi_simulator_telescope.
    """
    COORD = "EQUATORIAL_EOD_COORD"

    def __init__(self, device="Telescope Simulator", host="localhost", port=7624,
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
        cli.wait_vector(self.device, self.COORD, timeout=self._connect_timeout)
        self._connected = True
        return self

    def _ensure(self):
        if not self._connected:
            self.connect()

    def _coord_mode(self, mode):                 # SLEW | TRACK | SYNC
        others = [m for m in ("SLEW", "TRACK", "SYNC") if m != mode]
        self.client.send_switch(self.device, "ON_COORD_SET", on=mode, off=others)

    def slew_radec(self, ra_hours, dec_deg, track=True, timeout=60.0):
        """GOTO para RA(h)/DEC(°). Bloqueia até o vetor voltar a Ok (fim do slew)."""
        self._ensure()
        self._coord_mode("TRACK" if track else "SLEW")
        self.client.send_number(self.device, self.COORD,
                                {"RA": float(ra_hours), "DEC": float(dec_deg)})
        self.client.wait_state(self.device, self.COORD, "Ok", timeout=timeout)
        return self.get_radec()

    def sync_radec(self, ra_hours, dec_deg, timeout=10.0):
        """Sincroniza o modelo da montagem com RA/DEC conhecidos (após plate solve)."""
        self._ensure()
        self._coord_mode("SYNC")
        self.client.send_number(self.device, self.COORD,
                                {"RA": float(ra_hours), "DEC": float(dec_deg)})
        self.client.wait_state(self.device, self.COORD, "Ok", timeout=timeout)
        self._coord_mode("TRACK")

    def get_radec(self):
        self._ensure()
        p = self.client.get(self.device, self.COORD)
        return (None, None) if p is None else (p.elements.get("RA"), p.elements.get("DEC"))

    # -- interface RA/DEC em GRAUS (mesma do SimRaDecMount) p/ o laço de auto-find (T16) --
    # INDI usa RA em HORAS; convertemos na fronteira (graus/15). Assim o MESMO close_loop_goto
    # roda no simulador e no hardware. Ver docs/22.
    def goto(self, ra_deg, dec_deg):
        self.slew_radec(ra_deg / 15.0, dec_deg)
        return self.position()

    def sync(self, ra_deg, dec_deg):
        self.sync_radec(ra_deg / 15.0, dec_deg)

    def position(self):
        ra_h, dec = self.get_radec()
        return (None if ra_h is None else ra_h * 15.0, dec)

    def abort(self):
        self.client.send_switch(self.device, "TELESCOPE_ABORT_MOTION", on="ABORT")

    # -- port em pixels: conceito do simulador, não existe no hardware --------
    def pointing(self):
        raise NotImplementedError("IndiMount é RA/DEC; use get_radec() (pixels são do simulador)")

    def slew(self, cx, cy):
        raise NotImplementedError("IndiMount é RA/DEC; use slew_radec() (pixels são do simulador)")

    def nudge(self, dcx, dcy):
        raise NotImplementedError("IndiMount é RA/DEC; a correção fina é via sync_radec/slew_radec")

    def close(self):
        if self._own_client:
            self.client.close()
