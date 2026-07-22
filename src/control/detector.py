"""T9 — Detector de objeto (satélite/ISS). Port + adapters.

`BrightObjectDetector`: acha o objeto brilhante e compacto (CV simples, roda em qualquer lugar).
`YoloTensorRTDetector`: usa YOLOv8 exportado para **TensorRT** na Jetson; **fallback** para o
detector CV quando TensorRT/engine não estão disponíveis (ex.: PC de dev). Ver docs/18.
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy


class Detector:
    def detect(self, frame):
        """Retorna (x, y) do objeto na tela, ou None."""
        raise NotImplementedError


class BrightObjectDetector(Detector):
    def __init__(self, k_sigma: float = 6.0, blur: float = 1.5):
        self.k = k_sigma
        self.blur = blur

    def detect(self, frame):
        g = asnumpy(frame).astype(np.float32)
        g = cv2.GaussianBlur(g, (0, 0), self.blur)
        med = float(np.median(g))
        mad = float(np.median(np.abs(g - med))) + 1e-6
        y, x = np.unravel_index(int(np.argmax(g)), g.shape)
        if g[y, x] < med + self.k * 1.4826 * mad:      # nada suficientemente brilhante
            return None
        return (float(x), float(y))


class YoloTensorRTDetector(Detector):
    """YOLOv8→TensorRT (Jetson) com fallback CV. Escafold — validar engine no bring-up."""
    def __init__(self, engine_path: str = None, fallback: Detector = None):
        self.fallback = fallback or BrightObjectDetector()
        self.backend = None
        try:
            import os
            import tensorrt  # noqa: F401  (só existe na Jetson com TensorRT)
            if engine_path and os.path.exists(engine_path):
                self.backend = "tensorrt"     # TODO(bring-up): carregar o engine aqui
        except Exception:
            self.backend = None

    def detect(self, frame):
        if self.backend == "tensorrt":
            # TODO(bring-up): pré-processo → inferência TensorRT → maior confiança → (x,y)
            pass
        return self.fallback.detect(frame)
