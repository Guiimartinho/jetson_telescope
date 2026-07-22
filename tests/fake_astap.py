"""ASTAP FALSO (test double) — imita o binário do ASTAP para testar o AstapSolver na CI.

Invocado como `python fake_astap.py -f <img.fits> -fov F -r R [-ra H -spd SPD]`, grava um
`<img>.ini` no formato do ASTAP (PLTSOLVD=T + WCS). Se receber a dica -ra/-spd, "resolve" para
ela (roundtrip verificável); senão usa um campo padrão (região de M42). Não resolve nada de
verdade — só exercita o fluxo salvar-FITS → invocar → parsear. Ver docs/21.
"""
import os
import sys


def main(argv):
    args = {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("-") and i + 1 < len(argv):
            args[a] = argv[i + 1]
            i += 2
        else:
            i += 1

    fits_path = args.get("-f")
    if not fits_path:
        return 1

    if "-ra" in args and "-spd" in args:
        ra_deg = (float(args["-ra"]) * 15.0) % 360.0        # ASTAP -ra é em HORAS
        dec_deg = float(args["-spd"]) - 90.0                # -spd = DEC + 90
    else:
        ra_deg, dec_deg = 83.8221, -5.3911                  # padrão: perto de M42

    ini = os.path.splitext(fits_path)[0] + ".ini"
    with open(ini, "w", encoding="utf-8") as f:
        f.write("PLTSOLVD=T\n")
        f.write(f"CRVAL1={ra_deg:.6f}\n")                   # RA do centro (graus)
        f.write(f"CRVAL2={dec_deg:.6f}\n")                  # DEC do centro (graus)
        f.write("CRPIX1=512.0\n")
        f.write("CRPIX2=384.0\n")
        f.write("CDELT1=-0.000555556\n")                    # ~2 arcsec/px
        f.write("CDELT2=0.000555556\n")
        f.write("CROTA1=1.5\n")
        f.write("CROTA2=1.5\n")                             # twist do campo (graus)
        f.write("FOV_H=1.0\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
