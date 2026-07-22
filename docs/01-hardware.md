# 01 — Hardware & BOM (Bill of Materials)

Todos os preços são de rua 2025–mid-2026 (USD), aproximados; conferir no checkout.

---

## 1. Computação (o "cérebro")

### Lineup Jetson mid-2026 — o que faz sentido

| Módulo / Kit | RAM | GPU (CUDA / Tensor) | AI (Super Mode) | Potência | Preço | Papel neste projeto |
|---|---|---|---|---|---|---|
| Orin Nano Super 8GB Dev Kit | 8GB LPDDR5 | 1024 / 32 (Ampere) | **67 TOPS** | 7–25W | **$249** | **Kit de desenvolvimento / entrada** |
| Orin NX 16GB (módulo) | 16GB LPDDR5 | 1024 / 32 (Ampere) | **157 TOPS** | 10–40W | ~$599 (1KU) / ~$900–1.400 single | **✅ Alvo de produção** |
| AGX Orin 64GB Dev Kit | 64GB LPDDR5 | 2048 / 64 + 2× NVDLA | **275 TOPS** | 15–60W | $1.999 | Opção sem compromissos |
| ~~AGX Thor (Blackwell)~~ | 128GB | Blackwell | ~2000 TFLOPS FP4 | **130W** | $3.499 | ❌ **Overkill** — classe robótica humanoide |

### Recomendação — caminho de custo otimizado

> **Comece no Orin Nano Super 8GB Dev Kit ($249). Faça upgrade trocando o módulo pelo Orin NX 16GB.**

A carrier board do Orin Nano Developer Kit (P3768) aceita tanto módulos Orin Nano quanto **Orin NX**
(mesmo conector SO-DIMM). Isso permite:

1. Investir $249 agora para provar todo o pipeline (o Nano Super já supera o DWARF 3 com folga).
2. Mais tarde, comprar só o **módulo Orin NX 16GB** e encaixar na mesma carrier — sem trocar SSD, câmera, etc.

> ✅ **Confirmado pelos números de parte:** o dev kit é o **P3766**, composto por **módulo P3767** (SO-DIMM) +
> **carrier P3768**. Tanto o Orin Nano quanto o Orin NX usam módulos da **mesma família P3767** no **mesmo
> carrier P3768** — então o upgrade é literalmente **trocar o módulo P3767 (Nano) por um P3767 (NX 16GB)**.
> (Recomendável ainda conferir a revisão/entrada de firmware com o vendedor, mas o form factor é o mesmo.)
>
> P-numbers dos módulos: Orin Nano 8GB = `P3767-0003`; Orin Nano 4GB = `P3767-0004/0005`;
> Orin NX 8GB = `P3767-0001`; Orin NX 16GB = `P3767-0000`.

**Por que 16GB importa:** um frame 4K debayerizado em float32 RGB ocupa ~100 MB
(3840×2160 × 3 canais × 4 bytes). Acumulador + mapa de pesos + buffers de alinhamento + máscaras + modelo
TensorRT residente ao mesmo tempo cabem confortavelmente em 16GB; nos 8GB isso fica apertado quando
*stacking* e rastreamento IA rodam juntos (ver cálculo em [`docs/02-arquitetura.md`](02-arquitetura.md)).

### Software base

- **JetPack 6.2.x** (estável para Orin): CUDA 12.6, TensorRT 10.3, cuDNN 9.3, Ubuntu 22.04. Habilita o "Super Mode".
- JetPack 7.x (CUDA 13) só se quiser a base unificada Orin+Thor — desnecessário aqui.
- **OpenCV precisa ser recompilado com `WITH_CUDA=ON`** — o que vem no JetPack e no `pip` é **CPU-only**.
- **CuPy** tem wheels aarch64 prontas: `pip install cupy-cuda12x` (JetPack 6).

---

## 2. Câmera principal (Sony IMX585 STARVIS 2)

**Specs confirmadas:** 1/1.2" (12,84mm diag.), 3840×2160 (~8,3 MP), pixel 2,9µm, RN ~0,7–1,0e⁻,
full-well ~40–47 ke⁻, QE pico ~91%, **zero amp glow**, RAW 10/12-bit, HDR até 88–106 dB.
Nativo 90fps@10bit / 60fps@12bit sobre MIPI CSI-2 (via USB fica limitado a ~40–47fps por banda).

### Fase 1 — caminho USB3 (bring-up em uma tarde)

| Câmera | Resfriada? | Preço | Driver INDI | Nota |
|---|---|---|---|---|
| **ZWO ASI585MC** | Não | ~$389 | `indi-asi` (o mais maduro) | ✅ **Início recomendado** |
| ZWO ASI585MC **Pro** | **Sim (TEC)** | ~$599 | `indi-asi` | Upgrade para SNR de céu profundo |
| Player One Uranus-C | Não | ~$369 | `indi-playerone` | Alternativa levemente mais barata |
| QHY5III585C | Não | ~$390 | `indi-qhy` | USB-C; driver historicamente mais chato |

> **Recomendação:** começar com **ASI585MC (não resfriada)** para provar o pipeline. Migrar para a **Pro
> (resfriada)** quando for buscar SNR em sinais fracos — o resfriamento TEC dá temperatura estável e repetível,
> o que valida bibliotecas de *dark frames* e reduz *hot pixels*. Para *live stacking* (subs curtos de 1–30s)
> a não-resfriada é um começo legítimo.

### Fase 2 — caminho MIPI CSI (baixa latência, zero-copy)

