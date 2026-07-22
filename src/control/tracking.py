"""T8 — rastreamento por fluxo óptico (Lucas-Kanade esparso).

Segue um ponto (o objeto) entre frames. No PC de dev usa cv2 (CPU); na Jetson, cv2.cuda /
VPI (OFA no AGX). É a base do laço de tracking (Session.track em T10). Ver docs/18.
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy


def _u8(frame):
    g = asnumpy(frame).astype(np.float32)
    return cv2.normalize(g, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)


class OpticalFlowTracker:
    def __init__(self):
        self._prev = None
        self._pt = None

    def init(self, frame, point):
        self._prev = _u8(frame)
        self._pt = np.array([[point]], np.float32)     # (1,1,2)
        return tuple(self._pt[0, 0])

    def update(self, frame):
        cur = _u8(frame)
        if self._prev is None or self._pt is None:
            return None
        nxt, status, _ = cv2.calcOpticalFlowPyrLK(
            self._prev, cur, self._pt, None,
            winSize=(21, 21), maxLevel=3,
            criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))
        self._prev = cur
        if status is None or int(status[0, 0]) == 0:
            return None
        self._pt = nxt
        return (float(nxt[0, 0, 0]), float(nxt[0, 0, 1]))
