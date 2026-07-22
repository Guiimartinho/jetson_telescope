"""Registro (alinhamento) por estrelas-guia.

Estratégia de REUSO (ver docs/08): usa **astroalign** (correspondência por triângulos
de estrelas, MIT) quando disponível — é o algoritmo maduro; senão cai para o nosso
método próprio (vizinho mais próximo + afim parcial com RANSAC, cv2).

Separação: `estimate_transform` devolve a matriz M (2×3) que mapeia o frame atual →
referencial; `warp` aplica M ao frame (mono OU cor) e gera a máscara de validade.
O warp usa cv2.warpAffine (correto em qualquer plataforma); na Jetson, migrar para
cv2.cuda.warpAffine (GpuMat) para manter o frame na GPU (Fase 1.1).
"""
from __future__ import annotations
import numpy as np
import cv2

from ..backend import asnumpy

try:
    import astroalign as _aa          # reuso: pip install astroalign (MIT)
    HAS_ASTROALIGN = True
except Exception:
    _aa = None
    HAS_ASTROALIGN = False

try:                                  # warp na GPU (cupyx) — RTX 4070 / Jetson
    import cupyx.scipy.ndimage as _cndi
    from ..backend import xp as _xp, HAS_CUPY as _GPU_WARP
except Exception:
    _GPU_WARP = False


def match_nearest(src: np.ndarray, dst: np.ndarray, max_dist: float = 80.0):
    """Correspondência por vizinho mais próximo (fallback; válida p/ movimento pequeno)."""
    if len(src) == 0 or len(dst) == 0:
        e = np.empty((0, 2), np.float32)
        return e, e
    d = np.linalg.norm(src[:, None, :] - dst[None, :, :], axis=2)
    j = np.argmin(d, axis=1)
    keep = d[np.arange(len(src)), j] <= max_dist
    return src[keep].astype(np.float32), dst[j[keep]].astype(np.float32)


def estimate_transform(stars, ref_stars):
    """Devolve M (2×3, float32) mapeando o frame atual → referencial, ou None.

    Tenta astroalign (reuso) sobre os centroides já detectados; se indisponível ou
    falhar, usa NN + estimateAffinePartial2D com RANSAC."""
    stars = np.asarray(stars, np.float32)
    ref_stars = np.asarray(ref_stars, np.float32)

    if HAS_ASTROALIGN and len(stars) >= 3 and len(ref_stars) >= 3:
        try:
            t, _ = _aa.find_transform(stars, ref_stars)   # aceita listas de (x,y)
            return np.asarray(t.params[:2, :], dtype=np.float32)
        except Exception:
            pass  # cai para o fallback

    src, dst = match_nearest(stars, ref_stars)
    if len(src) < 3:
        return None
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                             ransacReprojThreshold=3.0)
    if M is None or (inliers is not None and int(inliers.sum()) < 3):
        return None
    return M.astype(np.float32)


def _warp_cpu(frame, M, shape):
    """Warp em CPU (cv2). Aceita mono HxW ou cor HxWx3. Retorna NumPy."""
    H, W = shape
    f = asnumpy(frame).astype(np.float32)
    warped = cv2.warpAffine(f, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0.0)
    mask = cv2.warpAffine(np.ones((H, W), np.float32), M, (W, H),
                          flags=cv2.INTER_NEAREST, borderValue=0.0)
    return warped, mask


def _warp_gpu(frame, M, shape):
    """Warp afim na GPU (cupyx). frame NumPy ou CuPy; retorna CuPy (fica na VRAM).

    cv2 usa coords (x,y); cupyx.affine_transform usa (linha,coluna)=(y,x) e a matriz
    'output->input'. Montamos o mapa direto em (linha,coluna) e invertemos."""
    H, W = shape
    M = np.asarray(M, np.float64)
    fwd = np.array([[M[1, 1], M[1, 0], M[1, 2]],     # forward (row,col): input->output
                    [M[0, 1], M[0, 0], M[0, 2]],
                    [0.0, 0.0, 1.0]])
    inv = np.linalg.inv(fwd)                         # output->input (o que o cupyx quer)
    f = _xp.asarray(frame, dtype=_xp.float32)
    mat = _xp.asarray(inv, dtype=_xp.float32)
    warped = _cndi.affine_transform(f, mat, output_shape=(H, W), order=1,
                                    mode="constant", cval=0.0)
    mask = _cndi.affine_transform(_xp.ones(f.shape, _xp.float32), mat,
                                  output_shape=(H, W), order=0, mode="constant", cval=0.0)
    return warped, mask


def warp(frame, M, ref_shape, prefer_gpu=True):
    """Aplica M ao frame → (warped, mask). Usa GPU (cupyx) quando disponível e mono."""
    H, W = ref_shape[:2]
    if prefer_gpu and _GPU_WARP and getattr(frame, "ndim", 2) == 2:
        return _warp_gpu(frame, M, (H, W))
    return _warp_cpu(frame, M, (H, W))
