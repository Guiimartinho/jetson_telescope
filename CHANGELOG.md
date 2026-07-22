# Changelog

Todas as mudanças notáveis do projeto. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); datas em ISO (AAAA-MM-DD).

## [Não lançado]

### T7/T21/T22 — CI + git, catálogo do céu, mais alvos reais (2026-07-21)
- **T22 catálogo**: `src/core/catalog.py` (OpenNGC/pyongc, ~14k objetos) — `find()` (RA/DEC p/ GOTO),
  `Rig` (FOV+mag limite), `framable()` (1868 capturáveis c/ nosso rig), `visible()` (altitude); `run_catalog.py`.
  GOTO aponta em QUALQUER alvo. Doc `docs/26`.
- **T21 alvos**: baixados/processados M51 (galáxia) + NGC2244 (Roseta) do MILAN → Estúdio com 3 alvos reais.
  Script ganhou `--mono` + `remove_hot_pixels` (`gpu/calibration`, testado) — corrige "walking noise" sem darks. `docs/27`.
- **T7 CI**: `git init` + commit inicial (main, 148 arquivos), `.github/workflows/ci.yml` (pytest `-m "not
  hardware"` + CTest), `.gitignore` + `requirements.txt` completos. **166 testes verdes no modo CI.**
- Deconvolução Richardson-Lucy + denoise (`postproc/deconv.py`) + preset H-alpha no estúdio. Doc `docs/25`.

### Painel: foto real visível + correção do congelamento (2026-07-21)
- **Modo "Dados reais (M67)"** no painel (`capture/real_source.py` `RealFitsSource` + `_run_realdata`):
  empilha a FOTO REAL do M67 ao vivo (registro por estrelas reais + lucky imaging), tornando o dado do
  T15 visível na UI. Relaxa o gate de FWHM (PSF real ~10px). Validado: 30 subs, SNR ~7,8x.
- **Fix (congelamento):** um modo que terminava SOZINHO (sem Parar) deixava o painel preso no último
  estado (STACKING) → botões pareciam mortos. `Controller._run_mode` ganhou `finally` que leva a IDLE/
  STOPPED ao fim de qualquer modo (`run_stack` continua sem forçar estado, p/ o agendador compor).
- Página visual de validação (artifact) com a foto real + estrelas detectadas + tabela dos modos.
- Testes: +3 (foto real source, modo realdata, regressão de congelamento). **143 verdes + 5 pulados.**

### T16 — Auto-find celeste em malha fechada RA/DEC (2026-07-21)
- **`control/autofind_radec.py`** `close_loop_goto`: o "apontar sozinho" em coordenadas celestes —
  slew→plate-solve→sync até centralizar (~2 iters). `angular_sep_arcmin` (haversine). Amarra T13+T14.
- Dublês `SimRaDecMount`/`SimRaDecSolver` (análogos celestes de SimMount/SimSolver); `IndiMount` ganhou
  `goto/sync/position` em GRAUS (converte p/ as HORAS do INDI) → o MESMO laço serve sim e hardware.
- Painel: botão **GOTO (RA/DEC)** (`run_app.py`), erro em arcmin ao vivo. Validado: M42 **19,4→0,36 arcmin**.
- Testes: +7 (`test_autofind_radec.py` 6 + controller goto). **140 verdes + 5 pulados.** Doc `docs/22`.

### T14–T15 — Solver ASTAP real + validação com dados reais (2026-07-21)
- **T14** `control/solver.py`: `AstapSolver` chama o **ASTAP** de verdade (salva FITS → CLI → parseia
  o `.ini` → `WcsInfo`) + `parse_astap_result` (parser puro). `astap_bin` aceita argv-prefixo → testado
  com um **ASTAP falso** (`tests/fake_astap.py`); sem ASTAP, falha limpa (`None`). Integração real em
  `test_solver_integration.py` (marker `hardware`, pulado).
