"""Denoise por IA — runner ONNX genérico (astro-csbdeep / GraXpert / qualquer modelo), fallback clássico.

Executa um modelo de denoise exportado para ONNX. No Jetson usa o Execution Provider TensorRT/CUDA
(acelerado); no PC, CPU. Opera na LUMINÂNCIA (modelos de denoise astro são mono), com normalização por
percentil e ladrilhamento para imagens grandes. Sem modelo (ou sem onnxruntime), cai no denoise clássico
(bilateral, `deconv.denoise_luminance`). Assim o pipeline funciona já, e ganha IA quando um modelo é
plugado. Ver docs/29 (como treinar/converter o astro-csbdeep → ONNX).
"""
from __future__ import annotations
import numpy as np

from .deconv import denoise_luminance

try:
    import onnxruntime as ort
    HAS_ORT = True
except Exception:
    HAS_ORT = False


def onnx_providers():
    """Melhor Execution Provider disponível: TensorRT > CUDA > CPU (Jetson acelera; PC = CPU)."""
    if not HAS_ORT:
        return []
    avail = set(ort.get_available_providers())
    order = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
    return [p for p in order if p in avail] or ["CPUExecutionProvider"]


class OnnxDenoiser:
    """Carrega um modelo ONNX de denoise e roda na luminância (ladrilhado). Reutilizável."""
    def __init__(self, model_path: str, tile: int = 512, overlap: int = 32, providers=None):
        if not HAS_ORT:
            raise RuntimeError("onnxruntime não instalado")
        self.sess = ort.InferenceSession(model_path, providers=providers or onnx_providers())
        inp = self.sess.get_inputs()[0]
        self.iname = inp.name
        self.oname = self.sess.get_outputs()[0].name
        # descobre o layout do input: (N,C,H,W) ou (N,H,W,C)
        shape = inp.shape
        self.nchw = len(shape) == 4 and (shape[1] in (1, 3) or str(shape[1]).isdigit() and int(shape[1]) in (1, 3))
        self.tile, self.overlap = tile, overlap

    def _run_tile(self, t):                            # t: HxW float32 [0,1]
        x = t[None, None] if self.nchw else t[None, ..., None]   # (1,1,H,W) ou (1,H,W,1)
        y = self.sess.run([self.oname], {self.iname: x.astype(np.float32)})[0]
        y = np.squeeze(y)
        return y.astype(np.float32)

    def denoise(self, gray) -> np.ndarray:
        g = np.asarray(gray, np.float32)
        lo, hi = np.percentile(g, 0.5), np.percentile(g, 99.9)   # normaliza p/ [0,1]
        n = np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1)
        h, w = n.shape
        out = np.zeros_like(n)
        wsum = np.zeros_like(n)
        step = self.tile - self.overlap
        for y0 in range(0, max(1, h), step):
            for x0 in range(0, max(1, w), step):
                y1, x1 = min(y0 + self.tile, h), min(x0 + self.tile, w)
                y0c, x0c = max(0, y1 - self.tile), max(0, x1 - self.tile)
                res = self._run_tile(n[y0c:y1, x0c:x1])
                out[y0c:y1, x0c:x1] += res[: y1 - y0c, : x1 - x0c]
                wsum[y0c:y1, x0c:x1] += 1.0
                if x1 >= w:
                    break
            if y1 >= h:
                break
        den = out / np.maximum(wsum, 1e-6)
        return den * max(hi - lo, 1e-6) + lo           # desnormaliza


def ai_denoise(image, model_path: str | None = None, strength: float = 1.0):
    """Denoise IA na luminância (preserva cor). Com modelo+onnxruntime → ONNX; senão bilateral clássico.

    image: HxWx3 (ou HxW) uint8/float. Retorna no mesmo formato/escala. `strength` mistura 0..1."""
    arr = np.asarray(image)
    if strength <= 0:
        return arr
    is_color = arr.ndim == 3
    lum = arr.mean(2).astype(np.float32) if is_color else arr.astype(np.float32)

    if model_path and HAS_ORT:
        try:
            den = OnnxDenoiser(model_path).denoise(lum)
        except Exception:
            den = None
    else:
        den = None

    if den is None:                                    # fallback clássico (sem modelo)
        u8 = np.clip(lum, 0, 255).astype(np.uint8) if lum.max() <= 255 else \
            (255 * (lum - lum.min()) / max(lum.ptp(), 1e-6)).astype(np.uint8)
        den = denoise_luminance(np.repeat(u8[..., None], 3, 2), max(strength, 0.3))[..., 0].astype(np.float32)
        den = den / 255.0 * (lum.max() if lum.max() > 1 else 1.0)

    den = (1 - strength) * lum + strength * den        # mistura pela força
    if not is_color:
        return den.astype(arr.dtype)
    ratio = np.clip(den / (lum + 1e-6), 0.3, 3.0)      # reaplica aos canais (preserva cor)
    return np.clip(arr.astype(np.float32) * ratio[..., None], 0, None).astype(arr.dtype)
