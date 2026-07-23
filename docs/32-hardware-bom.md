# 32 — BOM de hardware: montagem OnStepX + integração Jetson

Lista de materiais para o **protótipo de bancada** (de-riscar antes da versão compacta selada). Decisão do
usuário: **OnStepX** (firmware) + câmera **Svbony SV705** (IMX585). Objetivo aqui: o que **imprimir** e o que
**comprar**, separando o que já existe pronto (reuso) do que é específico do nosso telescópio.

## Base escolhida: OnStepX + OpenAstroExplorer (OAE)

**OpenAstroExplorer (OAE)** — montagem equatorial **compacta/portátil, 100% imprimível**, **v1.0 lançado
(pronto pra construir)**. **RA por correia (mesma redução 9:1 em dois estágios do OAM); DEC por rosca sem-fim
(worm) compacta.** Payload **5 kg**, precisão **0,6–0,9″ RMS** (PHD2), **3 kg** só o mount, **dobrável**, com
**auto polar align** e anel de RA magnético destacável. Roda **OnStep/OnStepX**. É a forma **mais próxima da
visão final (estilo DWARF)** — e não muda nossa eletrônica nem praticamente os motores.

> **Por que OAE e não OAM/OAT:** OAT = rastreador (leve/impreciso demais); OAM = GEM maior (0,5–0,7″ RMS, mais
> pesado); **OAE = compacto e portátil com o mesmo payload (5 kg) e precisão quase igual** → melhor encaixe no
> objetivo. Trade-off mínimo: precisão um tiquinho menor e DEC por worm (um pouco mais de backlash que correia).

> **⚠️ Fonte-mestra das peças da montagem:** o OAE publica no repositório
> `github.com/OpenAstroTech/OpenAstroExplorer` (+ wiki OpenAstroTech) a **"Shopping List"** (parafusos,
> rolamentos, correias, polias, worm, motores — quantidades exatas) e a **"Printed Parts List"** (todas as STLs).
> **Baixe as STLs de lá e use a Shopping List como BOM-mestra da montagem** — versionada junto com as peças.
> Abaixo: a visão geral + tudo que a planilha do OAE **não** cobre (o que somamos para o NOSSO telescópio).

---

## PARTE A — A montagem (OAE) — imprima + compre pela planilha do OAE

### A1. Peças 3D (imprimir) — do "Printed Parts List" do OAE
Conjunto RA + DEC + base polar + caixas de redução (gearbox) + suportes de motor + barra de contrapeso.
- Material: **PETG** (mais rígido/estável que PLA para carga estrutural) ou PLA+.
- Preenchimento ~40–50%, 3–4 perímetros. Pode **mandar imprimir já** — as STLs estão no repo.

### A2. Eletrônica de controle (OnStepX) — **placa escolhida: FYSETC E4** ✅

**FYSETC E4** (validada 2026-07): ESP32-WROOM-32 (240MHz, 16MB, **WiFi+BT**) + **4× TMC2209 onboard**
(UART, **2A** cada), entrada **12–24V**, CH340 USB, TF card, 3 endstops c/ sensorless. **Placa pronta,
made in China (~US$30) — compra, não fabrica.** Bate todos os critérios (OnStepX/WiFi/TMC2209/≥2 eixos+foco/12V).

| Item | Escolha | Qtd | Obs |
|---|---|---|---|
| Placa controladora | **FYSETC E4** (ESP32 + 4×TMC2209 + WiFi) | 1 | X=RA, Y=DEC, Z/E=foco, +1 sobra. **Confirmar o pinmap "FYSETC E4" no Config do OnStepX** (versão X). |
| Refrigeração dos drivers | dissipador + **fan 5V pequeno** | 1 | TMC2209 esquenta; nossa carga é leve, mas garante |
| Cabo USB / microSD | — | 1 | flash do firmware (CH340) |
| (opcional) GPS ou RTC | GPS uBlox **ou** RTC DS3231 | 1 | tempo/local; ou a Jetson fornece a hora |

