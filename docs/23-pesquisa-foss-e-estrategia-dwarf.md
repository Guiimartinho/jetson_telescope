# 23 — Pesquisa FOSS + estratégia para superar a DWARF 3

Síntese de 4 frentes de pesquisa (jul/2026). Tudo FOSS/grátis. Links confirmados via busca.
Artifact visual: ver histórico da sessão (página "Estratégia — como bater a DWARF 3").

## A descoberta central

A DWARF 3 usa um **Sony IMX678** — a **mesma classe** do nosso IMX585. A vantagem dela não é
sensor/óptica: é software, e o gargalo dela é **compute** (SoC de celular). A Jetson Orin
(GPU Ampere + Tensor Cores) esmaga esse chip. **Ganhamos rodando algoritmos que ela não faz ao vivo.**

## As 5 alavancas de qualidade (o "melhor que a DWARF")

1. **Lucky imaging agressivo** *(construir)* — muitos subs curtos, FWHM/variância por frame na GPU,
   guarda só os melhores %. A DWARF empilha subs de 60 s sem descarte fino.
2. **Super-resolução por drizzle** *(construir)* — dithering + drizzle 2×/3× → detalhe acima do pixel.
3. **Deconvolução quase em tempo real** *(construir+reusar)* — PSF das estrelas-guia → Richardson-Lucy
   na GPU (RedLionfish/CuPy) ou o modelo do Cosmic Clarity via TensorRT.
4. **Denoise/realce IA sobre float32 linear** *(reusar)* — GraXpert + Cosmic Clarity no stack linear
   (não em JPG comprimido como o app da DWARF).
5. **Cadeia float32 ponta-a-ponta + stretch reversível** *(construir)* — rejeição sigma na VRAM 32-bit,
   FITS linear, stretch GHS/asinh na GPU → mais dynamic range.

## Reusar — controle/automação

| Projeto | Papel | Licença |
|---|---|---|
| [indilib/indi](https://github.com/indilib/indi) + [indi-3rdparty](https://github.com/indilib/indi-3rdparty) | Servidor/drivers (ZWO/IMX585, foco, montagem) | LGPL |
| [smroid/cedar-solve](https://github.com/smroid/cedar-solve) (Tetra3) | **Plate solve sub-segundo** blind, Python puro | Apache-2.0 |
| [KDE/kstars](https://github.com/KDE/kstars) (Ekos) | Referência de autofoco/align/scheduler | GPL |
| [OpenPHDGuiding/phd2](https://github.com/OpenPHDGuiding/phd2) | Autoguiding | BSD-3 |
| [hjd1964/OnStepX](https://github.com/hjd1964/OnStepX) | Firmware GOTO da montagem (no MCU) | GPL |
| [smroid/cedar-server](https://github.com/smroid/cedar-server) | Smart-telescope FOSS completo em ARM (o "DWARF aberto") — estudar | — |

**Plate solving recomendado:** cedar-solve (blind, sub-segundo) → ASTAP (refino de campo estreito).
astrometry.net só como fallback difícil (segundos).

## Reusar — imagem/realce

| Projeto | Papel | Licença | Jetson |
|---|---|---|---|
| [setiastro/cosmicclarity](https://github.com/setiastro/cosmicclarity) | Deconv/sharpen + super-res + denoise IA | **MIT** | PyTorch→TensorRT |
| [Steffenhir/GraXpert](https://github.com/Steffenhir/GraXpert) | Gradiente + denoise IA (CLI) | GPL-3.0 | ONNX→CUDA/TensorRT |
| [lock042/siril](https://github.com/lock042/siril) | Calibração/registro/stack/cor/GHS (headless) | GPL-3.0 | CPU maduro |
| [quatrope/astroalign](https://github.com/quatrope/astroalign) | Registro por asterismos (já usamos) | MIT | CPU |
| [spacetelescope/drizzle](https://github.com/spacetelescope/drizzle) | Super-resolução drizzle | BSD | portar CuPy |
| [rosalindfranklininstitute/RedLionfish](https://github.com/rosalindfranklininstitute/RedLionfish) | Deconvolução RL em GPU | Apache-2.0 | GPU |
| [artyom-beilis/OpenLiveStacker](https://github.com/artyom-beilis/OpenLiveStacker) | **Referência arquitetural de EAA ao vivo** (Web UI, ASI/INDI) | GPL-3.0 | estudar/superar |

Hacks de protocolo (molde da nossa API WebSocket/JSON + RTSP): [seestar_alp](https://github.com/smart-underworld/seestar_alp),
[dwarfium](https://github.com/stevejcl/dwarfium), [dwarfAlp](https://github.com/acocalypso/dwarfAlp).

## Blocos do Jetson

- **Captura zero-copy:** `nvarguscamerasrc` + NVMM (MIPI CSI, futura IMX585) → latência ~10-30ms;
  [dusty-nv/jetson-utils](https://github.com/dusty-nv/jetson-utils) (MIT) para USB (ASI585) e CSI.
- **[NVIDIA VPI](https://developer.nvidia.com/embedded/vpi):** optical flow/features no PVA/OFA → libera CUDA p/ stacking.
- **[jetson-inference](https://github.com/dusty-nv/jetson-inference) + TensorRT:** YOLO >60 FPS.
- **OpenCV-CUDA:** recompilar (≥4.9, `CUDA_ARCH_BIN=8.7`, +swap, desinstalar apt antes).
- **`nvpmodel -m 2` (MAXN_SUPER) + `jetson_clocks`.** ASI SDK: **USB bandwidth=40** (evita frames quebrados).

## Datasets (provar algoritmos + demo bonita, NÃO o "ao vivo")

- **1º — [Siril M8/M20](https://siril.org/tutorials/tuto-scripts/)** (OSC, ~centenas MB, calibração completa) → valida
  o pipeline inteiro e rende imagem colorida bonita já.
- **2º — [MILAN Survey](https://zenodo.org/record/6865830)** (90-180 subs/alvo, FITS mono) → estressa o stacking em escala.
- Parecer: dataset = **benchmark de qualidade** do nosso algoritmo, não degrau para o tempo real
  (isso depende de câmera + tracking + latência).

## Ordem recomendada

**Agora (PC, grátis):** Siril M8/M20 → imagem bonita; adotar cedar-solve/GraXpert/Cosmic Clarity no plano; T7 (CI).
**Milestone E (Orin, sem câmera):** OpenCV-CUDA + nvpmodel + TensorRT + INDI server; medir FPS → decidir 8GB vs NX 16GB.
**Milestone F (câmera):** captura zero-copy + as 5 alavancas no céu real.
