# 14 — Otimização de GPU + benchmark (speedup medido)

Move as operações pesadas por pixel para a GPU e mantém o frame na VRAM ao longo do
pipeline — respondendo ao **Entregável #1** do CLAUDE.md (minimizar cópias Host↔Device).

## O que foi acelerado

| Op | Antes | Agora |
|---|---|---|
| **Warp afim** (registro) | cv2 (CPU) | `cupyx.scipy.ndimage.affine_transform` (GPU) |
| **Variância do Laplaciano** | cv2 (CPU) | `cupyx.scipy.ndimage.laplace` (GPU) |
| **Stack (soma ponderada)** | — | CuPy (GPU) — já era |

**Fluxo de memória (novo):** `calibração → cinza(↓1× p/ detecção) → warp(GPU) → stack(GPU)`.
O frame **fica na VRAM** da calibração até o acumulador; só o *cinza* é baixado uma vez (para a
detecção de estrelas em CPU, que é barata — poucas estrelas). Antes, o frame ia e voltava do host
a cada quadro.

## Nota sobre `cv2.cuda`
O OpenCV do `pip` é **CPU-only** (`cv2.cuda.getCudaEnabledDeviceCount()==0`). Por isso usamos
**CuPy/cupyx**, que roda na GPU tanto no PC de dev quanto na Jetson (mesmo `cupy-cuda12x`). Na Jetson,
com OpenCV **compilado com CUDA** (ver docs/05), o `cv2.cuda` vira uma alternativa — o código já está
estruturado para preferir GPU e cair em CPU quando preciso. A correção do warp GPU vs CPU é testada
(`tests/test_gpu_ops.py`).

## Speedup medido — RTX 4070 (dev), `scripts/benchmark_gpu.py`

**4K (3840×2160):**
| operação | CPU (ms) | GPU (ms) | speedup |
|---|--:|--:|--:|
| warp afim | 8.61 | 0.18 | **49×** |
| laplaciano + var | 38.56 | 4.02 | 9.6× |
| stack add | 15.58 | 0.38 | **41×** |

**1080p (1920×1080):**
| operação | CPU (ms) | GPU (ms) | speedup |
|---|--:|--:|--:|
| warp afim | 2.74 | 0.07 | 37.8× |
| laplaciano + var | 6.90 | 1.18 | 5.8× |
| stack add | 2.76 | 0.03 | 79.7× |

> As duas ops mais pesadas (warp e acumulação) ficam **~40–50× mais rápidas** em 4K. Rodar:
> `python scripts/benchmark_gpu.py`.

## O que continua em CPU (de propósito)
- **Detecção de estrelas** (`cv2.connectedComponents`) e **matching** (astroalign) — operam sobre
  poucas estrelas, custo baixo, e não têm equivalente GPU trivial. Baixamos só o cinza 1× por frame.
- FWHM (2º momento em janelas pequenas) — barato.

## Na Jetson
Mesmo `cupy-cuda12x`. Como a CPU da Orin é **muito** mais fraca que a de um desktop, o ganho relativo
da GPU tende a ser **ainda maior** lá — é exatamente onde esta otimização mais paga. E a captura MIPI
CSI (Fase 2 de HW) elimina até a cópia H→D inicial (buffer NVMM zero-copy).

## Validação
- `tests/test_gpu_ops.py`: warp GPU coloca a estrela no mesmo lugar do CPU (convenção de coords),
  concorda na média (<5%), e o laplaciano cresce com a nitidez. **71 testes verdes na GPU.**
