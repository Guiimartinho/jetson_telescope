# 33 — Console de campo (UI de produto: Live / Atlas / Pro)

A interface que o usuário usa **no campo, pelo celular, sem internet** — inspirada na **DWARF**
(polish de consumidor) + **ASIAIR Pro** (dados de astrofotógrafo). Uma **webpage** servida pela própria
Orin (nada de app). Módulo: `src/server/console.py` + `run_console.py` (porta 8080). Ver docs/31 (rede).

## As 3 abas

- **Atlas** — escolher alvo. Usa o **catálogo real** (`core/catalog`, pyongc) + a óptica (`DEFAULT_RIG`)
  p/ calcular **altitude/visibilidade AGORA** (local padrão São Paulo). Filtros (Visível agora / Nebulosa /
  Galáxia / Aglomerado), busca, miniaturas reais dos alvos que já processamos (M8/M20, Roseta, M51) e
  ícone p/ os demais. Tocar num alvo → GOTO (`start:goto:<desig>` no Controller).
- **Live** — view grande (imagem real do alvo, ou o stack ao vivo) + telemetria sobreposta (SNR, FWHM,
  subs, integração) puxada do `FrameHub`. Botão de captura empilha (`start:stack`) / para.
- **Pro** — curva V de autofoco, gráfico de guiding RA/DEC (ambos marcados **SIM** até ter hardware) e
  **histograma real** da imagem atual + status do plate-solve.

## Como conversa com o backend

Reusa o **mesmo `Controller`/`FrameHub` do painel** (docs/19). Endpoints (stdlib http.server):

| Rota | O quê |
|---|---|
| `GET /` | a SPA |
| `GET /api/targets` | catálogo + visibilidade agora (JSON) |
| `GET /api/state` | telemetria (polling ~0,9 s) |
| `GET /stream.mjpg` | live view (JPEG-push / MJPEG) |
| `GET /image/<key>` · `/thumb/<key>` | render real de um alvo (cacheado) |
| `GET /api/histogram[?key=]` | histograma do render ou do frame ao vivo |
| `GET /api/cmd/<ação>` | `start:<modo>[:<alvo>]` / `stop` → `Controller.submit` |

**Streaming:** JPEG-push (MJPEG) + polling JSON — no Orin os JPEGs podem sair no **encoder de HW (NVJPEG)**
(o Nano tem JPEG por HW, não tem NVENC de vídeo — ver docs/31/benchmark). Controle/telemetria por HTTP.

## Persistência e rede

Roda como **serviço systemd** (`telescope-console`, porta 8080) → sobe no boot, reinicia sozinho. Fica
**ao lado** do painel (8000) e do estúdio (8010). No campo a Orin vira hotspot WiFi e o celular abre
`http://<orin>:8080`; em bancada, mesma coisa pela rede atual (**não precisa mexer no WiFi p/ desenvolver**).

## Rodar / testar

```bash
py -3.11 run_console.py            # http://localhost:8080
py -3.11 -m pytest tests/test_console.py
```

Testes (5, offline): estrutura do Atlas, histograma normalizado, render real de imagem, fallbacks. O
catálogo cai numa lista estática se pyongc faltar (não quebra). É **conceito funcional** — foco/guiding são
simulados até a montagem/câmera reais; o resto (catálogo, imagens, telemetria de stack, comandos) é real.
