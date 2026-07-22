# TASKS — Plano de execução até a Fase 4

Ordem de execução das implementações restantes. **Definição de "pronto" (por task):**
código + **testes** (pytest, sem GPU/HW obrigatório) + **doc** em `docs/` + entrada no `CHANGELOG.md`.
Arquitetura: Ports & Adapters / Pipes & Filters / State Machine (ver `docs/11`).

## ✅ Concluído (base)
- Fase 1 (live stacking), Fase 2 (auto-find + autofoco), Fase 3 agendador multi-alvo.
- Calibração (bias/dark/flat), otimização GPU (warp/stack na GPU, benchmark ~40–50× em 4K),
  FITS/WCS (astropy), painel de controle web (todos os modos + Parar). Testes: **108 verdes** (GPU RTX 4070).
- Fase 4 (rastreamento IA: fluxo óptico + YOLO/TensorRT c/ fallback + feed-forward + satélite) e T1–T6, T12.

---

## Milestone A — Recursos de imagem (reuso)

### ✅ T1 — Mosaico multi-painel  *(feito — docs/16)*
- Dividir um alvo grande numa grade N×M; para cada painel: auto-find → autofoco → stack → FITS.
- **Reusar:** agendador, WCS (FITS), **Siril headless** para costurar os painéis.
- **Construir:** planejador de painéis, `core/mosaic.py` + `run_mosaic.py`.
- Feito: grade + captura por painel (reusa `Scheduler`), FITS por painel, `stitch_siril` (skip sem Siril).
  Testes: grade correta, 2×2 grava 4 FITS, stitch pula sem Siril. **77 testes verdes.**

### ✅ T2 — Pós-processo IA (denoise + gradiente)  *(feito — docs/17)*
- Aplicar **GraXpert** (CLI/ONNX) ao frame integrado (remoção de gradiente + denoise).
- **Reusar:** GraXpert (ONNX→TensorRT na Jetson). **Construir:** wrapper `postproc/enhance.py` com fallback.
- Testes: wrapper chama a ferramenta se instalada; sem ela, passa o frame adiante (no-op) sem quebrar.

### ✅ T3 — Roda de filtros  *(feito — docs/17)*
- Port **`FilterWheel`** + adapters `SimFilterWheel` / `IndiFilterWheel`; seleção por alvo
  (L-Pro p/ galáxias, dual-band p/ nebulosas em emissão).
- **Construir** o port + sim; **reusar** driver INDI no HW. Testes: contrato + troca de filtro por alvo.

---

## Milestone B — Produto / UX / robustez

### ✅ T4 — Controles no navegador  *(feito — docs/17: /cmd + botão Parar)*
- REST no `server/`: `POST /start`, `/stop`, `/goto?target=`, ajuste de stretch. UI ganha botões.
- **Construir.** Testes: endpoints respondem e disparam as ações no Session (via dublês).

### ✅ T5 — Config YAML + perfis de equipamento + Value Objects  *(feito — docs/17)*
- `config.yaml` com perfis (câmera/montagem/óptica/FOV); Value Objects `Pointing`/`FWHM`/`Target`
  (DDD tático). Trocar rig sem editar código.
- **Construir.** Testes: carrega perfil, valida, Value Objects imutáveis e com unidades.

### ✅ T6 — Persistência de sessão + telemetria  *(feito — docs/17)*
- Salvar subs FITS (opcional), metadados de sessão, e **resume**. Log estruturado.
- **Reusar** astropy. Testes: grava/relê sessão; resume continua de onde parou.

### ☐ T7 — CI (GitHub Actions)
- `git init` + primeiro commit; workflow rodando `pytest -m "not hardware"` + build/ctest do C++.
- Testes: o próprio CI (verde no push).

---

## Milestone C — Fase 4 (superação: rastreamento IA)

### ✅ T8 — Fluxo óptico (base do tracking)  *(feito — docs/18)*
- Protótipo de rastreamento por **fluxo óptico** (cupyx/VPI) em sim; medir FPS.
- **Construir** `control/tracking.py` (modo fluxo óptico). Testes: rastreia um alvo em movimento sintético.

### ✅ T9 — YOLOv8 → TensorRT (detector)  *(feito — docs/18: com fallback CV)*
- Exportar engine YOLOv8-n para TensorRT; wrapper de inferência com **fallback** (ONNX/CPU) quando
  sem TensorRT (no PC de dev). **Reusar** ultralytics/TensorRT.
