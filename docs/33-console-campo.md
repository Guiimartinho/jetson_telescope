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
| `GET /api/state` | telemetria (a página só consulta se o WebSocket não estiver aberto) |
| `ws://<host>:8081` | canal em tempo real: estado empurrado + comandos |
| `GET /manifest.webmanifest` · `/icon-*.png` · `/icon.svg` | manifesto e ícones do app |
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

## O console como app (2026-10-09)

> **Depois disto veio o app de verdade** (`app/`, Flutter, com a API protegida em `src/api`). O
> console continua existindo como reserva — abre em qualquer navegador, sem instalar nada. Com
> a API ligada (`run_console.py --api`) ele vira **só leitura**: comando por HTTP aberto ao lado
> de uma API protegida seria a porta dos fundos (`app/docs/07-seguranca.md`).

Esta página, servida pela Jetson, pode ser aberta no navegador do celular e posta na tela
inicial, sem loja de aplicativos. O celular fala só com a Jetson; a Jetson fala com a placa da
montagem pelo cabo USB (`docs/35`). Três coisas fazem a página se comportar como app:

| O quê | Como | Onde |
|---|---|---|
| Endereço sem IP nem porta | apelido mDNS **`telescopio.local`** + console também na porta 80 | `deploy/jetson/telescope_mdns_alias.py`, `telescope-console.app.conf` |
| Ícone na tela inicial | manifesto de app web + ícones PNG do logo | `ui_kit.manifest()`, `ui_kit.app_icon_png()` |
| Estado em tempo real | WebSocket: a Jetson **empurra** o estado; a página deixa de perguntar | `ConsoleServer._ws_handler` (porta 8081) |

Instalação na Jetson: `sudo bash scripts/jetson_setup_app.sh` (idempotente).

**Apelido na rede.** A Jetson continua se chamando `jetson-super`; um serviço pequeno
(`telescope-mdns`) pede ao avahi que anuncie também `telescopio.local`. O apelido sai como
registros de endereço (A), um por interface, e o serviço republica quando o IP muda (DHCP
novo, hotspot do campo). A primeira versão usava um CNAME, que seguiria o nome da máquina
sozinho — foi testada e descartada: o resolvedor mDNS do Windows ignora CNAME. Só entram as
redes de verdade: o avahi anuncia o nome da máquina também na ponte do docker (`172.17.0.1`),
e um celular que recebesse esse endereço não chegaria a lugar nenhum.

**Ícone.** É o logo do `ui_kit` (retículo + órbita), na cor de destaque sobre o fundo do app.
O PNG é desenhado a partir da mesma geometria do SVG do cabeçalho, sem depender de um
renderizador de SVG, e fica dentro do círculo central de 80%: o Android recorta ícones
"maskable" e não pode comer o símbolo.

**Tempo real.** O `FrameHub` ganhou `wait_change()`: cada conexão WebSocket acorda no
instante em que o estado muda e envia o JSON completo, limitado a ~10 mensagens por segundo.
Comandos também entram por ele (`{"cmd": "start:stack"}`), na mesma fila do `/api/cmd`. A
página aprende a porta em `/api/state` (`ws_port`); se o canal cair, ou se a lib `websockets`
faltar, ela volta a consultar a cada 0,9 s e tenta reabrir. A imagem ao vivo continua em
MJPEG.

Verificado na Orin, a partir de um PC na mesma rede: `http://telescopio.local` abre a página
(sem IP, sem porta); num Chrome de verdade (headless) o cabeçalho chega a "GPU", "montagem
conectada" e canal "tempo real"; e o WebSocket entrega atualizações sem ser consultado.

**Limite conhecido — Android e HTTPS.** No iPhone, "Adicionar à Tela de Início" abre a
página em tela cheia mesmo por HTTP. No Android, o Chrome só instala como app em tela cheia
se a página vier por HTTPS; por HTTP ele cria um atalho com o nosso ícone que abre no
navegador, com a barra de endereço. HTTPS numa rede local sem internet exige um certificado
em que o celular confie — fica como decisão futura. Não foi testado em celular.

## Rodar / testar

```bash
py -3.11 run_console.py            # http://localhost:8080  (+ WebSocket na 8081)
py -3.11 run_console.py --api      # + a API do app em https://<ip>:8443 (o console fica só leitura)
py -3.11 -m pytest tests/test_console.py tests/test_console_app.py tests/test_mdns_alias.py
```

Só no PC de desenvolvimento: `--advertise` anuncia a API na rede (para o app achar sem endereço)
e `TELE_NETWORK=sim` / `TELE_UPDATES=sim` ligam os adapters de mentira da rede e da atualização.
Detalhes em `app/README.md` e `app/docs/04-api.md` §10.

Testes (5, offline): estrutura do Atlas, histograma normalizado, render real de imagem, fallbacks. O
catálogo cai numa lista estática se pyongc faltar (não quebra).

## Design system (`ui_kit`) e "nada mockado"

A UI usa o **`src/server/ui_kit.py`** — tema coerente + **ícones SVG desenhados à mão (NUNCA emoji)** e a
logo (retículo + órbita). O mesmo kit será aplicado ao estúdio e ao painel. **Tudo funciona com dados/
imagens REAIS dos nossos modelos:** nebulosa/galáxia = stacks; **planeta = lucky imaging** (`/image/@jupiter`);
**Lua = foto real** realçada; **satélite = cena de rastreio** (rastro real); **autofoco = curva V real**
(roda o `AutoFocuser`, `/api/focus`); **guiding = fluxo óptico real** (`OpticalFlowTracker` sobre a cena de
satélite, resíduo após a deriva, `/api/guiding`); **histograma real**; telemetria+comandos via Controller.
Foco/guiding rodam os ALGORITMOS de verdade (sobre céu simulado, até a câmera/montagem físicas).
