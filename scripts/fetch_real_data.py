#!/usr/bin/env python3
"""Baixa um campo estelar REAL e salva como fixture de teste (T15).

Fonte: photutils.datasets.load_star_image — um CCD REAL do aglomerado M67 (dado público,
astropy data server). Recorta o centro 512×512 (região densa) e grava em
tests/data/real_starfield_m67.fits. Rode uma vez; a fixture fica versionada e os testes
(tests/test_real_pipeline.py) rodam offline. Precisa de: pip install photutils (FOSS, BSD).

    py -3.11 scripts/fetch_real_data.py
"""
from __future__ import annotations
import os
import warnings

import numpy as np

OUT = os.path.join(os.path.dirname(__file__), "..", "tests", "data", "real_starfield_m67.fits")


def main():
    warnings.filterwarnings("ignore")
    from astropy.io import fits
    try:
        from photutils.datasets import load_star_image
    except ImportError:
        raise SystemExit("Instale o photutils: py -3.11 -m pip install photutils")

    img = np.asarray(load_star_image().data, dtype=np.float32)
    h, w = img.shape
    cy, cx = h // 2, w // 2
    crop = img[cy - 256:cy + 256, cx - 256:cx + 256].copy()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fits.PrimaryHDU(crop).writeto(OUT, overwrite=True)
    print(f">> salvo {os.path.normpath(OUT)}  {crop.shape}  "
          f"fundo~{np.median(crop):.0f}  pico~{crop.max():.0f}")


if __name__ == "__main__":
    main()
