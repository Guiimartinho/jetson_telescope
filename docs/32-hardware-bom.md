# 32 — BOM de hardware: montagem OnStepX + integração Jetson

Lista de materiais para o **protótipo de bancada** (de-riscar antes da versão compacta selada). Decisão do
usuário: **OnStepX** (firmware) + câmera **Svbony SV705** (IMX585). Objetivo aqui: o que **imprimir** e o que
**comprar**, separando o que já existe pronto (reuso) do que é específico do nosso telescópio.

## Base escolhida: OnStepX + OpenAstroMount (OAM)

**OpenAstroMount (OAM)** — montagem equatorial **100% imprimível**, ambos os eixos por **correia (redução
9:1 em dois estágios)**, payload **5+ kg**, precisão **0,5–0,7″ RMS**, roda **OnStep/OnStepX**. É exatamente o
"reaproveitar as peças 3D": as STLs e a lista de ferragens já existem e são casadas entre si.

> **⚠️ Fonte-mestra das peças da montagem:** o OAM publica **duas planilhas** no repositório
> `github.com/OpenAstroTech/OpenAstroMount` — **"Shopping List"** (parafusos, rolamentos, correias, polias,
> motor, placa — com quantidades exatas) e **"Printed Parts List"** (todas as STLs). **Baixe as STLs de lá e
> use a Shopping List como BOM-mestra da montagem** — ela é versionada junto com as peças. Abaixo dou a visão
> geral + tudo que a planilha do OAM **não** cobre (é o que precisamos somar para o NOSSO telescópio).

OnStepX também roda **alt-az** — então a mesma eletrônica serve para a versão compacta (estilo DWARF) depois.

---

## PARTE A — A montagem (OAM) — imprima + compre pela planilha do OAM

### A1. Peças 3D (imprimir) — do "Printed Parts List" do OAM
Conjunto RA + DEC + base polar + caixas de redução (gearbox) + suportes de motor + barra de contrapeso.
- Material: **PETG** (mais rígido/estável que PLA para carga estrutural) ou PLA+.
- Preenchimento ~40–50%, 3–4 perímetros. Pode **mandar imprimir já** — as STLs estão no repo.

### A2. Eletrônica de controle (OnStepX)
| Item | Recomendado | Qtd | Obs |
|---|---|---|---|
| Placa controladora | **ESP32 dedicada OnStep** (Instein PCB / MaxESP4) ou **FYSETC E4** (ESP32 + 4×TMC2209 + WiFi) | 1 | WiFi já resolve o link com a Jetson. **Confira o pinmap na OnStep wiki (Boards).** |
| Drivers de passo | **TMC2209** (silencioso, UART) | 2–3 | RA + DEC (+ foco). Já vêm na FYSETC E4. |
| Cabo USB / microSD | — | 1 | flash do firmware |
| (opcional) GPS ou RTC | módulo GPS uBlox **ou** RTC DS3231 | 1 | tempo/local; ou a Jetson fornece a hora |

### A3. Motores + transmissão
| Item | Recomendado | Qtd |
|---|---|---|
| Motor de passo eixos | **NEMA 17** 1,8° ~1,0–1,5 A (pancake serve) | 2 (RA, DEC) |
| Correias/polias/idlers GT2 | **conforme a Shopping List do OAM** (redução 9:1) | — |
| Rolamentos dos eixos | **tamanhos exatos na Shopping List do OAM** | — |

### A4. Ferragens (fasteners) — quantidades exatas na Shopping List do OAM
- **Insertos térmicos de latão M3** (montagem em plástico impresso) + parafusos **M3/M4/M5**, porcas, arruelas.
- Barra de contrapeso + **contrapeso** (equatorial precisa equilibrar).

---

## PARTE B — O que a planilha do OAM NÃO cobre (nosso telescópio)

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
| Item | Opção A (barato) | Opção B (pronto) |
|---|---|---|
| Motor de foco | **NEMA 14/17 + acoplador** no focalizador do OTA (OnStepX controla como eixo de foco) | **ZWO EAF** (USB, INDI pronto) |
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

### B6. Peças 3D custom (projetar — não vêm do OAM)
- **Berço da Jetson** (dissipação/ventilação) acoplado à base.
- **Suporte câmera + OTA** (alinhado ao eixo óptico).
- **Caixa da eletrônica** (placa OnStep + buck).
- **Braçadeiras de cabo**.

### B7. Base / tripé
- **Tripé fotográfico robusto** (ou pier impresso + coluna) + **cunha/base de alinhamento polar** (o OAM tem a base polar).

---

## Integração Jetson ↔ OnStepX (recap docs/31)
OnStepX no ESP32 expõe **WiFi (protocolo LX200 por TCP)** ou **USB-serial** → a Jetson conecta via INDI
(`indi_lx200`/`indi_onstep`) → o nosso `IndiMount`/`IndiFocuser` (já prontos e testados). **Zero software novo.**

## Ordem sugerida (compra/impressão)
1. **Imprimir já** as STLs do OAM (PETG). ~1 rolo.
2. Comprar a **eletrônica** (placa OnStep ESP32 + TMC2209 + **NEMA 17 ×2**) + **kit de ferragens/correias/
   rolamentos da Shopping List do OAM**.
3. **Fonte 12 V + buck 5 V + cabos**.
4. **OTA (objetivo)** + **foco motorizado** + **SV705** + cabo USB3.
5. Peças 3D custom (berço Jetson / suporte câmera-OTA).

## Custo aproximado (DIY/FOSS, ordem de grandeza)
| Bloco | ~USD |
|---|---|
| Eletrônica OnStep + 2× NEMA 17 | 60–100 |
| Ferragens + correias + rolamentos (OAM) | 40–70 |
| Fonte + buck + cabos | 25–45 |
| Filamento (PETG) | ~20 |
| **Subtotal montagem (sem ótica/câmera)** | **~150–250** |
| SV705C | ~200 |
| Ótica (objetivo) | 50 (lente usada) – 250+ (apo) |
| Foco (NEMA barato → ZWO EAF) | 15 – 150 |

## Decisões/verificações antes de comprar
- **Placa OnStep:** confirmar na **OnStep wiki (Boards)** a que casa com o OAM + o pinmap (crítico).
- **SV705 no aarch64:** validar suporte INDI/UVC no Orin **antes** (posso pesquisar) — se travar, plano B é ASI585.
- **Objetivo (OTA):** definir focal/abertura (afeta escala e campo — ver o comparativo Lua).
- **Quantidades exatas** (parafusos/rolamentos/correias): **sempre pela Shopping List do OAM** (versionada com as STLs).
