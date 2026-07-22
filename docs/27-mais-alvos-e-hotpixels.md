# 27 — Mais alvos reais + remoção de hot pixels (T21)

## Novos alvos no Estúdio

Baixados do **MILAN Survey** (Zenodo, FITS, câmera Stellina/IMX178, subs de 10s) e processados
(`scripts/process_real_dataset.py --bin 2 --max 50`) → `data/stacks/`:

- **NGC2244 (Nebulosa Roseta)** — nebulosa de emissão (RGGB).
- **M51 (Galáxia Whirlpool)** — galáxia espiral + companheira NGC5195 (BGGR). O pipeline **resolveu a
  estrutura espiral** num stack de ~8 min.

O Estúdio (`run_studio.py`) agora tem **3 alvos reais** (Lagoa+Trifida, Roseta, M51) e só lista os que
já têm stack pronto. O script suporta `--mono` (dados sem Bayer).

## O bug do "walking noise" (e a correção)

Os primeiros stacks do MILAN saíram com **trilhas coloridas diagonais**. Diagnóstico: as **estrelas
estavam redondas** (registro OK), então não era desalinhamento — eram **hot pixels**. Sem darks, o pixel
quente é fixo no sensor; ao **registrar** os frames (que giram/derivam), ele é "espalhado" numa trilha
que segue a transformação → *walking noise*. O M8/M20 não tinha isso porque tinha darks.

**Correção:** `src/gpu/calibration.remove_hot_pixels(raw)` — substitui spikes de 1px pela mediana local
3×3 (um pixel é "quente" se excede a mediana por `max(60, 6·MAD)`). Aplicado por frame **quando não há
darks**. Testado (`test_calibration.py`). Resultado: estrelas redondas, sem trilhas.

Aprendizado geral: **sem darks → sempre remover hot pixels** antes de registrar/empilhar; ou usar stack
com rejeição sigma (rejeita o outlier que caminha). Amp glow (gradiente nas bordas do IMX178) ainda
aparece — darks/flats reais ou extração de fundo (T18/GraXpert) resolvem.

Ver docs/24 (estúdio) e docs/21 (dados reais).
