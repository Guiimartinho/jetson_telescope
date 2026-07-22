# 29 — Reuso: astroscrappy, denoise IA (astro-csbdeep) e StarNet

Três reusos FOSS que agregam ao pipeline (dos repos analisados pelo usuário). Todos seguem o padrão do
projeto: **usa a ferramenta se instalada, senão cai num método próprio** — nada quebra sem ela.

## 1. Raios cósmicos / hot pixels — `postproc/cosmic.py`

`clean_cosmics(raw)` usa o **astroscrappy** (algoritmo L.A.Cosmic de van Dokkum, padrão maduro da área)
para remover spikes preservando estrelas (`objlim` alto). Sem astroscrappy → mediana local
(`gpu.calibration.remove_hot_pixels`). Substituiu o método simples em `scripts/process_real_dataset.py`.
Essencial sem darks (evita o "walking noise", docs/27). `pip install astroscrappy` (wheel aarch64 ok).

## 2. Denoise por IA — `postproc/ai_denoise.py`

Runner **ONNX genérico**: roda um modelo de denoise (astro-csbdeep / GraXpert / próprio) exportado p/
ONNX. `onnx_providers()` escolhe **TensorRT > CUDA > CPU** (Jetson acelera). Opera na luminância
(normalização por percentil + ladrilhamento p/ imagens grandes), preservando a cor. Sem modelo (ou sem
onnxruntime) → denoise clássico (bilateral). `ai_denoise(img, model_path, strength)`.

**Como plugar o astro-csbdeep** (BSD-3, treinável): treinar/baixar o modelo → exportar Keras→ONNX
(`tf2onnx`) → apontar `STUDIO_DENOISE_MODEL` para o `.onnx`. No Jetson, `onnxruntime-gpu` roda com o EP
TensorRT. Vantagem: dá para **treinar um denoise específico do nosso IMX585** depois.

## 3. Remoção de estrelas — `postproc/starless.py`

`remove_stars(img)` chama o **StarNet++** (CLI) se instalado (TIFF 16-bit in/out); senão, **abertura
morfológica** que remove pontos pequenos (estrelas) preservando a nebulosa. Permite esticar o gás sem
estourar estrelas e recombinar (workflow "starless"). StarNet: baixar o binário do autor (pesos
não-comerciais — ok p/ DIY).

## No Estúdio

Novos controles: **Denoise IA** (slider) e **Remover estrelas (StarNet)** (toggle). Aplicados como
finalização após o render, no preview e no download. Sem as ferramentas, usam os fallbacks (ainda úteis).

Testes: `test_cosmic.py`, `test_ai_denoise.py`, `test_starless.py` (10; fallbacks sempre testados,
caminhos das ferramentas com skipif). Ver docs/23 (estratégia) e docs/25 (deconvolução/denoise clássico).
