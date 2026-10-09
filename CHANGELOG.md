# Changelog

Todas as mudanças notáveis do projeto. Formato baseado em
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/); datas em ISO (AAAA-MM-DD).

## [Não lançado]

### Link automático Jetson ↔ montagem + drivers dos motores validados (2026-10-09)
- **Do plugar até a montagem pronta, nenhum passo manual.** `scripts/jetson_setup_mount.sh`
  instala: regra udev → **`/dev/telescope-mount` em qualquer porta USB**; e
  `telescope-indi.service`, amarrado ao dispositivo, que sobe quando a placa aparece e cai
  quando o cabo sai. Arquivos versionados em `deploy/jetson/`.
- **`IndiMount` fecha as duas lacunas do teste manual:** configura porta e baud da serial
  antes do `CONNECT` (o INDI abre a 9600 por padrão) e ganhou `set_site_and_time()` — o
  OnStepX acorda em 2000-01-01, lat/long 0, e sem hora e local um goto por RA/DEC erra.
  Falha de conexão vira `ConnectionError` claro e imediato, não timeout mudo.
- **`MountLink` (`src/control/mount_link.py`):** mantém a montagem conectada sozinha —
  conecta quando o indiserver aparece, reenvia hora e local a cada reconexão, percebe a
  queda do cabo pelo socket fechado e volta a tentar. Ligado por `TELE_MOUNT=indi` (o serviço
  da Jetson define; PC e CI seguem nos simuladores).
- **Console:** `/api/state` ganhou `mount` e o cabeçalho mostra "montagem conectada /
  desconectada / simulada".
- **`IndiClient`:** `alive` (o servidor fechou a conexão?) e `wait_change()` (espera a
  resposta a um comando nosso sem se enganar com um `Alert` antigo).
- **Verificado na Orin:** hora, fuso e coordenadas lidos de volta pelo WiFi da própria placa;
  a casa da montagem passou a apontar o polo **sul** celeste ao receber a latitude; INDI
  parado e religado, o link voltou sozinho; no **reboot da Jetson**, "montagem conectada"
  antes de 30 s de boot sem tocar em nada; e, com o **cabo trocado de porta USB**, o INDI
  parou e voltou sozinho e o console reconectou em cerca de 2 s.
- **Drivers TMC2209 validados no hardware.** O OnStepX só confere os drivers sob
  `MOTOR_DRIVER_DETECT`; sem isso um pino de UART errado não vira erro. Novo build de
  diagnóstico (`idf.py -DONSTEPX_DIAG=ON build`): os três eixos reportaram
  `motor driver device detected` em GPIO21/22 — a correção de pinagem de setembro está
  confirmada na placa. `config_assert.cpp` recusa um build de produto com `DEBUG` ligado.
- **Gravação pela própria Jetson** (`scripts/jetson_flash_mount.sh`, `scripts/mount_bootlog.py`):
  o diagnóstico entrou e o firmware de produto voltou pelo mesmo cabo do link. A placa não
  precisa mais voltar ao PC.
- **Fix: as telas mostravam "CPU" com tudo parado.** O hub só recebia o campo `backend`
  quando um modo rodava; ocioso ficava vazio, e console e painel caíam no padrão "CPU" com o
  pipeline em CuPy/GPU. O `Controller` agora publica o estado inicial (IDLE + backend real).
- Testes: +19 (`test_mount_link.py` 15, `test_console.py` 2, `test_firmware_config.py` 1,
  `test_controller.py` 1), contra um servidor INDI falso que agora imita o
  `indi_lx200_OnStep` (só conecta com porta e baud certos; acorda sem hora nem local; pode
  "morrer" e voltar). **260 verdes** + 5 pulados. Doc `docs/35` §9–10.
- **Em aberto:** os modos do painel (GOTO, agendador, rastreio) ainda usam os simuladores —
  trocar pela montagem real exige a mecânica; calibração (passos/grau, sentido, limites).

### Primeiro flash do OnStepX na E4 + link serial com a Jetson (2026-10-09)
- **A controladora está gravada e viva.** Fonte de 12V na bancada; placa lida pelo USB do PC
  (ponte CH340): ESP32-D0WD-V3 rev 3.1, **16 MB de flash confirmados na placa**. Antes de
  qualquer escrita, **backup integral do firmware de fábrica** (Marlin bugfix-2.0.x sobre
  ESP-IDF 3.2.3; 16.777.216 bytes em `firmware/backup/`, fora do git). Depois `erase-flash`
  e gravação de bootloader + partições + app, com hash verificado.