**Bônus da E4:** a saída de aquecedor (15A/12V) vira **resistência anti-orvalho**; os 3 endstops viram
**fins de curso** dos eixos; StallGuard permite **homing sem sensor**.

> **Por que uma placa separada e não a própria Jetson?** Motor de passo precisa de pulsos STEP com timing de
> **microssegundos** (tempo real). O ESP32 é *bare-metal* com timers de hardware → pulso perfeito. A Jetson roda
> **Linux (não tempo-real)** e fica ocupada com visão/GPU → geraria *jitter* de ms → tracking tremido/estrelas
> alongadas. Divisão padrão (igual OctoPrint+Marlin na impressora 3D): **Jetson = cérebro** (visão, plate-solve,
> decisão, INDI client) ⇄ WiFi/USB ⇄ **ESP32+OnStepX = tempo real** (pulsos). O ESP32 não é o gasto — é ~US$5–30
> e dá o stack de montagem inteiro (goto/tracking/PEC/guiding/LX200) de graça. Ver docs/31.

### A3. Motores + transmissão (OAE: RA por correia 9:1, DEC por worm)
| Item | Escolha | Qtd | Obs |
|---|---|---|---|
| Motor **RA** (correia 9:1) | **17HS4401** (NEMA 17, 1,8°, ~40 N·cm, 1,7 A, bipolar, eixo 5mm) | 1 | validado |
| Motor **DEC** (worm) | **NEMA 17** — **confirmar no BOM do OAE** (worm pode usar NEMA 17 ou 14) | 1 | provável 17HS4401 também |
| Correias/polias/idlers GT2 + worm/coroa | **conforme a Shopping List do OAE** | — | |
| Rolamentos dos eixos | **tamanhos exatos na Shopping List do OAE** | — | |

> ⚠️ **Corrente dos NEMA 17 no OnStepX:** setar **~0,8–1,2 A** (não os 1,7 A cheios do 17HS4401) — a montagem
> quase não puxa torque; assim roda **frio e silencioso** nos TMC2209 da E4.

### A4. Ferragens (fasteners) — quantidades exatas na Shopping List do OAE
- **Insertos térmicos de latão M3** (montagem em plástico impresso) + parafusos **M3/M4/M5**, porcas, arruelas.
- Barra de contrapeso + **contrapeso** (equatorial precisa equilibrar).

---

## PARTE B — O que a planilha do OAE NÃO cobre (nosso telescópio)

### B1. Câmera + computação
| Item | Escolha | Qtd | Obs |
|---|---|---|---|
| Câmera | **Svbony SV705C** (IMX585, USB3) | 1 | sua escolha; validar driver INDI/UVC no aarch64 (ver docs/31) |
| Computador | **Jetson Orin Nano Super 8GB** | 1 | **já tem** |
| Cabo de dados | **USB3** (A↔C conforme a câmera) | 1 | câmera → Jetson |
| Cartão de armazenamento | microSD/NVMe | — | já no Orin |

### B2. Ótica (OTA) — ATENÇÃO: a SV705 é só o SENSOR
A câmera **não** tem lente de telescópio. Precisa de um **objetivo** (é o "telescópio" de fato):
- **Refrator apocromático pequeno** ~**50–60 mm de abertura**, ~**250–360 mm de focal** (classe RedCat/pequenos guiders apo), **ou**
- **Teleobjetiva fotográfica** (ex.: 135–300 mm) + adaptador para a câmera.
- Escala resultante (IMX585 2,9 µm): 250 mm → ~2,4″/px; Lua ~780 px (ver docs/comparativo).

### B3. Foco motorizado (autofoco)
| Item | Opção A (barato) — **escolhida** | Opção B (pronto) |
|---|---|---|
| Motor de foco | **35HS42** (NEMA 14 Kalatec — bipolar, 1,0 A, 20 N·cm, 1,8°, eixo 5mm) + acoplador/correia GT2 no focalizador → OnStepX controla no driver Z/E que sobra da E4 | **ZWO EAF** (USB, INDI pronto, ~US$150) |
| Focalizador | mecânica do OTA (helicoidal/Crayford) | idem |

