# 06 — Aceleração, Bibliotecas e a Ciência por trás das Imagens

Dois assuntos conectados: **(A)** *como* smart telescopes fazem imagens bonitas de nebulosas (a técnica),
e **(B)** *com o quê* aceleramos cada etapa na Jetson (as libs + os motores de hardware).

---

## A. Por que as imagens de nebulosa do DWARF são tão bonitas?

**Segredo nº 1: nebulosas são GRANDES, não pequenas — são apenas FRACAS.**
A Nebulosa de Órion tem ~1°, a North America ~2° (maior que a Lua cheia), Andrômeda ~3°. Você **não precisa
de magnificação nem de abertura grande** — precisa de *coletar fótons fracos* e *separar sinal de ruído*.
O DWARF tem só 35mm f/4.3; a "beleza" é **computacional**, não óptica. Isso é uma ótima notícia: dá para replicar.

As técnicas que produzem a imagem final (todas fazemos, melhor, na Jetson):

| # | Técnica | O que faz | Por que importa |
|---|---|---|---|
| 1 | **Empilhamento (stacking)** | Soma N subs curtos | **SNR cresce com √N**: 300 frames → ~17× menos ruído. É o coração |
| 2 | **Integração longa** | 30–120+ min de total | Nebulosidade fraca emerge do piso de ruído |
| 3 | **Razão focal rápida (f/4–5)** | Sinal ∝ 1/f² p/ objetos extensos | Tubo pequeno e rápido "enche" o sinal da nebulosa rápido |
| 4 | **Filtro dual-band (Hα+OIII)** | Passa só as linhas de emissão | **Maior salto de contraste sob céu urbano** — mata poluição luminosa |
| 5 | **Sensor STARVIS 2** | RN ~0,8e⁻, zero amp glow | Subs curtos empilham limpos, sem brilho de amplificador |
| 6 | **Calibração (dark/flat)** | Remove ruído de padrão fixo | Tira hot pixels e vinheta |
| 7 | **Tracking + plate solving** | Estrelas fixas nos mesmos pixels | O sinal acumula coerente ao longo dos minutos |
| 8 | **Stretch não-linear** | asinh/histograma | O RAW linear é ~99% preto; **é aqui que a estrutura fraca aparece** |
| 9 | **IA: denoise / remoção de gradiente / sharpen** | Pós-processo | O "acabamento" bonito e suave |

> **A sacada:** o DWARF não faz mágica óptica — faz software esperto sobre abertura pequena. Com a Jetson
> (~30× o processamento) podemos empilhar **mais frames em float32**, **rejeitar os ruins por FWHM/lucky
> imaging**, e rodar **denoise por IA mais pesado** — igualando ou superando as imagens dele com a mesma abordagem.

---

## B. O stack de aceleração na Jetson

### B.1 — O que o SEU Orin Nano **Super** 8GB realmente tem

> **O que significa "Super":** o *Jetson Orin Nano Super* **não é um chip novo** — é o **mesmo silício** do
> Orin Nano com um **modo de energia "Super Mode" (MAXN SUPER)** liberado por software no **JetPack 6.2**
> (dez/2024), que elevou os clocks de GPU/CPU/memória e o preço do dev kit caiu para **$249**. Resultado:
> o 8GB pulou de **40 → 67 TOPS** (~1,7× mais rápido), **de graça, só atualizando o JetPack**. Mas como é o
> mesmo silício, **os aceleradores de função fixa continuam os mesmos** — o "Super" **não adiciona DLA, PVA,
> OFA nem NVENC**. Ele deixa a **GPU** mais rápida, e é a GPU que faz todo o nosso pipeline. Ou seja: você
> tem a melhor e mais atual versão do Nano, e ela é genuinamente mais rápida — só não ganha motores novos.

⚠️ Os aceleradores de função fixa **variam por módulo**. Confirmado (ver fontes):