- **Teste de fumaça LX200 pela serial** (só consultas): `:GVP#` → `On-Step#`, versão
  `10.28x`, em casa apontando o polo, focalizador presente. Pronta para comandos 7,7 s após
  o reset. Binário: **1.054.576 bytes** (66% livres).
- **Correção de rumo — o link da Jetson é o cabo, como era o plano.** Em setembro, ao ver
  que o kernel do JetPack 6 não traz o driver CH340, o link foi virado para WiFi e isso foi
  documentado como decisão. O problema real custava dez minutos:
  `scripts/jetson_install_ch341.sh` compila o módulo `ch341` do kernel mainline para o
  kernel em execução e mascara a regra udev do `brltty`, que no Ubuntu 22.04 derruba o
  CH340 segundos depois de ele aparecer. Instalado e carregado na Orin.
- **O WiFi da placa fica, como acesso secundário:** ponto de acesso próprio
  (`OnStep-Telescopio`, LX200 sobre TCP em `192.168.0.1:9999`). A senha mora em
  `firmware/config/Config.local.h`, **fora do git**, gerada aleatória pelo
  `fetch_onstepx.py`; a Config versionada recusa compilar sem ela, então nunca sai um
  firmware com a senha padrão do OnStepX. Modo estação ficou de fora de propósito (exigiria
  a senha da rede de casa no firmware) e uma trava de compilação impede que volte.
  Verificado de ponta a ponta: um PC entrou no AP e `:GVP#` pela TCP 9999 devolveu `On-Step#`.
- **Log do IDF em `WARN`.** O console divide a UART0 com o canal LX200; em `INFO` o WiFi
  imprimiria uma linha a cada cliente do AP, no meio das respostas que o INDI lê.
  Verificado: 0 bytes espontâneos na serial enquanto um cliente entrava e saía do AP.
- **O que a bancada desmentiu:** `docs/35` dizia que a E4 "não se alimenta pelo USB:
  comprovado por não enumerar". Com os 12V ligados ela continuou fora do `lsusb` da Jetson
  (que não depende de driver) e enumerou na hora no PC. O sintoma era real; a causa não
  estava provada, e a da Jetson segue em aberto.
- Testes: `test_firmware_config.py` passou de 17 para 22 (link serial num baud do INDI,
  rádio só como AP, nenhuma credencial versionada, log em `WARN`, arquivo de segredos gerado
  e nunca sobrescrito) + duas travas novas em `config_assert.cpp`. `.gitattributes` força LF
  nos `.sh` (com `autocrlf` eles quebrariam na Jetson).
- **Link validado na Jetson, de ponta a ponta, sem mudar uma linha do nosso código:**
  `1a86:7523` → `ch341` → `/dev/ttyUSB0` (aberto pelo usuário comum) → `indi_lx200_OnStep`
  a 115200 → `IndiMount.get_radec()` devolveu RA 12,77 h / DEC +90°, a casa da GEM. Abrir a
  porta não reinicia a placa. A não-enumeração anterior na Jetson era a ligação do cabo.
- **Em aberto:** `IndiMount` precisa configurar porta e baud da serial (hoje feito à mão; o
  INDI abre a 9600); a Jetson tem de enviar hora e local na conexão (a montagem reporta
  `UTC 2000-01-01` e lat/long 0 — sem isso um goto por RA/DEC erra); **validar a UART dos
  TMC2209 no hardware** — `:GXU1#` devolve `0` porque o monitoramento vem desligado e a
  detecção só existe sob `MOTOR_DRIVER_DETECT`, então hoje um pino de UART errado não
  viraria erro. Doc `docs/35` §8–9.

### Firmware da montagem: OnStepX como projeto ESP-IDF 6 (2026-09-08)
- **`firmware/`**: projeto ESP-IDF 6 completo para a **FYSETC E4** (ESP32-WROOM-32E) —
  `CMakeLists`, `sdkconfig.defaults`, `partitions.csv` (16MB com OTA), componente `main`,
  componente `onstepx` e scripts. Doc `docs/35`.
- **Migração pelo caminho oficial, não por reescrita.** O OnStepX tem **432 arquivos /
  66.367 linhas** (o `.ino` em si são 161). Reescrevê-lo em API nativa do IDF seria meses
  num código de tempo real, e contra o princípio de reuso (`docs/08`). Em vez disso,
  `arduino-esp32` entra como **componente gerenciado do IDF** — ele declara
  `idf: ">=5.3,<6.2"` e a release 3.3.9 adicionou suporte a IDF 6.0. Resolvido: 3.3.11.
- **Poda em camadas** (`scripts/prune_onstepx.py`): remove o que não é alcançável na E4.
  Camada 1 aplicada — **−33 arquivos, −3.645 linhas** (HAL de atmel/STM32/Teensy/mbed/
  arduinoM0 + 17 pinmaps de outras placas). Camadas 2 e 3 declaradas para aplicar aos poucos,
  cada uma com build verde antes da seguinte.
