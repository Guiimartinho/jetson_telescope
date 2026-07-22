# 17 — T2…T6: pós-processo, filtros, controles web, perfis, persistência

Cinco features do Milestone A/B do `TASKS.md`. Todas testadas (parte da suíte de **96 testes**).

## T2 — Pós-processo IA (`src/postproc/enhance.py`)
- `enhance(image, gradient=True, denoise=False)`: remove gradiente + (opcional) denoise.
- **Reuso:** GraXpert (CLI/ONNX→TensorRT) quando instalado. **Fallback embutido:** `remove_gradient`
  (estima fundo suave por downscale→blur→upscale e subtrai) — passo astro real, preserva estrelas.
- Ligado ao `run_stack` via `SessionConfig.enhance` → salva `stack_<alvo>_enh.png`.

## T3 — Roda de filtros (`src/control/filterwheel.py`)
- Port `FilterWheel` + `SimFilterWheel` + `IndiFilterWheel` (escafold). `filter_for_target(kind)`:
  galáxia→**L-Pro**, nebulosa→**L-eXtreme**, padrão→VIS.
- `Target.filter` + `Session.filterwheel`/`set_filter`; o agendador troca o filtro por alvo.

## T4 — Controles no navegador (`server/webview.py`)
- `FrameHub` ganhou fila de comandos; endpoint **`GET /cmd/<ação>`**; botão **"⏹ Parar"** na UI.
- `Session._poll_commands()` consome a fila nos laços (`auto_find`, `run_stack`) → **parar pela web**.

## T5 — Value Objects + perfis (`src/core/vo.py`, `profiles.py`)
- Value Objects imutáveis (DDD tático): `Pointing`, `Fwhm`, `PixelScale`, `EquipmentProfile`
  (com `pixscale` e `fratio` derivados). Trocar rig sem código: **YAML** em `profiles/*.yaml`.
  Ex.: `load_profile("profiles/redcat51_am3n_imx585.yaml")` → escala 2,39"/px, f/4,9.

## T6 — Persistência + telemetria (`src/core/session_store.py`)
- `save_session`/`load_session` (resumo JSON por alvo — target/accepted/snr/filter/when), gravado
  ao fim do `run_stack` (`session_<alvo>.json`). `Telemetry` = log append-only JSONL para análise/resume.

## Validação (2026-07, GPU)
Testes por task: T2 (3), T3 (5), T4 (3), T5 (6), T6 (2). **96 testes verdes.**
Escafolds/reuso (GraXpert, INDI filterwheel, Siril) falham/pulam de forma clara sem o binário.
