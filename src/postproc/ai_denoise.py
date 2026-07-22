"""Denoise por IA — runner ONNX genérico (astro-csbdeep / Cosmic Clarity / GraXpert), fallback clássico.

Executa um modelo de denoise ONNX. **Na Jetson usa o TensorRT Execution Provider** (compila e CACHEIA
a engine FP16 — 1ª execução compila, depois carrega pronta); no PC, CUDA (RTX 4070). SEMPRE GPU quando
disponível, nunca só CPU. Suporta modelos de 1 canal (luminância) e 3 canais (RGB, ex.: Cosmic Clarity).
Ladrilha imagens grandes. Sem modelo/onnxruntime → denoise clássico (bilateral). Ver docs/29.
"""
from __future__ import annotations
import os
import numpy as np

from .deconv import denoise_luminance

try:
    import onnxruntime as ort
    HAS_ORT = True
except Exception:
    HAS_ORT = False

_TRT_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "models", ".trt_cache")


def onnx_providers(cache_dir: str | None = None):
    """TensorRT (FP16 + engine cache) > CUDA > CPU. Nunca só CPU se houver GPU.

    No Orin o TensorRT EP compila a engine na 1ª execução e a cacheia em `models/.trt_cache`;
    execuções seguintes carregam a engine pronta (rápido)."""
    if not HAS_ORT:
        return []
    avail = set(ort.get_available_providers())
    provs = []
    if "TensorrtExecutionProvider" in avail:
        cache = cache_dir or _TRT_CACHE
        try:
            os.makedirs(cache, exist_ok=True)
        except Exception:
            cache = None
        opts = {"trt_fp16_enable": True}
        if cache:
            opts.update(trt_engine_cache_enable=True, trt_engine_cache_path=cache)
        provs.append(("TensorrtExecutionProvider", opts))
    if "CUDAExecutionProvider" in avail:
        provs.append("CUDAExecutionProvider")
    provs.append("CPUExecutionProvider")
    return provs


class OnnxDenoiser:
    """Roda um modelo ONNX de denoise (1 ou 3 canais), ladrilhado. TensorRT/CUDA quando disponível."""
    def __init__(self, model_path: str, tile: int = 512, overlap: int = 32, providers=None):
        if not HAS_ORT:
            raise RuntimeError("onnxruntime não instalado")
        self.sess = ort.InferenceSession(model_path, providers=providers or onnx_providers())
        inp = self.sess.get_inputs()[0]
        self.iname = inp.name
        self.oname = self.sess.get_outputs()[0].name
        s = inp.shape                                        # (N,C,H,W) p/ modelos astro
        self.in_ch = int(s[1]) if len(s) == 4 and isinstance(s[1], int) else 3
        self.tile, self.overlap = tile, overlap

    @property
    def provider(self) -> str:
        return self.sess.get_providers()[0]

    def _tile(self, chw_or_hw):
        # entrada já no formato do modelo: (H,W,C_in) normalizado [0,1]
        if self.in_ch == 3:
            x = np.transpose(chw_or_hw, (2, 0, 1))[None]     # 1,3,H,W
        else:
            x = chw_or_hw[None, None]                        # 1,1,H,W
        y = self.sess.run([self.oname], {self.iname: x.astype(np.float32)})[0]
        y = np.squeeze(y)
        return np.transpose(y, (1, 2, 0)) if y.ndim == 3 else y   # -> (H,W,C) ou (H,W)

    def run(self, img01):
        """img01: (H,W,3) se in_ch==3, senão (H,W). Retorna mesmo shape, ladrilhado."""
        a = np.asarray(img01, np.float32)
        h, w = a.shape[:2]
        out = np.zeros_like(a)
        wsum = np.zeros((h, w), np.float32)
        step = max(1, self.tile - self.overlap)
        for y0 in range(0, h, step):
            for x0 in range(0, w, step):
                y1, x1 = min(y0 + self.tile, h), min(x0 + self.tile, w)
                y0c, x0c = max(0, y1 - self.tile), max(0, x1 - self.tile)
                res = self._tile(a[y0c:y1, x0c:x1])
                if out.ndim == 3 and res.ndim == 2:
                    res = np.repeat(res[..., None], 3, 2)
                out[y0c:y1, x0c:x1] += res
                wsum[y0c:y1, x0c:x1] += 1.0
                if x1 >= w:
                    break
            if y1 >= h:
                break
        return out / np.maximum(wsum[..., None] if out.ndim == 3 else wsum, 1e-6)


def ai_denoise(image, model_path: str | None = None, strength: float = 1.0):
    """Denoise IA. Com modelo+onnxruntime → ONNX (TensorRT/CUDA); senão bilateral clássico.

    image: HxWx3 (ou HxW) uint8/float. `strength` mistura 0..1."""
    arr = np.asarray(image)
    if strength <= 0:
        return arr
    is_color = arr.ndim == 3
    f = arr.astype(np.float32)
    scale = 255.0 if f.max() > 1.5 else 1.0

    den = None
    if model_path and HAS_ORT and os.path.exists(model_path):
        try:
            d = OnnxDenoiser(model_path)
            if d.in_ch == 3 and is_color:
                # o modelo limpa a ESTRUTURA mas dessatura → usamos a luminância limpa da IA +
                # a cor original (croma suavizada p/ matar ruído de cor). Prática padrão em astro.
                import cv2
                out01 = d.run(f / scale)                     # RGB [0,1] -> RGB [0,1] (dessaturado)
                ai_lum = np.clip(out01.mean(2) * 255, 0, 255).astype(np.uint8)
                u8 = np.clip(f if scale == 255 else f * 255, 0, 255).astype(np.uint8)
                lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB)
                lab[..., 0] = ai_lum                         # L = luminância limpa da IA
                lab[..., 1] = cv2.medianBlur(lab[..., 1], 5)  # croma suavizada (tira ruído de cor)
                lab[..., 2] = cv2.medianBlur(lab[..., 2], 5)
                den = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).astype(np.float32) / 255.0 * scale
            else:                                            # modelo 1 canal (luminância)
                lum = f.mean(2) if is_color else f
                lo, hi = np.percentile(lum, 0.5), np.percentile(lum, 99.9)
                den_l = d.run(np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)) * max(hi - lo, 1e-6) + lo
                if is_color:
                    ratio = np.clip(den_l / (lum + 1e-6), 0.3, 3.0)
                    den = np.clip(f * ratio[..., None], 0, scale)
                else:
                    den = den_l
        except Exception:
            den = None

    if den is None:                                          # fallback clássico
        lum = f.mean(2) if is_color else f
        u8 = np.clip(lum, 0, 255).astype(np.uint8) if scale == 255 else \
            (255 * np.clip(lum, 0, 1)).astype(np.uint8)
        d8 = denoise_luminance(np.repeat(u8[..., None], 3, 2), max(strength, 0.3))[..., 0]
        den_l = d8.astype(np.float32) / 255.0 * scale
        if is_color:
            ratio = np.clip(den_l / (lum + 1e-6), 0.3, 3.0)
            den = np.clip(f * ratio[..., None], 0, scale)
        else:
            den = den_l

    out = (1 - strength) * f + strength * den
    return out.astype(arr.dtype)
