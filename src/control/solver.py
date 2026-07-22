"""Plate solver — abstração unificada.

REUSO no hardware (docs/08 §2): NÃO escrevemos matcher de estrelas. O `AstapSolver` chama o
binário do ASTAP (grátis, local, sub-segundo); no Jetson pode-se usar cedar-solve (gRPC) igual.
O `SimSolver` é o substituto para a simulação: revela o apontamento REAL do céu (verdade do sim)
com ruído de medição — exatamente o que um solver faz, sem reimplementá-lo aqui.

Unidades: o `SimSolver` trabalha em PIXELS do mundo do simulador `(cx, cy, rot)`; o `AstapSolver`
resolve o céu REAL e devolve RA/DEC em GRAUS (`solve_wcs` → `WcsInfo`). A ponte pixel↔RA/DEC do
laço de auto-find no céu real é do bring-up de hardware (Milestone F). Ver docs/21.
"""
from __future__ import annotations
import numpy as np


class Solver:
    def solve(self, frame, hint=None):
        """Retorna (cx, cy, rot) em coords do céu, ou None se não resolveu."""
        raise NotImplementedError


class SimSolver(Solver):
    """Substituto de cedar-solve/ASTAP para simulação (verdade do céu + ruído)."""
    def __init__(self, mount, noise_px=1.5, seed=5):
        self.mount = mount
        self.noise = noise_px
        self.rng = np.random.default_rng(seed)

    def solve(self, frame=None, hint=None):
        cx, cy, rot = self.mount.pointing()
        return (cx + self.rng.normal(0, self.noise),
                cy + self.rng.normal(0, self.noise), rot)


class SimRaDecSolver(Solver):
    """Plate solver SIMULADO em RA/DEC — revela o apontamento REAL da SimRaDecMount + ruído.

    Análogo celeste do SimSolver: um plate solve descobre onde o telescópio REALMENTE aponta,
    não onde ele acha que aponta. Devolve um WcsInfo (graus). Dublê p/ validar o auto-find celeste
    (T16) sem ASTAP/índice de estrelas. Ver docs/22."""
    def __init__(self, mount, noise_arcsec=2.0, seed=11):
        self.mount = mount
        self.noise = noise_arcsec / 3600.0
        self.rng = np.random.default_rng(seed)

    def solve_wcs(self, frame=None, hint=None):
        from ..io.fits_io import WcsInfo
        return WcsInfo(ra_deg=(self.mount.true_ra + self.rng.normal(0, self.noise)) % 360.0,
                       dec_deg=self.mount.true_dec + self.rng.normal(0, self.noise),
                       pixscale_arcsec=2.0, rotation_deg=0.0)

    def solve(self, frame=None, hint=None):
        w = self.solve_wcs(frame, hint)
        return (w.ra_deg, w.dec_deg, w.rotation_deg)


# --------------------------------------------------------------------- ASTAP
def parse_astap_result(text: str):
    """Parseia a saída do ASTAP (arquivo .ini: KEY=VALUE) → WcsInfo | None.

    ASTAP grava, ao lado do FITS, um `.ini` com `PLTSOLVD=T` e o WCS (CRVAL1/2 em graus,
    CDELT/CROTA ou a matriz CD). Se não resolveu (`PLTSOLVD=F`/ausente), devolve None.
    Parser puro (testável com saída enlatada, sem ASTAP instalado).
    """
    from ..io.fits_io import WcsInfo
    kv = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(";") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        kv[key.strip().upper()] = val.strip()

    if kv.get("PLTSOLVD", "F").upper() not in ("T", "TRUE", "1"):
        return None

    def num(key):
        v = kv.get(key)
        if v is None:
            return None
        try:
            return float(v.split()[0].split("/")[0])   # 1º token (ignora comentário)
        except (ValueError, IndexError):
            return None

    ra, dec = num("CRVAL1"), num("CRVAL2")
    if ra is None or dec is None:
        return None

    # escala/rotação: preferir CDELT/CROTA; senão derivar da matriz CD
    cdelt2, crota2 = num("CDELT2"), num("CROTA2")
    if cdelt2 is not None:
        pixscale = abs(cdelt2) * 3600.0
        rot = crota2 if crota2 is not None else 0.0
    else:
        cd11, cd21 = num("CD1_1"), num("CD2_1")
        if cd11 is None or cd21 is None:
            return None
        pixscale = float(np.hypot(cd11, cd21)) * 3600.0
        rot = float(np.degrees(np.arctan2(cd21, cd11)))
    return WcsInfo(ra_deg=ra % 360.0, dec_deg=dec, pixscale_arcsec=pixscale, rotation_deg=rot)


class AstapSolver(Solver):
    """Plate solving REAL via ASTAP (grátis). Roda no PC de dev E na Jetson.

    Fluxo: salva o frame num FITS temporário → chama o ASTAP → lê o `.ini` gerado → WcsInfo.
    Requer o binário do ASTAP + um índice de estrelas (ex.: H18/D50) instalados. Sem eles,
    `solve` devolve None de forma limpa. `astap_bin` pode ser um caminho (str) ou um argv-prefixo
    (list) — útil para testes com um ASTAP falso. Ver docs/21.
    """
    def __init__(self, fov_deg=3.2, astap_bin="astap", search_radius_deg=10.0,
                 workdir=None, timeout=60):
        self.fov = fov_deg
        self.bin = list(astap_bin) if isinstance(astap_bin, (list, tuple)) else [astap_bin]
        self.radius = search_radius_deg
        self.workdir = workdir
        self.timeout = timeout

    def _cmd(self, fits_path, hint):
        cmd = self.bin + ["-f", fits_path, "-fov", repr(float(self.fov)),
                          "-r", repr(float(self.radius))]
        if hint is not None:                       # dica RA(h)/DEC(°) acelera muito
            cmd += ["-ra", repr(float(hint[0])), "-spd", repr(float(hint[1]) + 90.0)]
        return cmd

    def solve_wcs(self, frame, hint=None):
        """Resolve e devolve um WcsInfo (RA/DEC em graus) ou None."""
        import os
        import subprocess
        import tempfile
        from astropy.io import fits

        workdir = self.workdir or tempfile.mkdtemp(prefix="astap_")
        os.makedirs(workdir, exist_ok=True)
        path = os.path.join(workdir, "_solve.fits")
        base = os.path.splitext(path)[0]
        for ext in (".ini", ".wcs"):               # limpa resultados antigos
            try:
                os.remove(base + ext)
            except OSError:
                pass
        fits.PrimaryHDU(np.asarray(frame, dtype=np.float32)).writeto(path, overwrite=True)
        try:
            subprocess.run(self._cmd(path, hint), capture_output=True, timeout=self.timeout)
        except (FileNotFoundError, OSError, subprocess.SubprocessError):
            return None                            # ASTAP ausente/erro → falha limpa
        ini = base + ".ini"
        if not os.path.exists(ini):
            return None
        with open(ini, "r", encoding="utf-8", errors="replace") as f:
            return parse_astap_result(f.read())

    def solve(self, frame, hint=None):
        """Compat com o port: devolve (RA°, DEC°, rot°) — unidades celestes, não pixels."""
        w = self.solve_wcs(frame, hint)
        return None if w is None else (w.ra_deg, w.dec_deg, w.rotation_deg)
