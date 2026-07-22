#!/usr/bin/env python3
"""Atlas do telescópio — o que a NOSSA óptica consegue capturar, e o que está visível agora.

    py -3.11 run_catalog.py --lat -23.5 --lon -46.6       # São Paulo, agora
    py -3.11 run_catalog.py --find M51                    # resolve um alvo

Filtra ~14.000 objetos reais (OpenNGC) pelo campo de visão + magnitude do rig, e pela altitude no
horizonte. É a base do "escolher alvo" real do telescópio (o GOTO aponta com `catalog.find`). Ver docs/26.
"""
from __future__ import annotations
import argparse
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.core import catalog as cat


def main():
    ap = argparse.ArgumentParser(description="Atlas do telescópio (catálogo + óptica + visibilidade)")
    ap.add_argument("--lat", type=float, default=None, help="latitude do observador (graus)")
    ap.add_argument("--lon", type=float, default=None, help="longitude (graus)")
    ap.add_argument("--min-alt", type=float, default=25.0)
    ap.add_argument("--find", default=None, help="resolve um alvo por nome (ex.: M51, Andromeda)")
    ap.add_argument("--limit", type=int, default=25)
    a = ap.parse_args()

    if not cat.HAS_ONGC:
        raise SystemExit("pyongc não instalado. Rode: py -3.11 -m pip install pyongc")

    if a.find:
        o = cat.find(a.find)
        if o:
            print(f"{o.label}\n  RA={o.ra_deg:.4f}°  DEC={o.dec_deg:.4f}°  "
                  f"{o.kind}  mag {o.mag}  tam {o.size_arcmin}'")
        else:
            print(f"'{a.find}' não encontrado")
        return

    rig = cat.DEFAULT_RIG
    fw, fh = rig.fov_deg()
    print(f">> Rig: focal {rig.focal_mm:.0f}mm, abertura {rig.aperture_mm:.0f}mm, sensor IMX585")
    print(f">> Campo {fw:.2f}°x{fh:.2f}° · magnitude limite (empilhando) {rig.limiting_mag():.1f}\n")

    framable = cat.framable(cat.load(), rig)
    print(f">> {len(framable)} objetos CAPTURÁVEIS com esta óptica (de {len(cat.load())} do catálogo).")

    if a.lat is None or a.lon is None:
        print(">> Passe --lat e --lon para ver o que está visível AGORA no seu céu.")
        return

    from astropy.time import Time
    vis = cat.visible(framable, a.lat, a.lon, Time.now(), min_alt=a.min_alt)
    print(f">> {len(vis)} visíveis agora (>{a.min_alt:.0f}° acima do horizonte). Top {a.limit}:\n")
    print(f"   {'ALVO':16s} {'TIPO':22s} {'MAG':>5} {'TAM':>7}  NOME")
    for o in vis[:a.limit]:
        mag = f"{o.mag:.1f}" if o.mag is not None else "  ?"
        siz = f"{o.size_arcmin:.0f}'" if o.size_arcmin is not None else "   ?"
        print(f"   {o.name:16s} {o.kind:22s} {mag:>5} {siz:>7}  {o.common}")


if __name__ == "__main__":
    main()
