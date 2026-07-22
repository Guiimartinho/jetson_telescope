# 19 — Painel de controle + Noite autônoma (T12)

Fecha a Fase 3+: um **orquestrador de alto nível** que roda a noite inteira sem operador, e um
**painel web** para testar TODOS os modos pelo navegador.

## Noite autônoma (`core/autonomous.py`)

`AutonomousNight.run([Observation(...), ...])` amarra tudo por alvo, na ordem de prioridade:
agendar → (calibrar) → auto-find (slew+solve+corrige) → autofoco → stack → denoise → FITS.
`run_night.py` roda uma "noite" sintética e produz saídas de vários alvos. Teste: a noite gera
os arquivos esperados de cada alvo.

## Painel de controle (`core/controller.py` + `run_app.py`)

Um servidor único que monta o mundo simulado **uma vez** e roda qualquer modo sob demanda:

```
navegador ──/cmd/start:<modo>[:<alvo>]──▶ WebView ──on_command──▶ Controller.submit ──┐
navegador ──/cmd/stop───────────────────▶                                             │
                                                        Controller._loop (thread) ◀────┘
                                                             │ dispatch
                                        ┌────────────────────┴───────────────────┐
                                    start:X → _start (troca de modo)          stop → session.stop=True
                                        │ (mata o worker atual, reset_state,       │
                                        │  sobe o novo numa thread)                ▼
                                        ▼                                   run_* checa self.stop
                                  _run_mode: stack | autofind | scheduler |
                                             mosaic | tracking | night
```

Modos: **Empilhar / Auto-find / Agendador / Mosaico / Rastrear / Noite** (+ **Parar**). O painel
mostra estado/fase, fila, SNR em destaque, erro em px e badge de GPU. Abra `http://localhost:8000`.

## Dois bugs de concorrência resolvidos (o que fez o "Parar" funcionar)

1. **Troca de modo travava em STOPPED.** `STOPPED` é um estado terminal na máquina de estados; ao
   iniciar o próximo modo, a transição a partir de STOPPED levantava `InvalidTransition`. Correção:
   `Session.reset_state()` (máquina nova + flags limpas), chamado por `Controller._start` **depois**
   de esperar o worker anterior morrer (loop-join, evita "órfão revivido").

2. **O painel parecia não parar (mas parava).** Sutil: o worker encerrava certo (`state=STOPPED`),
   mas o `/stats` continuava mostrando `STACKING` para sempre. Causa: `_set_state` só atualizava o
   `self.stats` do Session — **nunca empurrava** o estado novo para o `FrameHub` (de onde o `/stats`
   lê). O hub ficava preso no último frame empilhado. Correção: `_set_state` (ponto único de troca de
   estado) agora chama `_publish()`, refletindo cada transição no painel na hora.

3. **Painel congelava quando o modo terminava sozinho.** Um modo que acaba por conta própria (ex.:
   "Dados reais" após N frames, GOTO após centralizar) — sem apertar Parar — deixava o estado preso no
   último (STACKING), fazendo os botões de cima parecerem mortos. Causa: só se setava STOPPED **se o
   usuário tivesse parado**. `run_stack` é bloco reutilizável (o agendador o chama por alvo), então quem
   encerra é o ponto de entrada: `Controller._run_mode` ganhou um `finally` que leva o painel a IDLE
   (pronto) / STOPPED ao fim de QUALQUER modo. Regressão: `test_mode_completing_naturally_leaves_panel_ready`.

Regressões travadas em `tests/test_controller.py`:
`test_reset_state_recovers_from_terminal_stopped`, `test_controller_switches_between_modes`,
`test_hub_stats_reflect_stopped_after_stop`. Validado ponta a ponta via HTTP: os 6 modos iniciam,
trocam e **param** de forma confiável.

Ver `TASKS.md` (T12) e `docs/18` (os modos de rastreamento).