| Motor | Orin **Nano Super** 8GB (o seu) | Orin **NX** 16GB (produção) | AGX Orin |
|---|:---:|:---:|:---:|
| GPU Ampere (CUDA + Tensor cores) | ✅ 1024/32 | ✅ 1024/32 | ✅ 2048/64 |
| **DLA** (Deep Learning Accelerator) | ❌ **nenhum** | ✅ 2× NVDLA v2 | ✅ 2× NVDLA v2 |
| **PVA** (Programmable Vision Accelerator) | ❌ nenhum | ✅ | ✅ |
| **OFA** (Optical Flow Accelerator) | ❌ nenhum | ❌ | ✅ |
| **NVENC** (encoder de vídeo por HW) | ❌ **nenhum** | ✅ | ✅ |
| NVDEC (decoder) | ✅ | ✅ | ✅ |
| VIC (Video Image Compositor) + ISP | ✅ | ✅ | ✅ |

**Conclusão prática:** no Orin Nano, **toda a aceleração é a GPU CUDA** (+ VIC/ISP/NVDEC de função fixa para
câmera/vídeo). Isso é **mais que suficiente** para as Fases 1–3 (stacking, FWHM, registro, plate solve).
Os motores DLA/PVA/OFA chegam **quando você trocar para o módulo Orin NX** — aí dá para **descarregar o
YOLO no DLA e liberar a GPU inteira para o stacking** (Fase 4). Ou seja: a sua limitação atual não trava nada
do núcleo do projeto; só adia o rastreamento IA pesado, que é fase posterior mesmo.

> Nota do NVENC ausente: para transmitir o frame empilhado à UI web no Nano, **codificamos na GPU com nvJPEG**
> (imagem) ou por software — não dependemos do encoder de HW.

### B.2 — Bibliotecas por etapa do pipeline

| Etapa | Biblioteca / Framework | Motor na Jetson | Papel |
|---|---|---|---|
| Álgebra em VRAM (acumulador, calibração) | **CuPy** | GPU CUDA | Soma ponderada float32, máscaras |
| Debayer / warp / resize / filtros | **OpenCV-CUDA** (`cv2.cuda`) | GPU CUDA | Pré-processo de imagem |
| CV de baixo nível **zero-copy** | **VPI** (Vision Programming Interface) ⭐ | GPU/VIC (Nano); +PVA/OFA (NX) | Harris/FAST, KLT tracker, **fluxo óptico**, FFT, **TNR (denoise temporal)**, distorção |
| Kernels sob medida | **Numba CUDA** / PyCUDA | GPU CUDA | FWHM custom, stack custom, debayer custom |
| Pré-processo DL em lote | **CV-CUDA** | GPU CUDA | Preparar tensores p/ inferência |
| Inferência (tracking, denoise IA) | **TensorRT** | GPU (DLA no NX) | YOLOv8, modelos de denoise/super-res |
| Encode do frame p/ web | **nvJPEG / nvImageCodec** | GPU CUDA | JPEG na GPU (Nano não tem NVENC) |
| FFT (registro por fase, deconvolução) | **cuFFT** | GPU CUDA | Correlação de fase, lucky planetário |
| Reduções / ordenações (ranking de frames) | **Thrust / CUB** | GPU CUDA | Selecionar melhores frames |
| Captura zero-copy + glue | **jetson-utils**, **GStreamer** (`nvarguscamerasrc`) | ISP/VIC/NVMM | MIPI → buffer de GPU (Fase 2) |
| Pipeline sensor→IA de baixa latência | **NVIDIA Holoscan SDK** | GPU/GXF | (Opcional, avançado) framework de streaming zero-copy |
| Squeeze de performance | **nvpmodel**, **jetson_clocks**, **jtop** | — | Clocks máximos, monitorização |

### B.3 — Bibliotecas de domínio astronômico (reaproveitar algoritmos)

