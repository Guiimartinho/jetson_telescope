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
        """img01: (H,W,3) se in_ch==3, senão (H,W). Ladrilha em blocos de tamanho FIXO (self.tile),
        com PADDING nas bordas → uma única shape de entrada → TensorRT compila 1 engine (cacheada).
        Sem isso, cada ladrilho de borda vira uma shape nova e o TRT recompila (lento)."""
        a = np.asarray(img01, np.float32)
        h, w = a.shape[:2]
        T = self.tile
        out = np.zeros_like(a)
        wsum = np.zeros((h, w), np.float32)
        step = max(1, T - self.overlap)
        for y0 in range(0, h, step):
            for x0 in range(0, w, step):
                y1, x1 = min(y0 + T, h), min(x0 + T, w)
                th, tw = y1 - y0, x1 - x0
                tile = a[y0:y1, x0:x1]
                if (th, tw) != (T, T):                       # padeia p/ TxT (shape fixa)
                    shp = (T, T, a.shape[2]) if a.ndim == 3 else (T, T)
                    pad = np.zeros(shp, np.float32)
                    pad[:th, :tw] = tile
                    tile = pad
                res = self._tile(tile)
                if a.ndim == 3 and res.ndim == 2:
                    res = np.repeat(res[..., None], 3, 2)
                out[y0:y1, x0:x1] += res[:th, :tw]           # corta de volta ao tamanho real
                wsum[y0:y1, x0:x1] += 1.0
                if x1 >= w:
                    break
            if y1 >= h:
                break
        return out / np.maximum(wsum[..., None] if out.ndim == 3 else wsum, 1e-6)


_SESSIONS: dict = {}          # cache de OnnxDenoiser por caminho de modelo
_SESS_LOCK = None


def get_denoiser(model_path: str, tile: int = 512):
    """OnnxDenoiser MEMOIZADO por modelo. Criar a sessão ONNX (deserializar a engine TensorRT do
    cache em disco) custa ~2 s no Orin; reusar a mesma sessão entre renders deixa os sliders de IA
    rápidos (só a 1ª chamada paga o carregamento). Thread-safe."""
    import threading
    global _SESS_LOCK
    if _SESS_LOCK is None:
        _SESS_LOCK = threading.Lock()
    key = (os.path.abspath(model_path), tile)
    with _SESS_LOCK:
        d = _SESSIONS.get(key)
        if d is None:
            d = OnnxDenoiser(model_path, tile=tile)
            _SESSIONS[key] = d
        return d


def _lum_transfer(f, out01, scale, smooth_chroma: bool):
    """Transfere a LUMINÂNCIA do resultado da IA (RGB→RGB) para a COR original, via Lab.

    Modelos RGB da Cosmic Clarity limpam/aguçam a estrutura mas mexem na saturação. Preservamos
    a cor: L (luminância) = resultado da IA; a,b (croma) = imagem original. `smooth_chroma`
    suaviza a croma (denoise: mata ruído de cor; sharpen: deixa False p/ não borrar cor).
    Retorna array float na mesma escala de `f`."""
    import cv2
    ai_lum = np.clip(out01.mean(2) * 255, 0, 255).astype(np.uint8)
    u8 = np.clip(f if scale == 255 else f * 255, 0, 255).astype(np.uint8)
    lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB)
    lab[..., 0] = ai_lum
    if smooth_chroma:
        lab[..., 1] = cv2.medianBlur(lab[..., 1], 5)
        lab[..., 2] = cv2.medianBlur(lab[..., 2], 5)
    return cv2.cvtColor(lab, cv2.COLOR_LAB2RGB).astype(np.float32) / 255.0 * scale


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
            d = get_denoiser(model_path)
            if d.in_ch == 3 and is_color:
                out01 = d.run(f / scale)                     # RGB [0,1] -> RGB [0,1]
                den = _lum_transfer(f, out01, scale, smooth_chroma=True)  # luminância IA + cor orig
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


def ai_sharpen(image, model_path: str | None = None, strength: float = 1.0):
    """Aguçamento/Deconvolução IA (Cosmic Clarity SharpeningCNN → ONNX, TensorRT/CUDA na GPU).

    Recupera detalhe fino (estrelas menores, estrutura de nebulosa/galáxia) desfeito pelo seeing —
    o que uma deconvolução de Richardson-Lucy faz, mas aprendido. Aplica a luminância aguçada da
    IA à cor original (sem borrar croma). Sem modelo → unsharp mask clássico. `strength` mistura 0..1.
    """
    arr = np.asarray(image)
    if strength <= 0:
        return arr
    is_color = arr.ndim == 3
    f = arr.astype(np.float32)
    scale = 255.0 if f.max() > 1.5 else 1.0

    den = None
    if model_path and HAS_ORT and os.path.exists(model_path):
        try:
            d = get_denoiser(model_path)
            if d.in_ch == 3 and is_color:
                out01 = d.run(f / scale)
                den = _lum_transfer(f, out01, scale, smooth_chroma=False)  # aguça L, mantém cor
            else:                                            # modelo 1 canal
                lum = f.mean(2) if is_color else f
                lo, hi = np.percentile(lum, 0.5), np.percentile(lum, 99.9)
                sh_l = d.run(np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)) * max(hi - lo, 1e-6) + lo
                if is_color:
                    ratio = np.clip(sh_l / (lum + 1e-6), 0.3, 3.0)
                    den = np.clip(f * ratio[..., None], 0, scale)
                else:
                    den = sh_l
        except Exception:
            den = None

    if den is None:                                          # fallback: unsharp mask clássico
        import cv2
        u8 = np.clip(f if scale == 255 else f * 255, 0, 255).astype(np.uint8)
        blur = cv2.GaussianBlur(u8, (0, 0), 1.4)
        u8 = cv2.addWeighted(u8, 1.0 + 0.7 * strength, blur, -0.7 * strength, 0)
        den = u8.astype(np.float32) / 255.0 * scale

    out = (1 - strength) * f + strength * den
    return np.clip(out, 0, scale).astype(arr.dtype)