- Testes: wrapper carrega e infere num frame (mock/ONNX) sem quebrar sem TensorRT.

### ✅ T10 — Laço de tracking em tempo real (feed-forward)  *(feito — docs/18)*
- detecção → predição de velocidade → **correção feed-forward** ao mount (SimMount). Novo estado `TRACKING`.
- **Construir.** Testes: o alvo em movimento é mantido centralizado ao longo dos frames.

### ✅ T11 — Modo satélite/ISS (demo Fase 4)  *(feito — docs/18, erro ~1 px)*
- Alvo rápido no `SkyModel` (trajetória) + o laço T10 rastreando-o. Entrada `run_tracking.py` + live view.
- Testes: erro de rastreio permanece pequeno enquanto o alvo cruza o campo.

### ✅ T12 — Modo autônomo noturno (integração final)  *(feito — docs/19)*
- Amarra tudo: agendador → (calibração) → mosaico/stack → denoise → FITS, sem operador. Fecha a Fase 3+.
- Feito: `core/autonomous.py` (`AutonomousNight` + `Observation`), `run_night.py`, e o **painel de
  controle** (`core/controller.py` + `run_app.py`) que roda TODOS os modos pelo navegador com Parar.
  Testes: "noite" sintética produz saídas de vários alvos; painel inicia/troca/para cada modo. **108 verdes.**

---

---

## Milestone D — Fechar a stack de software ANTES da câmera (tudo no PC de dev, sem HW novo)
Objetivo: validar 100% do software com ferramentas grátis + simuladores + dados reais, para só
gastar dinheiro na câmera depois que o risco de software estiver zerado. Ver docs/20 (checklist).

### ☐ T13 — Validar a camada INDI contra os *simuladores* do INDI (sem hardware)
- Escrever/testar `IndiCameraSource`/`IndiMount`/`IndiFocuser`/`IndiFilterWheel` contra
  `indi_simulator_ccd/telescope/focuser/filter` (grátis, vêm com o INDI). Exercita a fronteira de HW inteira.
- Testes: adapters conectam, leem propriedades e disparam ações contra o INDI simulado.

### ✅ T14 — Plate solving REAL com ASTAP (grátis)  *(feito — docs/21)*
- `control/solver.py`: `AstapSolver` (salva FITS → chama ASTAP → parseia o `.ini` → `WcsInfo`) +
  `parse_astap_result` (parser puro). `astap_bin` aceita argv-prefixo → testável com **ASTAP falso**.
- Testes: parser (resolvido/não/matriz-CD), e2e com `tests/fake_astap.py`, hint roundtrip, binário ausente.
  Integração real em `test_solver_integration.py` (marker `hardware`, pulado). Substitui o solver-hash sim.

### ✅ T15 — Validar o pipeline com DADOS REAIS  *(feito — docs/21)*
- Campo estelar REAL (CCD de M67, `tests/data/real_starfield_m67.fits`; `scripts/fetch_real_data.py`).
- Detecção (60 estrelas), FWHM real (~10px), registro (corr **0,215→0,995**), empilhamento (**√16=4,0×**).
  Testes: `test_real_pipeline.py` (5, offline). Pega o que o céu sintético esconde (PSF/ruído/fundo reais).

### ✅ T16 — Auto-find celeste em malha fechada (RA/DEC)  *(feito — docs/22)*
- `control/autofind_radec.py` `close_loop_goto`: slew→solve→sync em RA/DEC até centralizar (~2 iters).
  Dublês `SimRaDecMount`/`SimRaDecSolver`; `IndiMount` ganhou `goto/sync/position` (graus↔horas INDI).
- Modo **GOTO (RA/DEC)** no painel (`run_app.py`). Validado: M42 **19,4→0,36 arcmin**. Amarra T13+T14.
  Testes: `test_autofind_radec.py` (6) + controller goto. Ponte pixel↔RA/DEC do céu real fica no Milestone F.