| Lib | Uso | Nota |
|---|---|---|
| **astropy** | FITS I/O, WCS, coordenadas RA/DEC | Essencial |
| **photutils** | Detecção de fontes (DAOStarFinder), fundo 2D, **PSF/FWHM** | Referência p/ nossa versão GPU |
| **sep** (Source Extractor lib) | Extração de fontes + fundo, muito rápida | Roda barato em thread de CPU |
| **astroalign** | Registro por triângulos de estrelas | Referência/porta p/ GPU |
| **ccdproc** | Master dark/flat/bias | Calibração |
| **Siril** (open source) | App de live stacking/processamento | **Ouro** para estudar algoritmos (registro, stretch, cor) |
| **ASTAP** | Plate solving local | Já escolhido |
| **INDI / pyindi-client** | Controle de hardware | Mount, câmera, foco |
| **GraXpert / StarNet++** | Remoção de gradiente/estrelas, **denoise IA** astro | A etapa de "beleza" (pós), acelerável por GPU |

---

## C. O que rodar no Orin Nano 8GB **agora** (sem câmera)

Você tem exatamente o que precisa para **começar hoje** e provar o núcleo do projeto:

1. **Fase 0** — setup do ambiente (ver [`docs/05-setup-ambiente.md`](05-setup-ambiente.md)): JetPack, OpenCV-CUDA, CuPy, VPI, ASTAP.
2. **Simulador de frames** — em vez de esperar a câmera, geramos campos estelares sintéticos (estrelas +
   ruído de leitura + deriva + rotação de campo + frames "ruins" borrados). Com isso dá para desenvolver e
   **ver o live stacking + o portão de qualidade FWHM funcionando de ponta a ponta** na bancada.
3. **Datasets reais** — também podemos alimentar o pipeline com **subs FITS reais** de céu profundo baixados
   (validação em dados verdadeiros antes de gastar com câmera).
4. Quando o orçamento permitir: **ZWO ASI585MC (~$389)** entra via INDI sem reescrever nada.

**Restrições do 8GB (todas contornáveis nas Fases 1–3):** manter o acumulador + ring buffer modesto; **não**
carregar o engine YOLO residente ainda (isso é Fase 4/NX); encode via nvJPEG (sem NVENC). O núcleo cabe folgado.

---

## Fontes (aceleradores por módulo)

- ⭐ **NVIDIA — Jetson Linux Developer Guide, tabelas oficiais de `nvpmodel` (prova definitiva):** o Orin Nano
  8GB/4GB lista **DLA cores: 0** e **PVA cores: 0** em todos os modos de energia; só Orin NX (DLA:1–2, PVA:1) e
  AGX Orin (DLA:2, PVA:1) listam esses motores. https://docs.nvidia.com/jetson/archives/r36.4.4/DeveloperGuide/SD/PlatformPowerAndPerformance/JetsonOrinNanoSeriesJetsonOrinNxSeriesAndJetsonAgxOrinSeries.html
- ⚠️ **Cuidado com docs "Jetson Orin" genéricos** (Technical Brief do AGX Orin): eles descrevem o **SoC Orin
  completo** (2 DLA + PVA + NVENC). O Orin Nano é uma versão do SoC com esses blocos **desabilitados por fusível** —
  por isso specs genéricas "de Orin" mencionam DLA/PVA/NVENC que **não existem no módulo Nano**.
- Wikipédia — Nvidia Jetson (tabela Orin: Nano sem DLA): https://en.wikipedia.org/wiki/Nvidia_Jetson
- NVIDIA — Deep Learning Accelerator on Jetson Orin: https://developer.nvidia.com/blog/getting-started-with-the-deep-learning-accelerator-on-nvidia-jetson-orin/
- "Does the Orin Nano have an OFA?" (OFA ausente no Nano): https://nvidia-jetson.piveral.com/jetson-orin-nano/does-the-nvidia-jetson-orin-nano-dev-board-have-an-optical-flow-accelerator/
- RidgeRun — Jetson Orin AGX SoM overview (DLA/PVA v2 no AGX): https://developer.ridgerun.com/wiki/index.php/NVIDIA_Jetson_Orin/Introduction/SoM_Overview
- RidgeRun — Orin Nano video encoding (NVENC ausente, encode por GPU): https://www.ridgerun.com/post/jetson-orin-nano-how-to-achieve-real-time-performance-for-video-encoding
- NVIDIA VPI (backends CPU/CUDA/PVA/VIC/OFA): https://docs.nvidia.com/vpi/
