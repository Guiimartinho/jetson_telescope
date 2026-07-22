"""Debayer (Bayer → RGB) na GPU.

Só é exercitado no caminho de câmera COLORIDA (ex.: ASI585MC). O simulador é mono e
pula esta etapa. Na Jetson com OpenCV-CUDA, usar cv2.cuda.demosaicing (mantém na GPU);
aqui usamos cv2.cvtColor (CPU) como base correta e portátil.
Ver docs/02-arquitetura.md.
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy

# ATENÇÃO: a nomenclatura Bayer do OpenCV é DESLOCADA em relação ao rótulo do sensor (o código
# é nomeado a partir do 2º pixel do padrão). Para um sensor "RGGB" (ASI2600MC/ASI585MC) o código
# CORRETO é BayerGR2RGB — verificado empiricamente (só ele dá cor consistente do núcleo ao halo;
# o RG2RGB gerava um artefato azul no halo). O mesmo deslocamento (RG<->GR, BG<->GB) vale p/ os 4.
# Ajustar por câmera no bring-up se a cor sair trocada. Ver docs/24.
_CODES = {
    "RGGB": cv2.COLOR_BayerGR2RGB, "BGGR": cv2.COLOR_BayerGB2RGB,
    "GRBG": cv2.COLOR_BayerRG2RGB, "GBRG": cv2.COLOR_BayerBG2RGB,
}


def debayer(frame, pattern: str = "RGGB"):
    """frame: Bayer HxW (uint8/16 ou float). Retorna RGB HxWx3 float32.

    OBS: o mosaico Bayer exato depende da câmera; ajustar `pattern` conforme o sensor
    (a ASI585MC costuma ser RGGB) quando o hardware chegar."""
    g = asnumpy(frame)
    if g.dtype not in (np.uint8, np.uint16):
        g = np.clip(g, 0, 65535).astype(np.uint16)
    rgb = cv2.cvtColor(g, _CODES.get(pattern, cv2.COLOR_BayerRG2RGB))
    return rgb.astype(np.float32)
