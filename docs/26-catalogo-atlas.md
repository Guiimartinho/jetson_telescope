# 26 — Catálogo do céu (atlas real) + filtro pela óptica

O que o usuário levantou (certeiro): um telescópio real precisa de um **catálogo completo** de alvos, e
**nem todo objeto é observável com a nossa lente** — depende do campo de visão e da magnitude. Isto NÃO é
simulação: são objetos reais, com RA/DEC reais, que o GOTO aponta de verdade.

## O catálogo (`src/core/catalog.py`)

Usa o **OpenNGC** via `pyongc` (FOSS): ~14.000 objetos NGC/IC/Messier com RA/DEC, tipo, magnitude e
tamanho. `SkyObject` normaliza tudo (RA/DEC em graus, mag V, eixo maior em arcmin, nome popular).

- `load()` — carrega os DSOs (galáxias, nebulosas, aglomerados) do catálogo (cacheado). **12.014 objetos.**
- `find(name)` — resolve por designação ou nome popular (`M51`, `NGC5194`, `Whirlpool`) → RA/DEC real.
  É isto que o **GOTO** (T16, `controller._radec_for`) usa: aponta em QUALQUER alvo, não só 3 fixos.

## O filtro pela NOSSA óptica (`Rig`)

```
Rig(focal_mm, aperture_mm, sensor_w_mm, sensor_h_mm)
  fov_deg()      -> campo de visão (2·atan(sensor/(2·focal)))
  limiting_mag() -> 2.5 + 5·log10(D_mm) + 4.5 (empilhando)
```
Rig padrão do projeto (IMX585 + refrator ~250mm f/5): **campo 2,57°×1,44° · mag limite 15,5**.

- `framable(objs, rig)` — mantém só o que **cabe no quadro** (tamanho entre 3% e 90% do menor lado do
  FOV — nem pontinho, nem maior que o campo) e é **brilhante o bastante** (mag ≤ limite). Do nosso rig:
  **1.868 objetos capturáveis** (de 12.014).
- `altitude_deg(obj, lat, lon, when)` / `visible(objs, lat, lon, when, min_alt)` — filtra pelo que está
  **acima do horizonte** num local/hora (astropy). Ex.: de São Paulo agora → **474 visíveis** (>25°).

## Uso

```
py -3.11 run_catalog.py --lat -23.5 --lon -46.6      # o que dá pra fotografar AGORA no seu céu
py -3.11 run_catalog.py --find "Whirlpool"           # resolve um alvo -> RA/DEC
```

No telescópio real: **escolher alvo (dos 474 visíveis) → `find` dá o RA/DEC → GOTO aponta (T16) →
captura → pipeline → Estúdio.** É a mesma cadeia da DWARF, aberta.

Requer `pyongc` (pip install pyongc). Testes: `tests/test_catalog.py` (6, pulam sem pyongc). Ver docs/22
(GOTO) e docs/24 (estúdio).
