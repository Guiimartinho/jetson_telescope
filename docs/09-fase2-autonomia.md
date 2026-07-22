# 09 — Fase 2: Autonomia (auto-find + autofoco)

Adiciona à Fase 1 o que o DWARF faz sozinho: **procurar e centralizar o alvo** (o *auto-find*)
e **focar**. Tudo demonstrável **sem hardware** (montagem/foco/solver simulados) e pronto para
trocar por INDI/ASTAP na Jetson **sem tocar no núcleo**. Ver [`docs/08`](08-reusar-vs-construir.md).

## A sequência autônoma (o que o `run_autonomous` faz)

```
1. slew 'bruto' p/ o alvo         mount.slew()      → erra por ~centenas de px (erro mecânico)
2. AUTO-FIND (laço fechado):      solver.solve()    → RA/DEC real
     erro = solved − alvo         mount.nudge()     → corrige; repete até erro < tolerância
3. AUTOFOCO:                      curva-V de FWHM   → bracketa o mínimo → hipérbole → foco crítico
4. LIVE STACK:                    (o núcleo da Fase 1)
```

## Componentes (injetados no orquestrador)

| Papel | Simulação (PC) | Hardware (Jetson) — REUSO |
|---|---|---|
| Montagem | `SimMount` (erra o GOTO, deriva) | `IndiMount` → `indi_lx200am5` (AM3N) |
| Focalizador | `SimFocuser` (foco ótimo oculto) | `IndiFocuser` → `indi_asi_focuser` (EAF) |
| Plate solver | `SimSolver` (verdade + ruído) | `AstapSolver` / cedar-solve |
| Câmera/céu | `SkyModel` + `SkyCameraSource` | câmera INDI (Fase 1) |
| Autofoco | `AutoFocuser` (algoritmo do Ekos: hipérbole) | idem — mesmo código |

Arquivos: `src/control/{mount,focuser,solver,autofocus}.py`, `src/capture/sky.py`,
`src/core/orchestrator.py` (métodos `auto_find`, `autofocus`, `run_autonomous`).

## Como rodar

```bash
python run_fase2.py                 # alvo M31, live view em http://localhost:8000
python run_fase2.py --loop          # cicla M31→M42→M45 (find+foco+stack em cada) — bom p/ demo
python run_fase2.py --no-web --frames 25 --target M42   # headless
```

Na Jetson (quando o hardware chegar): trocar as fábricas em `run_fase2.py` por `IndiMount`/
`IndiFocuser`/`AstapSolver` e a fonte por a câmera INDI. `auto_find`/`autofocus`/`run_stack` não mudam.

## Validação (PC de dev, 2026-07)
- **Auto-find:** erro **556,8 px → 1,6 px em 2 iterações** (centralizou).
- **Autofoco:** curva-V bracketada; foco crítico em **6294** (real 6300, erro 6 passos), FWHM 3,91.
- **Stacking:** 25/25 aceitos, SNR ~6,7×. Modo `--loop` cicla os 3 alvos indefinidamente.

## Pendências → Fase 3
- `IndiMount`/`IndiFocuser`/`AstapSolver` são escafolds: implementar no bring-up do hardware.
- Fase 3: mosaico (Siril), filtros, agendador multi-alvo (reuso do scheduler do Ekos), denoise IA (GraXpert).
