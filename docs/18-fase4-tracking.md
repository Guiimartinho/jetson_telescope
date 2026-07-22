# 18 — Fase 4: Rastreamento IA em tempo real (T8–T11)

A "superação": rastrear objetos rápidos (satélites/ISS/meteoros) mantendo-os centralizados por
**correção feed-forward** — algo que os smart telescopes comerciais não fazem. Demonstrado em
simulação; na Jetson os mesmos módulos usam GPU/TensorRT.

## Componentes

### T8 — Fluxo óptico (`control/tracking.py`)
`OpticalFlowTracker` (Lucas-Kanade esparso, cv2): segue um ponto entre frames. Na Jetson: cv2.cuda /
VPI (OFA no AGX). Base do rastreamento.

### T9 — Detector (`control/detector.py`)
`Detector` (port) + `BrightObjectDetector` (CV, acha o objeto brilhante — roda em qualquer lugar) +
`YoloTensorRTDetector` (YOLOv8→**TensorRT** na Jetson, com **fallback** para o CV quando TensorRT/engine
ausentes — caso do PC de dev).

### T10 — Laço de rastreamento (`Session.track`)
Novo estado **`TRACKING`**. Por frame: **detecta** → reconstrói a posição do objeto → estima a
**velocidade** → `mount.nudge(erro + velocidade)` (**proporcional + feed-forward**) → mantém centralizado.
O feed-forward elimina o atraso de rastreio (trava em ~2 frames).

### T11 — Cena satélite/ISS (`capture/satellite.py`, `run_tracking.py`)
`SatelliteScene`: objeto brilhante em movimento sobre o campo estelar. `run_tracking.py` demonstra o
laço ao vivo (fase "rastreando" na UI).

## Como rodar
```bash
python run_tracking.py                 # satélite cruzando, rastreado ao vivo em :8000
python run_tracking.py --vx 6 --vy 3   # objeto mais rápido
```

## Validação (PC de dev, 2026-07, GPU)
- `tests/test_tracking.py`: detector acha o objeto (<3 px da verdade); YOLO cai no fallback sem TensorRT;
  fluxo óptico segue o objeto; **o laço mantém centralizado (< 10 px)**.
- Demo headless: **erro médio ~1,1 px** ao longo do trânsito. **100 testes verdes.**

## No hardware
`BrightObjectDetector` → `YoloTensorRTDetector` com engine real (exportar YOLOv8-n → TensorRT na Orin,
idealmente no **DLA** do Orin NX para liberar a GPU). O feed-forward vai à montagem real via INDI.
Alvo do spec: **>60 FPS** — a Orin NX entrega com folga.
