# 12 — Fase 3: Agendador multi-alvo (Plan mode)

Sessão autônoma que percorre uma **fila de alvos** sozinha — como o DWARF a noite toda.
Para cada alvo: **auto-find → autofoco → live stack por N frames → próximo**. Compõe os
métodos do `Session` (Fases 1 e 2) sem duplicar nada. Ver [`docs/11`](11-arquitetura-recomendada.md).

## O que faz

1. Ordena os alvos por **prioridade** (maior primeiro).
2. **Filtra por visibilidade** (`Target.visible` — bool ou callable; no hardware vem de
   altitude/tempo via astropy). Alvos não visíveis são pulados e listados.
3. Para cada alvo visível: `auto_find` → (`autofocus`) → `run_stack(frames=t.frames)`.
4. **Robustez:** se o auto-find falha num alvo, registra `falha-autofind` e **segue para o
   próximo** — um alvo ruim não derruba a noite.
5. Atualiza `stats` (`target`, `queue_done/queue_total`) → o live view mostra o alvo e o progresso.

## Máquina de estados

Novo estado **`SCHEDULING`** (entre alvos). Ciclo por alvo:

```
SCHEDULING → SLEWING → SOLVING → FOCUSING → STACKING → SCHEDULING → … → IDLE
```

O invariante de segurança continua (SLEWING nunca vai direto a STACKING). Ver `src/core/state.py`
e `tests/test_state.py`.

## Arquivos
- `src/core/scheduler.py` — `Target` (dataclass) + `Scheduler`.
- `src/core/orchestrator.py` — `run_stack(frames=…, label=…)` (orçamento e nome por alvo).
- `src/core/state.py` — estado `SCHEDULING` + transições.
- `run_scheduler.py` — entrada (com `--loop`).

## Como rodar

```bash
python run_scheduler.py                    # M31→M42→M45, 60 frames cada, live em :8000
python run_scheduler.py --loop             # repete a agenda (demo)
python run_scheduler.py --no-web --frames 8   # headless rápido
```

No live view o banner mostra `Fase: empilhando · M31 (1/3)` etc. Saídas por alvo em
`output/stack_<alvo>.png`.

## Validação (PC de dev, 2026-07)
- Percorreu **M31 (pri 3) → M42 (pri 2) → M45 (pri 1)** em ordem, cada um centralizado, focado
  (~6208–6283) e empilhado. Transições de estado válidas, sem crash.
- Testes (`tests/test_scheduler.py`): ordem por prioridade, alvo invisível pulado, **falha de um
  alvo não derruba a agenda**, stats de fila atualizados. 61 testes verdes no total.

## No hardware (bring-up)
`Target.xy` vira (RA, DEC); `visible` passa a checar **altitude/janela de tempo** (astropy) e o
mount/solver reais entram no lugar dos `Sim*`. O `Scheduler` **não muda**.

## Próximo
Calibração completa (darks/flats — reuso ccdproc), saída FITS+WCS, e as features de reuso
(mosaico/Siril, denoise/GraXpert, filtros). Ver [`docs/04-roadmap.md`](04-roadmap.md).
