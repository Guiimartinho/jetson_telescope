# 30 — Modo Sistema Solar (Lua, planetas, Sol): lucky imaging

O pipeline até aqui era **100% céu profundo** (deep-sky): exposições longas, alinhamento por estrelas,
esticar sinal fraco. Lua / planetas / Sol são uma **disciplina diferente** — *lucky imaging de alta
cadência* — e é o que faltava para o telescópio cobrir o céu inteiro. Módulo: `src/planetary/`.

## Por que é diferente

| | Céu profundo (`src/gpu`) | Sistema Solar (`src/planetary`) |
|---|---|---|
| Captura | exposições de segundos, poucos frames | ROI pequena, **100–200+ FPS**, milhares de frames curtos |
| Motivo | sinal fraco | **congelar o seeing** (turbulência atmosférica) |
| Seleção | FWHM das estrelas | **variância do Laplaciano** por frame, fica com os top N% |
| Alinhamento | estrelas (astroalign) | **correlação de fase** (FFT) — não há estrelas na Lua/planeta |
| Empilhamento | média ponderada por estrela | idem (reusa `LiveStacker`), peso ∝ nitidez |
| Nitidez final | deconv / unsharp | **wavelets à trous** (revela bandas/crateras) |

Referências FOSS: **AutoStakkert!** e **Registax** são o padrão-ouro, mas fechados e Windows-x86 →
**não rodam no Orin aarch64**. Estratégia (igual à da IA, docs/29): reconstruímos o pipeline em GPU
(`xp` = CuPy) em vez de portar o binário. **PlanetarySystemStacker** (Python, aberto) é a boa referência.

## Os filtros (Pipes & Filters) — tudo em `xp` (GPU na Jetson, NumPy no CI)

1. **`lucky.sharpness(frame)`** — variância do Laplaciano da luminância. **Pré-suaviza** (sigma≈1) antes
   de medir: sem isso, com ruído forte a métrica escolheria os frames mais RUIDOSOS, não os mais nítidos.
   Validado no simulador: `corr(nitidez, seeing) = −0.88`; os escolhidos têm seeing 0.80 vs. 2.12 médio.
2. **`lucky.select_best(scores, keep)`** — índices dos top `keep` (ex.: 0.15 = melhores 15%).
3. **`align.estimate_shift(ref, frame)`** — deslocamento (dy,dx) subpixel por correlação de fase
   (FFT + janela de Hann + refino parabólico). `align.align_to(frame, ref)` desfaz o deslocamento.
4. **`gpu.stacker.LiveStacker`** (reuso) — acumula `Σ w·mask·frame` / `Σ w·mask` em float32 na VRAM.
5. **`wavelets.wavelet_sharpen(img, weights)`** — starlet à trous: decompõe por escala e realça cada
   uma. Pesos `(fina→grossa)`; escala fina (ruído) segurada baixa, escalas médias (detalhe real) >1.
   Invariante: pesos todos = 1 → reconstrução exata.

Orquestra tudo: **`stack.lucky_stack(frames, keep, align, sharpen)` → `LuckyResult`**.

## Rodar

```bash
py -3.11 run_planetary.py --kind jupiter --frames 200 --keep 0.15   # demo (simulador)
py -3.11 run_planetary.py --kind moon --frames 300 --keep 0.10
```

Gera `planetary.png` (1 frame cru | resultado). No simulador de Júpiter: 200 frames → 30 usados → disco
limpo, bandas definidas, Grande Mancha visível, bordo nítido (vs. frame cru ruidoso e mole).

## No estúdio (celular) — `src/server/studio.py`

Os alvos **Júpiter** e **Lua** aparecem no seletor do estúdio junto com os de céu profundo. Ao escolher
um, o servidor gera o lucky-stack sob demanda (200 frames simulados → seleção → alinhamento → stack, ~6 s
no Orin, **cacheado**) e a UI troca para os controles planetários (âmbar): **wavelets** (força do detalhe),
brilho, gamma, ponto preto, saturação, denoise — com presets `nitido`/`suave`/`detalhe`. O base fica
cacheado, então mexer nos sliders é **~26 ms** (só wavelets+níveis na GPU). Deep-sky segue com seus
controles (stretch/SCNR/asinh/IA). A distinção é o campo `mode` de cada alvo em `/targets`. Quando a câmera
chegar, troca-se o simulador por captura ROI real — a UI e o render não mudam.

## Caminho até a câmera real

O pipeline é **agnóstico à fonte** — recebe qualquer lista de frames. Para o modo real basta trocar o
`PlanetSimulator` por uma `FrameSource` de câmera em ROI/alta cadência (V4L2 do IMX585, ou a SV705/IMX585
— que é uma câmera **planetária**: sensor pequeno, FPS alto). Próximos incrementos (Fase 1.5):
alinhamento **multiponto** (crateras da Lua, campo grande), **derrotação** de Júpiter (WinJUPOS), drizzle.
⚠️ **Sol exige filtro solar de HARDWARE** (branco p/ manchas, Hα p/ proeminências) — sem ele, destrói o
sensor e é perigoso. O software é o mesmo da Lua.

## Testes

`tests/test_planetary_{align,lucky,wavelets,stack}.py` (18) — recuperação de deslocamento conhecido,
seleção dos nítidos, reconstrução exata das wavelets, e o stack baixando o ruído de fundo. Rodam por
`backend` (NumPy) no CI, sem GPU/hardware.
