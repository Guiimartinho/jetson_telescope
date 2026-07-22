# Biblioteca de modelos de IA (embarcados)

**Um modelo por TAREFA** (não vários do mesmo). Formato **ONNX** — roda no Jetson via `onnxruntime`
com Execution Provider **TensorRT/CUDA** (ver `src/postproc/ai_denoise.py` e `models.py`).

Dropar aqui como `<tarefa>.onnx` (ou apontar a env `TELE_MODEL_<TAREFA>`). O código detecta e usa;
sem o modelo, cai no fallback clássico. Estes arquivos **não** vão pro git (grandes) — ver `.gitignore`.

| Arquivo | Tarefa | De onde vem (FOSS) |
|---|---|---|
| `denoise.onnx` | Denoise IA | astro-csbdeep (BSD-3, treinável no nosso IMX585) ou GraXpert (exportar Keras→ONNX com `tf2onnx`) |
| `starless.onnx` | Remover estrelas | StarNet v2 convertido p/ ONNX (é **UM** modelo geral — não vários) |
| `gradient.onnx` | Remover gradiente/fundo | GraXpert (modelo de background) |
| `deconv.onnx` | Deconvolução/nitidez | Cosmic Clarity (PyTorch→ONNX) |

## Por que ONNX e não os apps

No Orin (aarch64, Python 3.10) os apps x86 **não** rodam: StarNet++ é binário x86, GraXpert-pip exige
Python ≥3.11, Cosmic Clarity precisa do torch da Jetson. Então embarcamos os **modelos** (.onnx) e os
rodamos com o nosso runner (`ai_denoise.OnnxDenoiser`) — que já escolhe TensorRT > CUDA > CPU.

## Como obter cada um

- **denoise / gradient (GraXpert)**: instalar o GraXpert num PC (Py≥3.11), rodar uma vez p/ baixar os
  modelos ONNX, e copiá-los pra cá. Ou treinar um astro-csbdeep e exportar (`tf2onnx`).
- **starless (StarNet)**: usar uma conversão ONNX do StarNet v2 (comunidade) — 1 modelo geral.
- **deconv (Cosmic Clarity)**: exportar o `.pth` para ONNX (`torch.onnx.export`).

Depois de dropar, no Jetson: `pip install onnxruntime-gpu` (build da Jetson) ativa o EP TensorRT.
