# 13 — Calibração completa (bias / dark / flat)

Remove os defeitos fixos do sensor/óptica antes do empilhamento: **bias**, **corrente de escuro**,
**pixels quentes** e **vinheta/poeira**. Roda na GPU (float32 na VRAM) — `src/gpu/calibration.py`.

## A redução (estilo ccdproc, simplificada p/ tempo real)

```
calibrado = clip(light − master_dark, 0) / master_flat_normalizado
master_flat_normalizado = (mean(flats) − master_bias) / mean(...)      # média ≈ 1
```

| Master | Construído de | Remove |
|---|---|---|
| **master_dark** | N frames de obturador fechado | bias + corrente de escuro + **pixels quentes** |
| **master_flat** | N frames de campo uniforme (normalizado) | **vinheta** + poeira (resposta do sistema) |
| **master_bias** | N exposições ~zero | offset de bias (usado sem dark e p/ calibrar o flat) |

Os masters ficam residentes na VRAM. Reuso para o **FITS offline**: `astropy`/`ccdproc` (ver docs/08).

## API

```python
from src.gpu.calibration import Calibrator
cal = Calibrator.from_frames(dark=[...], flat=[...], bias=[...])   # constrói os masters
frame_calibrado = cal.apply(light_frame)                          # aplica (GPU)
```

Injeta-se no pipeline via `Session(..., calibrator=cal)` → `run_stack` usa em cada frame.

## Simulador: artefatos + frames de calibração

O `StarFieldSimulator` agora injeta (quando ligado no `SimConfig`) os mesmos defeitos fixos em
**light e frames de calibração**, para testar/demonstrar de verdade:
`bias`, `dark_current`, `hot_pixel_frac`, `vignette`, `flat_level`. Geradores: `bias_frame()`,
`dark_frame()`, `flat_frame()`. (Padrão OFF → não perturba os demais demos.)

## Como ver

```bash
python run_fase1.py --calibrate          # injeta bias/dark/vinheta/pixels quentes e corrige, ao vivo
```

## Validação (PC de dev, 2026-07, na GPU)
- Teste end-to-end (`tests/test_calibration.py`): **vinheta achatada** (razão canto/centro → ~1) e
  **pixels quentes removidos** após calibrar. Masters (bias/dark/flat) e normalização do flat testados.
- `run_fase1 --calibrate`: 14/15 frames aceitos, SNR 5,2× — rodando em **CuPy/GPU (RTX 4070)**.
- Regressão do bug de dimensão do simulador coberta (`test_session_syncs_simulator_dimensions`,
  `test_calibrated_pipeline_runs_at_custom_size`). **67 testes verdes.**

## No hardware
Trocar os frames sintéticos por darks/flats reais da ASI585MC (mesma temperatura p/ o dark). O
`Calibrator` e o `from_frames` **não mudam**; a leitura de FITS entra via astropy/ccdproc.
