# 24 — Estúdio de Processamento (a experiência de PRODUTO) + dados reais

Objetivo: sair do "protótipo de bancada" e ter a experiência que o usuário quer — **escolher o
alvo como na DWARF, ver a imagem REAL em alta resolução e ajustar com dezenas de controles**, tudo
bonito. Rodando no PC hoje; a mesma UI serve a Jetson com a câmera.

## Como usar

```
py -3.11 run_studio.py            # http://localhost:8010
```
Escolha o alvo → ajuste os sliders (o preview atualiza ao vivo) → **baixe em alta resolução**.

## Peças

### Dado real → stack linear (`scripts/process_real_dataset.py`)
Processa subs REAIS (OSC) numa imagem: carrega lights FITS → subtrai master-dark → **debayer**
(Bayer→RGB) → **registra** por estrelas (astroalign) → **empilha** média float32 → salva PNG +
**FITS linear** (para o estúdio reprocessar). Provado no dataset Siril **M8 Lagoa + M20 Trifida**
(15×180s, ASI2600MC, 26MP): gerou `output/lagoon_trifid_real.png` e `data/stacks/lagoon_trifid_linear.fits`.

### Motor de render (`src/postproc/render.py`)
Transforma o stack **linear** (float32, preserva dynamic range) na imagem final, com os controles:

| Grupo | Controles |
|---|---|
| Brilho/stretch | ponto preto, **stretch (asinh)**, ponto branco, gamma |
| Cor | saturação, ganho R/G/B, balanço automático nas estrelas |
| Detalhe/ruído | **denoise de croma**, **redução de estrela**, **nitidez (unsharp)** |
| Fundo | remoção de gradiente (gentil — não come a nebulosa difusa) |

Presets de 1 clique (como o "otimizar" da DWARF, mas ajustáveis): `natural`, `vivido`, `nebulosa`,
`suave`. Renderiza em ~1s no PC (preview reduzido é instantâneo). **Nota**: gradiente OFF por padrão
— ligado agressivo, ele apaga nebulosas grandes (aprendizado: a Lagoa é sinal, não "fundo").

### Estúdio web (`src/server/studio.py` + `run_studio.py`)
Servidor stdlib. Mantém os stacks lineares em memória (full + preview). Endpoints:
`/` (página), `/targets` (catálogo JSON), `/render?<params>` (JPEG preview), `/download?<params>`
(JPEG **alta-res** 13MP). Catálogo com o alvo real + vitrine de alvos "com a câmera" (M31/M42/M45).

## T18 — Cor correta (dois bugs reais consertados)

A primeira imagem saía **azul/verde** (errada). Investigando com a imagem de referência do autor do
dataset (Lagoa deve ser **rosa/Hα**), achamos e corrigimos **dois bugs de verdade**:

1. **Debayer errado** (`src/gpu/debayer.py`): a nomenclatura Bayer do OpenCV é DESLOCADA em relação ao
   rótulo do sensor. Para um sensor "RGGB" (ASI2600MC/585MC) o código correto é `COLOR_BayerGR2RGB`, não
   `RG2RGB`. O errado gerava um **artefato azul** no halo da nebulosa. Diagnóstico: só o padrão correto dá
   **cor consistente do núcleo ao halo** (teste dos 4 padrões).
2. **Green cast do sensor OSC**: o canal verde tem o dobro de fotossítios no Bayer → domina tudo (fica
   verde). Corrigido com **SCNR** (Subtractive Chromatic Noise Reduction) no motor de render:
   `G = min(G, (R+B)/2)`. É o passo padrão de todo processamento OSC.

Pipeline de cor no `render.py`: fundo neutro (percentil do céu por canal) → **SCNR** → trim R/G/B →
stretch → saturação. Resultado: emissão em **rosa/Hα** (Trifida rosa, Lagoa rosada), sem falso azul/verde.
Controles novos no estúdio: **SCNR** e ganhos R/G/B. (Uma tentativa anterior — balanço por "estrela média
neutra" — foi descartada: FALHA na Via Láctea, onde as estrelas são avermelhadas por extinção.)

## O que isto NÃO é ainda (honesto)

- A cor está correta mas **sutil** (45 min de dado; a Lagoa fica rosada-clara, não vermelho profundo). Cor
  vibrante como a referência precisa de mais integração + **PCC com catálogo** (Gaia via cedar-solve) — futuro.
- Denoise/nitidez são clássicos (gaussian/unsharp); o **denoise IA (GraXpert) e a deconvolução
  (cuCIM/Cosmic Clarity→TensorRT)** — as alavancas que batem a DWARF (docs/23) — ainda não entraram.
- Só 1 alvo real (M8/M20). Mais alvos = baixar mais datasets ou a câmera.

Próximas tasks em `TASKS.md` (Milestone D+): calibração de cor, denoise IA, deconvolução, mais alvos.
Ver `docs/23` (estratégia/alavancas) e `docs/21` (dados reais).
