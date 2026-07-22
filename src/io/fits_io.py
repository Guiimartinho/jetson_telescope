"""Saída/leitura FITS com WCS e metadados — reuso de astropy (docs/08).

Salva o stack final como FITS float32 com coordenadas (RA/DEC do plate solve) e header de
equipamento — abrível no Siril/PixInsight/ASTAP. Também lê FITS (subs reais no futuro).
Ver docs/15-fits-wcs.md.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np

from ..backend import asnumpy

try:
    from astropy.io import fits
    from astropy.wcs import WCS
    HAS_ASTROPY = True
except Exception:
    HAS_ASTROPY = False


@dataclass
class WcsInfo:
    """Solução astrométrica do centro da imagem."""
    ra_deg: float
    dec_deg: float
    pixscale_arcsec: float          # escala de placa (arcsec/px)
    rotation_deg: float = 0.0       # rotação do campo


def _wcs_header(w: WcsInfo, width: int, height: int):
    wcs = WCS(naxis=2)
    wcs.wcs.crpix = [width / 2.0 + 0.5, height / 2.0 + 0.5]   # pixel de referência = centro
    wcs.wcs.crval = [w.ra_deg, w.dec_deg]
    scale = w.pixscale_arcsec / 3600.0                        # deg/px
    rot = np.deg2rad(w.rotation_deg)
    # matriz CD (RA cresce para a esquerda -> sinal negativo em CD1_1)
    wcs.wcs.cd = scale * np.array([[-np.cos(rot), np.sin(rot)],
                                   [np.sin(rot), np.cos(rot)]])
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    return wcs.to_header()


def save_fits(path: str, image, wcs: WcsInfo | None = None, meta: dict | None = None):
    """Salva `image` (mono HxW ou cor 3xHxW) em FITS float32 com WCS + metadados."""
    if not HAS_ASTROPY:
        raise RuntimeError("astropy não instalado (pip install astropy)")
    data = asnumpy(image).astype(np.float32)
    if data.ndim == 3 and data.shape[2] == 3:      # HxWx3 -> 3xHxW (convenção FITS)
        data = np.moveaxis(data, 2, 0)
    h, w = data.shape[-2:]

    header = fits.Header()
    if wcs is not None:
        header.update(_wcs_header(wcs, w, h))
    header["SWCREATE"] = ("tele-jetson", "creation software")
    for key, val in (meta or {}).items():
        header[key[:8].upper()] = val              # cards FITS: chave <= 8 chars
    # (BITPIX/NAXIS são estruturais — o astropy os define a partir dos dados)

    fits.PrimaryHDU(data=data, header=header).writeto(path, overwrite=True)
    return path


def load_fits(path: str):
    """Lê um FITS → (dados float32, header). Para calibração/subs reais."""
    if not HAS_ASTROPY:
        raise RuntimeError("astropy não instalado (pip install astropy)")
    with fits.open(path) as hdul:
        return np.asarray(hdul[0].data, dtype=np.float32), hdul[0].header
