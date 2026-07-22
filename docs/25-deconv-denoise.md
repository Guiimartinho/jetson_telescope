# 25 — Deconvolução + denoise (T19): as alavancas que passam a DWARF

A DWARF faz GOTO + live stacking + um "otimizar" fechado. O que ela **não** faz ao vivo é
**deconvolução** (recuperar detalhe desfeito pela atmosfera/óptica) — porque não tem compute. É aqui
que a Jetson ganha. Ver `docs/23` (estratégia).

## Deconvolução Richardson-Lucy (`src/postproc/deconv.py`)

Estima a PSF pelas estrelas (gaussiana ~FWHM) e roda **Richardson-Lucy** na **luminância** (afia sem
amplificar ruído de cor), reaplicando o ganho aos canais RGB (`deconvolve_rgb`). FOSS puro (scipy FFT).

- `richardson_lucy(img, psf, iterations)` — o algoritmo clássico (iterativo, não-negativo).
- `deconvolve_rgb(rgb, iterations, sigma, max_gain)` — luminância + limite de ganho (evita estourar).
- Resultado: estrelas mais **apertadas** e estrutura da nebulosa mais definida. Em iterações altas
  aparece "anelamento" (halo escuro nas estrelas) — por isso é um **controle** (padrão 0; dosar 5–12).

Controle no estúdio: **Deconvolução (detalhe)** (0–20).

## Denoise (`deconv.denoise_luminance`)

Denoise de luminância clássico (bilateral, preserva bordas). É o **placeholder** do denoise IA:
- Hoje (PC): bilateral rápido, sem dependência.
- **GraXpert** (`postproc/enhance.py`): se instalado, faz denoise IA (ONNX). Fallback limpo sem ele.
- **Jetson**: GraXpert (ONNX→TensorRT) e **cuCIM/Cosmic Clarity** (deconv/denoise IA→TensorRT) substituem
  os passos clássicos com muito mais qualidade e velocidade (pesquisa `docs/23`).

Controles no estúdio: **Denoise (croma)** e **Denoise (luminância)**.

## Preset "H-alpha"

Novo preset de 1 clique que realça o vermelho da emissão (a Lagoa/Trifida em rosa/Hα), como o usuário
pediu. Junto com `vivido`, `nebulosa`, `natural`, `suave`.

## Honesto

- A deconvolução clássica (R-L + PSF gaussiana) é real e útil, mas a versão IA (Cosmic Clarity) e a
  aceleração GPU (cuCIM/TensorRT) só entram na Jetson — é lá que vira "tempo real".
- Denoise IA de verdade depende do GraXpert instalado (ou dos modelos na Jetson).

Testes: `tests/test_deconv.py` (5). **159 testes verdes.** Ver `docs/24` (estúdio) e `docs/23` (estratégia).