- **Achado que virou teste — a UART dos TMC2209.** A tabela de pinos oficial da FYSETC (e o
  Marlin) põem a UART dos drivers em **GPIO21/22**; o pinmap `FYSETC_E4` do OnStepX usa
  **GPIO15**, que nesta placa é o **Z-MIN/Z-DIAG**. O padrão não alcançaria os drivers e
  colidiria com o endstop. Corrigido na nossa Config + patch que torna `SERIAL_TMC_TX`
  sobrescrevível (o pinmap o redefinia sem guarda, descartando nossa escolha em silêncio).
- **Atrito arduino-esp32 × IDF 6** documentado e resolvido cirurgicamente: `-Werror` do IDF 6
  transformava dois avisos de bibliotecas do Arduino em erro fatal. Rebaixados **só** nesse
  componente (`LittleFS`), e o do mbedTLS resolvido fazendo o que o aviso pedia
  (`CONFIG_MBEDTLS_PSK_MODES`). Nosso código e o do OnStepX seguem sob `-Werror`.
- **A árvore do OnStepX não é versionada** — baixada pinada no commit `65a7518` (v10.28x)
  por `scripts/fetch_onstepx.py`, que instala a Config, aplica o patch e poda. Build
  reprodutível sem 66k linhas de terceiro no `git diff`.
- **Build VERDE no ESP-IDF v6.0.2** (alvo `esp32`): `onstepx_telescope.bin` = **1.063.440
  bytes**, 66% livres na partição de 3 MB. Outros erros achados e corrigidos pelo caminho:
  `SERIAL_B` não existe na E4 (o canal de rede é `SERIAL_RADIO`), `FileVersionConfig`
  ausente, e o OnStepX **não embute** o driver dos TMC (`<TMC2209.h>` é lib externa — virou
  o componente `firmware/components/tmc2209/`).
- **Política de warnings explícita:** `-Wno-error` **apenas** nos componentes de terceiro
  (`onstepx`, `tmc2209`) — o OnStepX é escrito para o toolchain Arduino e dispara avisos
  reais mas não acionáveis (`volatile--` do C++20, `unsigned < 0` dentro do `Arduino.h`).
  Nosso código e o do IDF seguem sob `-Werror`.
- Testes: **+26** (`test_firmware_config.py` 17, `test_firmware_prune.py` 9), sem placa nem
  toolchain, mais `config_assert.cpp` — travas de pinagem verificadas **após o
  pré-processador** (o valor que o compilador usou, não o texto da Config). **Ambos
  verificados com dentes**: injetando `SERIAL_TMC_TX 15`, dois testes falham e o **build
  para** com as mensagens escritas.
- ⛔ **Gravar continua bloqueado por uma fonte 12V** — a E4 não se alimenta pelo USB (não
  enumera nem na Jetson nem no PC). Ver `docs/34`.

### Prontidão de campo: arranque do Atlas + operação offline (2026-09-08)
- **Atlas abria em 78,8 s** no Orin (2ª chamada: 0,27 s) — no celular, lê como travado. Causa
  dominante: o **astropy tentava BAIXAR a tabela IERS** (~70 s), mais 6,6 s de carga do OpenNGC
  e 1,7 s da 1ª transformação de coordenada. `catalog.configure_astropy_offline()`
  (`auto_download=False` **+ `auto_max_age=None`**) + `console.warm_cache()` numa thread no
  arranque do serviço → **3,07 s no pior caso, 0,28 s aquecido**.
- **Elimina uma dependência de rede escondida:** `docs/33` promete campo sem internet, mas o
  cálculo de visibilidade saía para a rede a cada boot do serviço. Agora não sai.
- **Armadilha coberta por teste:** desligar só o `auto_download` **quebra** o cálculo
  (`ValueError ... predictive values ... more than 30.0 days old` — o caso real do Orin). O teste
  `test_altitude_still_works_offline` falhou primeiro e forçou a segunda trava. Trocar lento por
  quebrado teria sido pior.
- **`usermod -aG dialout`** na Jetson: `/dev/ttyUSB*` não abriria para o `indi_lx200_OnStep`
  (que roda como usuário) quando a controladora da montagem for plugada — pré-requisito do Milestone F.
- Testes: +5 (`test_catalog.py` 3, `test_console.py` 2). **210 verdes** (GPU) + 5 pulados;
  16/16 dos módulos tocados verificados no próprio Orin (aarch64, Py3.10, astropy 6.1.7). Doc `docs/34`.

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