### ✅ T17 — Estúdio de produto + primeira imagem real bonita  *(feito — docs/24)*
- `scripts/process_real_dataset.py` (dataset Siril M8/M20 real → imagem colorida), `postproc/render.py`
  (motor com dezenas de controles + presets), `src/server/studio.py` + `run_studio.py` (escolher alvo,
  ver 13MP real, ajustar ao vivo, baixar alta-res). Testes: render + studio (10). **153 verdes.**

---

## Milestone D+ — Qualidade de imagem "melhor que a DWARF" (pesquisa docs/23)

### ◑ T18 — Cor correta  *(parcial — docs/24)*
- **FEITO:** consertado o **debayer** (convenção Bayer do OpenCV deslocada: RGGB→`BayerGR2RGB`) que gerava
  artefato azul, e adicionado **SCNR** (remove o green cast do OSC) ao motor de render → emissão em rosa/Hα.
  Fundo neutro por percentil. Testes: SCNR reduz o verde. Controles SCNR + R/G/B no estúdio.
- **FALTA (futuro):** **PCC com catálogo** (Gaia via cedar-solve) para cor fotométrica precisa e vibrante.

### ◑ T19 — Deconvolução + denoise  *(parcial — docs/25)*
- **FEITO:** `postproc/deconv.py` — deconvolução **Richardson-Lucy** na luminância (recupera detalhe;
  FOSS/scipy) + denoise de luminância (bilateral). Integrados ao motor de render + estúdio (sliders
  Deconvolução / Denoise croma / Denoise luminância). Preset **H-alpha**. Testes: 5.
- **FALTA (Jetson):** denoise IA **GraXpert** (ONNX→TensorRT) e deconv/super-res IA **cuCIM/Cosmic Clarity**
  (→TensorRT) — o salto de qualidade final. Wrapper GraXpert já existe (fallback sem a ferramenta).

### ☐ T20 — Lucky imaging agressivo + drizzle (diferencial de GPU)
- Rejeição por-frame na GPU (FWHM/Laplaciana) guardando top-X% + **super-resolução drizzle** com dithering.
- **Construir** (nosso diferencial). Testes: FWHM do stack melhora com rejeição; drizzle 2× dá +detalhe.

### ✅ T22 — Catálogo do céu real + filtro pela óptica  *(feito — docs/26)*
- `src/core/catalog.py` (OpenNGC/pyongc): ~14k objetos reais; `find()` (RA/DEC p/ o GOTO), `Rig` (FOV +
  mag limite), `framable()` (1868 capturáveis c/ nossa óptica), `visible()` (altitude no horizonte).
  `run_catalog.py` ("o que fotografar hoje"). GOTO usa `catalog.find` (aponta em QUALQUER alvo). Testes: 6.

### ✅ T21 — Mais alvos reais no Estúdio  *(feito)*
- Baixados e processados **M51 (galáxia) + NGC2244 (Roseta)** do MILAN Survey. Estúdio agora tem 3 alvos
  reais (2 nebulosas + 1 galáxia). Script ganhou `--mono` e **remoção de hot pixels** (`gpu/calibration.
  remove_hot_pixels`, testada) — sem darks, hot pixels viravam "walking noise". Ver docs/27.

### ✅ T7 — CI + git  *(feito)*
- `git init` + commit inicial (branch main, 148 arquivos). `.github/workflows/ci.yml`: pytest `-m "not
  hardware"` + CTest C++. `.gitignore` (exclui dados grandes/stacks), `requirements.txt` completo.
- **Falta só** (quando o usuário quiser): criar o remoto GitHub e `git push` → o CI roda no push.

---

## ✅ Milestone E — Bring-up na Orin  *(feito — docs/28)*
- Software portado e rodando na Orin Nano Super 8GB (JetPack 6.2/CUDA 12.6/TensorRT 10.3): **164 testes
  verdes**, backend **CuPy/GPU (Orin)**, painel + Estúdio acessíveis pelo celular, **INDI real 4/4**
  (achou+corrigiu 2 bugs: timing do foco, UPLOAD_MODE da câmera). Benchmark: 4K stack **4,3×** GPU, ~30 FPS.
- 8GB deu conta da stack. **Falta (otimização):** OpenCV-CUDA (compilação de horas), engine TensorRT do YOLO.

## Milestone F — Bring-up de hardware (precisa das peças físicas)
- Captura **MIPI CSI zero-copy** (Argus/NVMM) ou USB3/INDI do IMX585; foco/solve/tracking no céu real.