- **T15** validação do pipeline com **dados REAIS**: campo estelar de M67 (`tests/data/real_starfield_
  m67.fits`, via `scripts/fetch_real_data.py`/photutils). Detecção 60 estrelas, FWHM real ~10px, registro
  correlação **0,215→0,995**, empilhamento **σ 60→15 = √16 (4,0×)**. Pega o que o simulador esconde.
- Testes: +12 (`test_solver_astap.py` 7, `test_real_pipeline.py` 5). **133 verdes + 5 pulados.** Doc `docs/21`.
  Milestone D quase fechado — resta só **T7 (CI)**.

### T13 — Camada INDI validada sem hardware (2026-07-21)
- **`io/indi_client.py`**: cliente INDI **puro-Python** (socket + XML, stdlib) — substitui o
  `pyindi-client`, que não roda no Windows. Roda no PC de dev E na Jetson; testável na CI.
- **Adapters reescritos** sobre o cliente: `IndiCameraSource` (CCD_EXPOSURE→BLOB FITS), `IndiMount`
  (EQUATORIAL_EOD_COORD, RA/DEC nativo), `IndiFocuser` (ABS_FOCUS_POSITION), `IndiFilterWheel`
  (FILTER_SLOT/FILTER_NAME). Antes eram escafolds que levantavam `NotImplementedError`.
- **`tests/fake_indi.py`**: servidor INDI falso (imita os `indi_simulator_*`) → testa a fronteira de
  hardware inteira no Windows. `scripts/run_indi_sim.sh` sobe os simuladores reais no WSL/Jetson.
- Testes: +13 (`test_indi_client.py`, `test_indi_adapters.py`) + 4 de integração (`hardware`, pulados
  no CI). Atualizados os testes de robustez (adapters agora falham com erro de conexão claro, não stub).
  **121 testes verdes** (4 pulados). Doc `docs/20`. Milestones D/E/F em `TASKS.md`.

### T12 — Painel de controle + Noite autônoma; correção do "Parar" (2026-07-21)
- **`core/autonomous.py`** (`AutonomousNight` + `Observation`) + `run_night.py`: noite sem operador.
- **`core/controller.py`** + `run_app.py`: painel web que roda TODOS os modos (Empilhar/Auto-find/
  Agendador/Mosaico/Rastrear/Noite/Parar) sob demanda, em `http://localhost:8000`.
- **Fix de concorrência 1:** trocar de modo travava em `STOPPED` (terminal) → `Session.reset_state()`
  chamado por `Controller._start` após esperar o worker morrer (loop-join, sem órfão revivido).
- **Fix de concorrência 2:** o "Parar" parecia não funcionar — o worker *parava* (`state=STOPPED`),
  mas `/stats` mostrava `STACKING` para sempre. `_set_state` não empurrava o estado ao `FrameHub`.
  Corrigido: `_set_state`/`reset_state` agora chamam `_publish()`. Painel atualiza na hora.
- Testes: +regressões em `test_controller.py` (recupera de STOPPED, troca de modo, hub reflete stop).
  Doc `docs/19`. T12 fechado em `TASKS.md`.

### Fase 4 (T8–T11) — rastreamento IA em tempo real (2026-07-21)
- **T8** `control/tracking.py`: `OpticalFlowTracker` (Lucas-Kanade; cv2.cuda/VPI na Jetson).
- **T9** `control/detector.py`: `BrightObjectDetector` (CV) + `YoloTensorRTDetector` (YOLO→TensorRT
  na Jetson, **fallback CV** no PC).
- **T10** `Session.track`: laço detecção → predição de velocidade → **feed-forward** ao mount; estado `TRACKING`.
- **T11** `capture/satellite.py` (objeto em movimento) + `run_tracking.py`. Erro de rastreio **~1 px**.
- Testes: +4 (`test_tracking.py`) → **100 testes verdes**. Doc `docs/18`. T8–T11 em `TASKS.md`.

