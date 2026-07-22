"""T16 — Auto-find celeste em malha fechada (RA/DEC): o "apontar sozinho".

Este é o cérebro do apontamento automático (o que faz a DWARF achar o alvo). Fecha o laço em
COORDENADAS CELESTES, não nos pixels do simulador:

    alvo (RA°,DEC°) ─► slew ─► captura ─► PLATE SOLVE (RA°,DEC° reais) ─► erro angular
                        ▲                                                     │
                        └──────────── sync (corrige o modelo) ◄──────────────┘  (repete até centrar)

Funciona com qualquer `mount` que exponha `goto/sync/position` em GRAUS (SimRaDecMount OU IndiMount)
e qualquer `solver` com `solve_wcs(frame) -> WcsInfo` (SimRaDecSolver OU AstapSolver). No PC roda com
os dublês; na Jetson, os MESMOS argumentos viram INDI + ASTAP, sem tocar neste laço. Ver docs/22.
"""
from __future__ import annotations
import numpy as np


def angular_sep_arcmin(a, b) -> float:
    """Separação angular (arcmin) entre (RA°,DEC°) a e b — haversine (correto perto dos polos)."""
    ra1, dec1 = np.radians(a[0]), np.radians(a[1])
    ra2, dec2 = np.radians(b[0]), np.radians(b[1])
    h = (np.sin((dec2 - dec1) / 2) ** 2
         + np.cos(dec1) * np.cos(dec2) * np.sin((ra2 - ra1) / 2) ** 2)
    return float(np.degrees(2 * np.arcsin(min(1.0, np.sqrt(h)))) * 60.0)


def close_loop_goto(mount, solver, target_deg, source=None, tol_arcmin=1.0, max_iters=6,
                    on_state=None, progress=None, should_stop=None):
    """Aponta para `target_deg=(RA°,DEC°)` fechando o laço slew→solve→sync.

    Retorna (ok, err_arcmin, iters). `on_state(str)` recebe 'SLEWING'/'SOLVING' (p/ a UI);
    `progress(i, err_arcmin, wcs, frame)` a cada iteração; `should_stop()` aborta.
    """
    ra_t, dec_t = float(target_deg[0]), float(target_deg[1])
    err = float("inf")
    for i in range(max_iters):
        if should_stop and should_stop():
            break
        if on_state:
            on_state("SLEWING")
        mount.goto(ra_t, dec_t)                       # GOTO 'bruto' (cai deslocado)
        if should_stop and should_stop():
            break
        if on_state:
            on_state("SOLVING")
        frame = source.read()[0] if source is not None else None
        wcs = solver.solve_wcs(frame)                 # plate solve → onde REALMENTE aponta
        if wcs is None:                               # não resolveu: tenta de novo
            continue
        err = angular_sep_arcmin((ra_t, dec_t), (wcs.ra_deg, wcs.dec_deg))
        if progress:
            progress(i, err, wcs, frame)
        if err <= tol_arcmin:                         # centralizado
            return True, err, i + 1
        mount.sync(wcs.ra_deg, wcs.dec_deg)           # corrige o modelo → próximo GOTO acerta
    return (err <= tol_arcmin), err, max_iters