| Módulo | Suporte Jetson | Dificuldade | Nota |
|---|---|---|---|
| **Arducam xISP "Darksee" IMX585** | Orin Nano/NX | Moderada | ✅ Caminho barato; DT overlays + docs prontos |
| Framos FSM-IMX585C/TXA | AGX/Orin (adaptadores) | Maior custo | Driver JetPack mais robusto (industrial) |
| Leopard / e-con IMX585 4K | Jetson | Moderada | Suporte por cotação/NDA |

> MIPI entrega **V4L2 → buffer NVMM zero-copy** e os 60–90fps nativos — ideal para o rastreamento ativo.
> Custo: bring-up de *device tree*/clock/lanes e você mesmo constrói debayer/calibração (o que já é o
> nosso pipeline `cv2.cuda`+CuPy). **Módulos MIPI são não-resfriados** — se resfriamento for obrigatório,
> fique no caminho USB3.

### Há algo melhor que o IMX585 em 2026?

- **IMX678** (1/1.8", 2.0µm): mais barato, melhor disponibilidade MIPI, mas pixels menores/menos poço. Lateral.
- **IMX571 (APS-C, 26MP)**: *o* benchmark de céu profundo — FOV enorme. Mas **sai do ecossistema MIPI**
  (só USB), exige resfriamento e custa $1.000–2.000. É o próximo degrau real de qualidade/campo, se um dia quiser.
- **Veredito:** IMX585 é o ponto ideal para um rig compacto de *live stacking* de alto FPS. O salto além dele
  é APS-C (IMX571), que muda a categoria do projeto.

---

## 3. Montagem, óptica e acessórios

### Montagem (harmônica, forte suporte INDI)

| Montagem | Tipo | Payload | Driver INDI | Preço | Nota |
|---|---|---|---|---|---|
| **ZWO AM3N** | Strain-wave AZ/EQ | 8/13 kg | `indi_lx200am5` | ~$1.499–1.699 | ✅ **Ponto ideal** — sem contrapeso, <4kg |
| ZWO AM5N | Strain-wave AZ/EQ | 15/20 kg | `indi_lx200am5` | ~$1.799 | Se for carregar tubo maior |
| iOptron HEM27 | Strain-wave híbrida | ~13,5 kg | `indi_ioptronv3` | ~$1.600–1.800 | Tem iPolar embutido |
| Sky-Watcher AZ-GTi | Altaz (+cunha p/ EQ) | ~5 kg | `indi_eqmod` | ~$399 + cunha | Só se orçamento for a trava dura |

### Óptica — dimensionada ao sensor IMX585 (11,2×6,3mm)

| Focal | FOV (L×A) | Escala | Andrômeda (~3°×1°) |
|---|---|---|---|
| 250mm | 3,2°×1,8° | 2,99"/px | ✅ M31 inteira com margem |
| 300mm | 2,1°×1,2° | 1,99"/px | Núcleo / mosaico 2 painéis p/ halo |
| 400mm | 1,6°×0,9° | 1,50"/px | Mosaico p/ M31; ótimo p/ galáxias menores |

> **Recomendação:** apo plano-de-campo **~250mm f/4–5 classe William Optics RedCat 51** (~$800–1.200).
> Enquadra Andrômeda em um disparo a ~2,4"/px, bem casado com *seeing* típico de 2–3" sem *oversampling*.
> Alternativa mais longa/nítida: Askar FRA400 (400mm f/5,6) com mosaico para os maiores alvos.

### Focalizador e filtros (INDI)

- **Focalizador motorizado:** **ZWO EAF** (~$199, driver `indi_asi_focuser`) — casa com o loop de autofoco FWHM/CFZ.
- **Galáxias (broadband, ex. Andrômeda):** filtro anti-poluição luminosa suave **Optolong L-Pro** (~$250). *Não* use dual-band aqui.
- **Nebulosas em emissão:** **Optolong L-eXtreme** (Hα+OIII, ~$309) para máximo contraste sob céu urbano.

---

## 4. Armazenamento, energia e mecânica

- **SSD NVMe M.2 1TB** (~$80–100): captura RAW + **índices do ASTAP** para *plate solving* sub-segundo. A carrier do Orin Nano tem slot M.2 NVMe.
- **Energia (bancada):** fonte 12V/5A + conversores buck para 5V da câmera/EAF. Orin NX fica em 10–40W.
- **Energia (portátil, futuro):** bateria LiFePO4 12V + regulador; a Jetson e a montagem AM3N aceitam 12V.
- **Térmica:** cooler ativo (já no dev kit). Ao ar livre, **fita anti-orvalho** no tubo. Gabinete IP54+ só na fase de produto selado.
- **Guiagem:** com montagem harmônica + FL curto (250mm) e subs curtos, guiagem provavelmente **dispensável** no início.

---

## 5. Orçamento consolidado (DIY, Fase 1)

| Item | Recomendação | USD |
|---|---|---|
| Compute | Orin Nano Super 8GB → módulo NX 16GB depois | $249 (+~$600 módulo) |
| Câmera | ZWO ASI585MC (não resfriada) | $389 |
| Montagem | ZWO AM3N | $1.599 |
| Óptica | RedCat 51 (250mm) | $999 |
| Focalizador | ZWO EAF | $199 |
| Filtros | L-Pro + L-eXtreme | $560 |
| SSD | NVMe 1TB | $90 |
| Diversos | cabos, fonte, anti-orvalho, tripé/pilar | ~$250 |
| **Total Fase 1 (Nano Super)** | | **~$4.335** |
| Upgrade para produção (módulo NX 16GB) | | +~$600 |

> Comparado a US$ 549 (DWARF 3) / US$ 499 (Seestar), o prêmio compra **óptica aberta, montagem harmônica
> de verdade e ~30× o poder de processamento** — o espaço para superar esses produtos em software.