### T2–T6 — pós-processo, filtros, controles web, perfis, persistência (2026-07-21)
- **T2** `postproc/enhance.py`: remoção de gradiente (fallback) + wrapper GraXpert; `--enhance` no run_stack.
- **T3** `control/filterwheel.py`: port + Sim/INDI + `filter_for_target`; `Target.filter` trocado pelo agendador.
- **T4** controles web: `FrameHub` com fila de comandos, `GET /cmd/<ação>`, botão **Parar**; `Session._poll_commands`.
- **T5** `core/vo.py` (Value Objects imutáveis) + `core/profiles.py` (YAML) + `profiles/*.yaml`.
- **T6** `core/session_store.py`: resumo de sessão (JSON) + `Telemetry` (JSONL); resumo salvo no run_stack.
- Testes: +19 → **96 testes verdes** (na GPU). Doc `docs/17`. T2…T6 marcadas em `TASKS.md`.

### T1 — Mosaico multi-painel + plano de execução (2026-07-21)
- **`TASKS.md`**: plano ordenado até a Fase 4 (T1…T12) + bring-up de HW depois.
- **`src/core/mosaic.py`** + `run_mosaic.py`: planeja a grade de painéis e captura cada um reusando
  o `Scheduler` (auto-find→autofoco→stack→FITS/WCS por painel); `stitch_siril` costura no Siril
  (pula com mensagem clara se ausente). Testes: +3 → **77 testes verdes**. Doc `docs/16`.

### Saída FITS/WCS + UI redesenhada (2026-07-21)
- **`src/io/fits_io.py`**: `save_fits`/`load_fits` + `WcsInfo` (reuso astropy). Salva o stack como
  FITS float32 com **WCS** (RA/DEC do plate solve) e metadados (OBJECT/NCOMBINE/DATE-OBS) —
  abre no Siril/PixInsight/ASTAP. Integrado ao `run_stack` (`stack_<alvo>.fits`).
- **UI do live view redesenhada** (`server/webview.py`): painel de controle — pílula de estado
  colorida, barra de progresso da fila de alvos, SNR em destaque, badge GPU/CPU, indicador "AO VIVO".
- Testes: +3 (`test_fits.py`) → **74 testes verdes**. Doc `docs/15`.