### B4. Energia
| Item | Recomendado | Qtd | Obs |
|---|---|---|---|
| Fonte principal | **12 V DC, ≥5 A (60 W)** | 1 | alimenta a montagem/motores |
| Fonte da Jetson | **Buck 12 V→5 V 5 A** OU fonte **USB-C PD** | 1 | Orin sob carga (MAXN_SUPER) ~25 W → 5 V/5 A |
| Campo (portátil, futuro) | bateria **12 V LiFePO4** + XT60 + fusível | 1 | de-risca campo depois |

### B5. Cabos + conectores
| Item | Qtd | Obs |
|---|---|---|
| Cabo de motor 4-fios (JST/Dupont conforme a placa) | 2–3 | RA, DEC (+ foco) |
| USB3 (câmera) | 1 | curto, blindado |
| USB-C ou barrel (energia Jetson) | 1 | do buck/PD |
| Rede (opcional) | 1 | ou WiFi ESP32 ↔ Jetson |
| Fio, termorretrátil, conectores, DC barrel, XT60, fusível | — | avulsos |

### B6. Peças 3D custom (projetar — não vêm do OAE)
- **Berço da Jetson** (dissipação/ventilação) acoplado à base.
- **Suporte câmera + OTA** (alinhado ao eixo óptico).
- **Caixa da eletrônica** (placa OnStep + buck).
- **Braçadeiras de cabo**.

### B7. Base / tripé
- **Tripé fotográfico robusto** (ou pier impresso + coluna) + **cunha/base de alinhamento polar** (o OAE tem a base polar).

---

## Integração Jetson ↔ OnStepX (recap docs/31)
OnStepX no ESP32 expõe **WiFi (protocolo LX200 por TCP)** ou **USB-serial** → a Jetson conecta via INDI
(`indi_lx200`/`indi_onstep`) → o nosso `IndiMount`/`IndiFocuser` (já prontos e testados). **Zero software novo.**

## Ordem sugerida (compra/impressão)
1. **Imprimir já** as STLs do OAE (PETG). ~1 rolo.
2. Comprar a **eletrônica** (placa OnStep ESP32 + TMC2209 + **NEMA 17 ×2**) + **kit de ferragens/correias/
   rolamentos da Shopping List do OAE**.
3. **Fonte 12 V + buck 5 V + cabos**.
4. **OTA (objetivo)** + **foco motorizado** + **SV705** + cabo USB3.
5. Peças 3D custom (berço Jetson / suporte câmera-OTA).

## Custo aproximado (DIY/FOSS, ordem de grandeza)
| Bloco | ~USD |
|---|---|
| Eletrônica OnStep + 2× NEMA 17 | 60–100 |
| Ferragens + correias + rolamentos (OAE) | 40–70 |
| Fonte + buck + cabos | 25–45 |
| Filamento (PETG) | ~20 |
| **Subtotal montagem (sem ótica/câmera)** | **~150–250** |
| SV705C | ~200 |
| Ótica (objetivo) | 50 (lente usada) – 250+ (apo) |
| Foco (NEMA barato → ZWO EAF) | 15 – 150 |

## Decisões/verificações antes de comprar
- **Placa OnStep:** confirmar na **OnStep wiki (Boards)** a que casa com o OAE + o pinmap (crítico).
- **SV705 no aarch64:** validar suporte INDI/UVC no Orin **antes** (posso pesquisar) — se travar, plano B é ASI585.
- **Objetivo (OTA):** definir focal/abertura (afeta escala e campo — ver o comparativo Lua).
- **Quantidades exatas** (parafusos/rolamentos/correias): **sempre pela Shopping List do OAE** (versionada com as STLs).
