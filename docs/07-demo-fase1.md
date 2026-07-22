# 07 — Fase 1 completa (Live Stacking + live view)

Implementa o **inner loop de GPU** (o nosso diferencial) no formato de reuso de
[`docs/08-reusar-vs-construir.md`](08-reusar-vs-construir.md). Roda **sem câmera** (simulador)
e, na Jetson, com câmera real via INDI — **o mesmo código**.

## Pipeline

```
fonte (simulador OU câmera INDI)
  → [debayer, se colorida]        gpu/debayer.py
  → calibração (master dark)      gpu/calibration.py
  → portão de qualidade (FWHM + Var. Laplaciana)   gpu/quality.py      [CONSTRUÍDO]
  → registro (astroalign / reuso, fallback cv2)    gpu/registration.py [REUSO]
  → stacker CUDA float32 ponderado na VRAM         gpu/stacker.py      [CONSTRUÍDO]
  → live view MJPEG no navegador                   server/webview.py
```

Orquestração (máquina de estados da sessão): `core/orchestrator.py`. Entrada: `run_fase1.py`.

## Como rodar

**PC de desenvolvimento (Windows/Linux, CPU) — com live view:**
```bash
pip install -r requirements.txt
python run_fase1.py                       # abre http://localhost:8000 no navegador
```

**Validação headless rápida (sem web):**
```bash
python run_fase1.py --frames 60 --no-web --width 800 --height 600
```

**Jetson Orin Nano Super (GPU) — simulador em 4K:**
```bash
pip install cupy-cuda12x                  # + OpenCV compilado com CUDA (docs/05)
python run_fase1.py --width 3840 --height 2160
```

**Jetson — câmera real via INDI:**
```bash
indiserver -v indi_asi_ccd &              # driver da ASI585MC
pip install pyindi-client astropy
python run_fase1.py --source indi --width 3840 --height 2160
```

Opções: `--source {sim,indi}` · `--frames N` (0 = live até Ctrl+C) · `--stars`, `--bad-frac`
(simulador) · `--no-web` · `--port` · `--out` · `--save-every`.

## O que observar
- **Live view** em `http://localhost:8000`: imagem empilhada ao vivo + painel (empilhados,
  rejeitados, FWHM, ganho de SNR). Abre em qualquer navegador da rede (`http://IP-da-jetson:8000`).
- **Rejeição funcionando:** frames borrados (FWHM alto) e nublados (poucas estrelas) descartados.
- **SNR sobe ~raiz(N):** comparar `output/single_frame.png` × `output/stack_final.png`.

## Validação (PC de dev, 2026-07)
- 50/60 frames aceitos, 10 rejeitados (17%): blur ~FWHM 8,3–8,6 e nuvem (n≈0) corretamente descartados.
- **Ganho de SNR ~9,9×** em 50 frames. `add()` ~3 ms/frame na CPU (muito mais rápido na GPU).
- Live view MJPEG servido e respondendo (`/`, `/stats`, `/stream.mjpg`).

## Detecção automática de backend/reuso (mesmo código, dois ambientes)
| Recurso | Presente | Ausente |
|---|---|---|
| CuPy | GPU (VRAM) | NumPy/CPU |
| astroalign | registro por triângulos (reuso) | fallback cv2 (NN + afim) |
| pyindi-client | câmera real | simulador |

## Pendências / próximos passos (Fase 1.1 → 2)
- Migrar warp e Laplaciano para `cv2.cuda` (GPU) — hoje o warp roda em cv2/CPU.
- `indi_source.py` é escafold: validar nomes de propriedades no bring-up da câmera.
- Master dark real (hoje calibração é no-op sem dark).
- **Fase 2:** plugar GOTO/plate-solve (cedar-solve/ASTAP) + montagem (INDI) *antes* do laço,
  sem tocar no núcleo. Ver [`docs/04-roadmap.md`](04-roadmap.md).