### Otimização de GPU + benchmark (2026-07-21)
- **Warp afim** e **variância do Laplaciano** movidos para a GPU (`cupyx.scipy.ndimage`);
  stack já era CuPy. Pipeline **mantém o frame na VRAM** (calibração→warp→stack), baixando só o
  cinza 1× para a detecção — minimiza cópias Host↔Device (Entregável #1 do CLAUDE.md).
- `scripts/benchmark_gpu.py` — **speedup medido no RTX 4070**: warp **49×**, stack **41×**,
  laplaciano 9,6× em 4K.
- `cv2.cuda` indisponível no pip (CPU-only) → usamos cupyx; na Jetson o cv2.cuda compilado é alternativa.
- Testes: +4 (`test_gpu_ops.py`, warp GPU≈CPU) → **71 testes verdes (na GPU)**. Doc `docs/14`.

### Calibração completa + GPU no PC de dev (2026-07-21)
- **`gpu/calibration.py`**: `Calibrator` completo (bias/dark/flat), `build_master`,
  `build_master_flat` (normalizado), `from_frames`. Corrige bias, corrente de escuro,
  **pixels quentes** e **vinheta**. Injetável via `Session(calibrator=…)`; `run_fase1 --calibrate`.
- **Simulador**: artefatos fixos do sensor (bias/dark/hot-pixels/vinheta) + geradores
  `bias_frame()`/`dark_frame()`/`flat_frame()` (padrão OFF).
- **GPU validada no PC de dev (RTX 4070, CUDA 12.9)**: `cupy-cuda12x` instalado → toda a suíte
  e o pipeline rodam em **CuPy/GPU** (mesma família da Jetson) — de-risca o caminho GPU.
- Correção de bug: dimensões do simulador não sincronizavam com o pipeline (regressão coberta).
- Testes: +6 → **67 testes Python** verdes (agora na GPU). Doc `docs/13-calibracao.md`.

### Fase 3 (parte) — Agendador multi-alvo / Plan mode (2026-07-21)
- **`core/scheduler.py`** (`Target` + `Scheduler`): percorre uma fila de alvos sozinho
  (auto-find → autofoco → stack por alvo), por prioridade e com filtro de visibilidade.
  Falha num alvo não derruba a agenda. Entrada `run_scheduler.py` (com `--loop`).
- **State machine:** novo estado `SCHEDULING` (entre alvos), preservando o invariante de segurança.
- **`run_stack(frames=…, label=…)`**: orçamento de integração e saída (`stack_<alvo>.png`) por alvo.
- Pausas de ritmo agora só ocorrem com live view (headless/CI mais rápido).
- Testes: +4 (`tests/test_scheduler.py`) → **61 testes Python** verdes.

### Fase 2 — Autonomia (2026-07-21)
- **Auto-find (GOTO + plate solving):** laço `slew → solve → corrige → centraliza`
  (`Session.auto_find`). Validado: erro 556 → 1,6 px em 2 iterações.
- **Autofoco:** curva-V/hipérbole com *bracketing* do mínimo (`control/autofocus.py`).
  Validado: foco crítico em 6294 (real 6300).
- **Ports de controle:** `control/{mount,focuser,solver}.py` (adapters `Sim*` + escafolds
  `Indi*`/`Astap*` p/ hardware) e `capture/sky.py` (céu apontável). `run_fase2.py` (com `--loop`).
- **State Machine explícita** (`core/state.py`): IDLE/SLEWING/SOLVING/FOCUSING/STACKING/ERROR/
  STOPPED, com invariante de segurança (não empilha após slew cego) — integrada ao orquestrador.

### Fase 1 — Live Stacking MVP (2026-07-21)
- **Pipeline GPU** (o diferencial): `gpu/stacker.py` (média ponderada float32 na VRAM),
  `gpu/quality.py` (FWHM por área a meia-altura + Var. Laplaciana), `gpu/registration.py`
  (astroalign com fallback cv2), `calibration.py`, `debayer.py`.
- **Backend agnóstico** (`backend.py`): CuPy/GPU na Jetson, NumPy/CPU no PC — mesmo código.
- **Captura:** `capture/{simulator,source,ring_buffer,indi_source}.py` (roda sem câmera).
- **Live view web** (`server/webview.py`): stream MJPEG + stats, sem dependências extras.
- **Orquestrador** (`core/orchestrator.py`) + `run_fase1.py`. Validado: SNR ~9,9× em 50 frames.

### Engenharia — arquitetura & testes (2026-07-21)
- **Suíte de testes:** 57 testes Python (`pytest`: unit, propriedades/hypothesis, robustez,
  integração/contrato) + 5 casos C++ (`doctest`/CTest, `cpp/`). Todos verdes.
- **Docs de engenharia:** `docs/10` (arquitetura testável + pirâmide) e `docs/11` (decisão de
  arquitetura: Hexagonal + Pipes&Filters + State Machine; TDD sim, DDD não).
- Convenções anexadas ao `CLAUDE.md`; `.gitignore`, `pytest.ini`, `cpp/CMakeLists.txt`.

### Planejamento & pesquisa (2026-07-20 → 21)
- **Documentação de projeto** `docs/01..09`: hardware/BOM, arquitetura de dados (zero-copy),
  pipeline, roadmap, setup da Jetson, aceleração & técnicas, reusar-vs-construir, Fase 2.
- **Pesquisa de mercado (mid-2026):** compute Orin NX 16GB (dev em Orin Nano Super 8GB),
  câmera Sony IMX585 (ZWO ASI585MC), montagem ZWO AM3N, óptica ~250mm, ASTAP/cedar-solve.
- **Comparativo visual** com o DWARFLAB DWARF 3 (Artifact): placar 11×7×5 + implicações de arquitetura.
- Restrição adotada: **somente software FOSS/grátis**.
