# Projeto: Telescópio Robótico Inteligente sobre NVIDIA Jetson

> Um *smart telescope* autônomo estilo DWARFLAB / ZWO Seestar, porém com um cérebro de
> processamento de borda **~30× mais poderoso**, usando GPU CUDA/TensorRT para *live stacking*,
> *lucky imaging* e rastreamento em tempo real que os SoCs ARM desses produtos não conseguem fazer.

Status: **fase de planejamento / arquitetura** (pré-código). Data-base do plano: 2026-07.

---

## 1. Visão em uma frase

Capturar céu profundo (Andrômeda, nebulosas, galáxias), Lua, planetas e objetos rápidos (ISS/satélites)
com um pipeline **100% na borda** (sem nuvem), fazendo empilhamento ao vivo em ponto flutuante 32 bits
na memória da Jetson, com autofoco, *plate solving* e rastreamento local — expondo o frame empilhado
em tempo real para uma UI web via WebSocket.

## 2. Benchmark — o que estamos superando

| | **DWARFLAB DWARF 3** | **ZWO Seestar S50** | **Este projeto (alvo)** |
|---|---|---|---|
| Sensor | Sony IMX678 (1/1.8", 2.0µm) | Sony IMX462 (1/2.8", 2.9µm) | **Sony IMX585 STARVIS 2** (1/1.2", 2.9µm, ~0.8e⁻ RN, zero amp glow) |
| Óptica | 35mm f/4.3 (150mm) | 50mm f/5 (250mm) | **Aberta** — apo 50–72mm intercambiável (250–400mm) |
| Montagem | Altaz + "EQ" por inclinação | Altaz + EQ por software | **Harmônica AZ/EQ real** (ZWO AM3N/AM5N via INDI) |
| Compute | ARM SoC + ~5 TOPS NPU | ARM SoC + NPU pequeno | **Jetson Orin NX 16GB — 157 TOPS + 1024 CUDA cores** |
| Empilhamento | Real-time no SoC | Real-time no SoC | **CUDA/CuPy float32 na memória unificada** |
| Rejeição de frames | Básica | Básica | **FWHM + Variância Laplaciana em GPU (lucky imaging)** |
| Rastreamento IA | Tracking simples | — | **YOLOv8-TensorRT + fluxo óptico CUDA >60 FPS** |
| Preço | ~US$ 549 | ~US$ 499 | ~US$ 4.000 (DIY, óptica aberta + compute de sobra) |

**Conclusão do benchmark:** o diferencial não é a captura — é o que fazemos *depois* dela na GPU.
O DWARF 3 tem ~5 TOPS; a Orin NX entrega 157 TOPS. Essa folga é o que permite empilhar em float32,
rejeitar frames por qualidade e rodar IA de rastreamento **em paralelo**, sem escolher um ou outro.

## 3. Decisões travadas nesta rodada de planejamento

| Decisão | Escolha | Motivo |
|---|---|---|
| **Formato inicial** | Bancada robusta → depois portátil | De-riscar software antes de mecânica/térmica selada |
| **Escopo de capacidade** | Paridade total com DWARF + superação | Céu profundo, planetário, lunar, panorama, satélites |
| **Pilar central do pipeline** | Céu profundo / *live stacking* | Maior valor e maior seção do spec |
| **Compute** | Orin NX 16GB (dev em Orin Nano Super 8GB) | Melhor custo/desempenho/térmica; 16GB para float32 4K |
| **Câmera** | IMX585 — USB3 (Fase 1) → MIPI CSI (Fase 2) | Bring-up rápido primeiro, baixa latência depois |
| **Montagem** | ZWO AM3N (harmônica, INDI) | Sem contrapeso, <4kg, driver maduro |
| **Óptica** | Apo ~250mm f/4–5 (classe RedCat 51) | Enquadra Andrômeda em 1 disparo, ~2,4"/px |
| **Software base** | INDI (hardware) + orquestrador próprio | Appliance dedicado, não desktop Ekos |
| **Plate solving** | ASTAP local (índices em NVMe) | Mais rápido/leve que astrometry.net |

## 4. Filosofia de desenvolvimento

> **De-riscar o software primeiro; otimizar o hardware depois.**

O diferencial e a parte difícil é o pipeline CUDA/CV. Mecânica selada, driver MIPI e montagem custom
são armadilhas que travam meses sem serem o diferencial. Por isso:

- **Fase 1** usa peças "chatas e prontas" (câmera USB3 + INDI + montagem comercial) para **provar o pipeline**.
- **Fase 2+** troca por hardware otimizado (MIPI CSI zero-copy, corpo selado) sem reescrever o núcleo.

## 5. Índice da documentação

| Doc | Conteúdo |
|---|---|
| [`docs/01-hardware.md`](docs/01-hardware.md) | BOM completa em 3 níveis, câmera/montagem/óptica/foco/energia, orçamento |
| [`docs/02-arquitetura.md`](docs/02-arquitetura.md) | Fluxo de dados sensor→GPU→VRAM, **memória unificada / zero-copy**, stack de software, concorrência |
| [`docs/03-pipeline-software.md`](docs/03-pipeline-software.md) | Live stacking, FWHM/lucky imaging, autofoco, plate solving, rastreamento — desenho de cada módulo |
| [`docs/04-roadmap.md`](docs/04-roadmap.md) | Roadmap faseado (Fase 0→4) com entregáveis e critérios de saída |
| [`docs/05-setup-ambiente.md`](docs/05-setup-ambiente.md) | Comandos de preparação da Jetson (JetPack, nvpmodel, OpenCV-CUDA, CuPy, INDI, ASTAP) |
| [`docs/06-aceleracao-e-tecnicas.md`](docs/06-aceleracao-e-tecnicas.md) | **Como o DWARF faz imagens bonitas** + stack de libs/frameworks + o que o Orin Nano tem de acelerador |
| [`docs/07-demo-fase1.md`](docs/07-demo-fase1.md) | Como rodar a demo de live stacking (com simulador, sem câmera) |
| [`docs/08-reusar-vs-construir.md`](docs/08-reusar-vs-construir.md) | ⭐ **Mapa de decisão: o que reusar (INDI/Ekos/cedar-solve/ZWO SDK…) vs. construir (pipeline GPU)** |
| [`docs/09-fase2-autonomia.md`](docs/09-fase2-autonomia.md) | Fase 2: auto-find (GOTO + plate solving) + autofoco — como rodar `run_fase2.py` |
| [`docs/10-arquitetura-e-testes.md`](docs/10-arquitetura-e-testes.md) | ⭐ **Premissa de engenharia: arquitetura Hexagonal + pirâmide de testes (pytest + doctest)** |
| [`docs/11-arquitetura-recomendada.md`](docs/11-arquitetura-recomendada.md) | ⭐ **Qual arquitetura (a decisão): Hexagonal + Pipes&Filters + State Machine; TDD sim, DDD não** |
| [`docs/12-fase3-agendador.md`](docs/12-fase3-agendador.md) | Fase 3: agendador multi-alvo (Plan mode) — `run_scheduler.py` |
| [`docs/13-calibracao.md`](docs/13-calibracao.md) | Calibração completa (bias/dark/flat) — `run_fase1.py --calibrate` |
| [`docs/14-otimizacao-gpu.md`](docs/14-otimizacao-gpu.md) | ⭐ **Otimização GPU + speedup medido (warp/stack ~40–50× em 4K no RTX 4070)** |
| [`docs/15-fits-wcs.md`](docs/15-fits-wcs.md) | Saída FITS + WCS (astropy) — abre no Siril/PixInsight |
| [`docs/16-mosaico.md`](docs/16-mosaico.md) | T1: mosaico multi-painel — `run_mosaic.py` |
| [`docs/17-features-t2-t6.md`](docs/17-features-t2-t6.md) | T2–T6: pós-processo, filtros, controles web, perfis, persistência |
| [`docs/18-fase4-tracking.md`](docs/18-fase4-tracking.md) | ⭐ **Fase 4 (T8–T11): rastreamento IA em tempo real — `run_tracking.py`** |
| [`docs/19-painel-noite-autonoma.md`](docs/19-painel-noite-autonoma.md) | T12: painel de controle web (todos os modos + Parar) + noite autônoma — `run_app.py` |
| [`docs/20-indi-simulador.md`](docs/20-indi-simulador.md) | ⭐ **T13: camada INDI validada sem hardware (cliente puro-Python + servidor falso)** |
| [`docs/21-astap-e-dados-reais.md`](docs/21-astap-e-dados-reais.md) | ⭐ **T14–T15: plate solving real (ASTAP) + validação do pipeline com dados reais (M67)** |
| [`docs/22-autofind-radec.md`](docs/22-autofind-radec.md) | ⭐ **T16: auto-find celeste em malha fechada (RA/DEC) — o "apontar sozinho" (modo GOTO)** |
| [`docs/23-pesquisa-foss-e-estrategia-dwarf.md`](docs/23-pesquisa-foss-e-estrategia-dwarf.md) | ⭐ **Pesquisa FOSS + estratégia p/ superar a DWARF 3 (reusar/construir, 5 alavancas, datasets)** |
| [`docs/24-estudio-produto.md`](docs/24-estudio-produto.md) | ⭐ **Estúdio de produto: escolher alvo + imagem REAL 13MP + dezenas de controles — `run_studio.py`** |
| [`docs/25-deconv-denoise.md`](docs/25-deconv-denoise.md) | ⭐ **T19: deconvolução Richardson-Lucy + denoise (as alavancas que passam a DWARF)** |
| [`docs/26-catalogo-atlas.md`](docs/26-catalogo-atlas.md) | ⭐ **Catálogo do céu real (14k objetos) + filtro pela óptica + visibilidade — `run_catalog.py`** |
| [`docs/27-mais-alvos-e-hotpixels.md`](docs/27-mais-alvos-e-hotpixels.md) | T21: mais alvos reais (M51 galáxia + Roseta) + remoção de hot pixels (walking noise) |
| [`docs/29-reuso-astroscrappy-ia-starnet.md`](docs/29-reuso-astroscrappy-ia-starnet.md) | Reuso: astroscrappy (raios cósmicos) + denoise IA (astro-csbdeep→ONNX) + StarNet (remover estrelas) |
| [`docs/28-bringup-jetson.md`](docs/28-bringup-jetson.md) | ⭐ **Milestone E: bring-up na Jetson Orin — roda no Orin (GPU), painel/estúdio no celular, INDI real 4/4** |
| [`docs/30-modo-planetario.md`](docs/30-modo-planetario.md) | ⭐ **Modo Sistema Solar (Lua/planetas/Sol): lucky imaging em GPU — grade→seleção→correlação de fase→stack→wavelets — `run_planetary.py`** |
| [`docs/31-bringup-camera-controle.md`](docs/31-bringup-camera-controle.md) | ⭐ **Milestone F: como a Jetson recebe a imagem (USB3/MIPI→GPU) e controla montagem/foco p/ apontar — fluxograma + sequência F1–F6** |
| [`docs/32-hardware-bom.md`](docs/32-hardware-bom.md) | ⭐ **BOM de hardware: OnStepX + FYSETC E4 + OpenAstroExplorer (OAE, 3D imprimível compacto) + SV705 + motores/ótica/foco/energia — o que imprimir e comprar** |
| [`TASKS.md`](TASKS.md) | ⭐ **Plano de execução: Fase 1→4 + Milestones D/E/F (fechar software antes da câmera)** |

---

*Persona de trabalho: Engenheiro de Sistemas Embarcados Sênior — Visão Computacional de Baixa Latência e
Astrofotografia Computacional. Ver [`CLAUDE.md`](CLAUDE.md) para o briefing técnico completo.*
