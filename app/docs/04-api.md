# 04 — Contrato da API (v1)

O app nunca toca em arquivo, banco ou hardware: tudo passa por esta API. O contrato é escrito
antes do código dos dois lados, e o app é desenvolvido contra um **telescópio falso** que o
obedece — mesma ideia dos adapters `Sim*` do projeto.

## 1. Ponto de partida: o que existe hoje

Três servidores, cada um com o seu jeito. Funciona para as páginas atuais; para um app é
confuso (três portas, nomes diferentes para a mesma coisa).

| Servidor | Porta | Rotas |
|---|---|---|
| Painel | 8000 | `/stats`, `/cmd/<ação>`, `/stream.mjpg` |
| Estúdio | 8010 | `/targets`, `/render`, `/download` |
| Console | 80 e 8080 | `/api/state`, `/api/targets`, `/api/cmd/<ação>`, `/api/histogram`, `/api/focus`, `/api/guiding`, `/image/<alvo>`, `/thumb/<alvo>`, `/stream.mjpg`; WebSocket na 8081 |

Modos que o `Controller` aceita hoje (`start:<modo>[:<alvo>]`): `stack`, `autofind`, `goto`,
`realdata`, `scheduler`, `mosaic`, `tracking`, `night`; e `stop`.

## 2. Princípios da v1

- **Só por canal cifrado.** `https://` e `wss://` na porta 8443, com o certificado do aparelho
  fixado no app e o token do celular em toda chamada (`Authorization: Bearer …`). As únicas
  rotas sem token são `/info` e as de pareamento. Ver [`07-seguranca.md`](07-seguranca.md).
- **Uma porta, um prefixo:** tudo em `/api/v1/…`. As páginas antigas continuam nas portas
  atuais enquanto forem úteis, mas perdem os comandos quando a API protegida entrar.
- **Versão no caminho.** Mudança incompatível vira `/api/v2`; a v1 segue no ar por um tempo.
- **Capacidades declaradas.** `/info` diz o que este telescópio tem (montagem real? foco?
  roda de filtros?) e o app mostra só o que existe. O mesmo app serve o simulador e o
  aparelho completo.
- **Comando devolve um trabalho.** Ações longas (goto, foco, empilhar) respondem na hora com
  um `job`; o progresso chega pelo WebSocket.
- **Unidades explícitas** no nome do campo: `ra_deg`, `exposure_s`, `fwhm_px`. Hora sempre em
  UTC, formato ISO 8601.
- **Erros com código**, não só texto: `{"error": {"code": "mount_disconnected", "message": "…"}}`.
  O app traduz o código; a mensagem é para o log.

## 3. Rotas

Estado: **existe** (só muda de endereço), **parcial** (a função existe no código, falta a
rota) ou **novo**.

### Aparelho e sessão do app

| Rota | O quê | Estado |
|---|---|---|
| `GET /api/v1/info` | identificador, nome, versões, `api: 1`, capacidades, hora da Jetson, se precisa de hora/local. Sem token | novo |
| `POST /api/v1/pair/start` | abre o pareamento: devolve um número aleatório. Sem token | novo |
| `POST /api/v1/pair/finish` | recebe a prova (HMAC) e devolve o token do celular. Sem token | novo |
| `GET /api/v1/clients` · `DELETE /clients/{id}` | celulares pareados; revogar | novo |
| `POST /api/v1/clients/invite` | um dono gera um QR de uso único para outro celular | novo (depois) |
| `POST /api/v1/site` | hora UTC + latitude/longitude/altitude vindas do celular | novo |
| `POST /api/v1/control` · `DELETE` | pedir e devolver a vez de comandar | novo (depois) |
| `GET /api/v1/state` | retrato completo do estado | existe (`/api/state`) |
| `WS /api/v1/ws` | eventos empurrados + comandos | existe (porta 8081) |

### Céu e alvos

| Rota | O quê | Estado |
|---|---|---|
| `GET /api/v1/targets?q=&type=&visible=&fits=&limit=` | busca no catálogo, com altitude agora | existe (`/api/targets`), falta filtro e paginação |
| `GET /api/v1/targets/{id}` | detalhe: curva de altitude na noite, nascer/pôr, tamanho contra o nosso campo | parcial (`core/catalog`) |
| `GET /api/v1/targets/{id}/thumb` | miniatura do alvo | existe (`/thumb/<alvo>`) |

### Observar

| Rota | O quê | Estado |
|---|---|---|
| `POST /api/v1/observe/goto` | `{target}` ou `{ra_deg, dec_deg}`: aponta e centraliza por plate solve | existe (`start:goto`), hoje simulado |
| `POST /api/v1/observe/focus` | autofoco | parcial (`control/autofocus`) |
| `POST /api/v1/observe/stack` | começa a empilhar: `{exposure_s, gain, filter, frames}` | existe (`start:stack`), sem parâmetros |
| `POST /api/v1/observe/stop` | para o que estiver rodando | existe (`stop`) |
| `GET /api/v1/preview.mjpg` | imagem ao vivo | existe (`/stream.mjpg`) |
| `GET /api/v1/frame.jpg` | o último quadro, uma vez | novo |
| `GET /api/v1/histogram` | histograma do quadro atual | existe |

### Planejar

| Rota | O quê | Estado |
|---|---|---|
| `GET` · `PUT /api/v1/plan` | a fila de alvos da noite, com prioridade, janela e orçamento | parcial (`core/scheduler`) |
| `POST /api/v1/plan/start` · `/stop` | noite autônoma | existe (`start:night`, `start:scheduler`) |
| `POST /api/v1/mosaic` | grade de painéis sobre um alvo | existe (`start:mosaic`), sem parâmetros |

### Galeria e estúdio

| Rota | O quê | Estado |
|---|---|---|
| `GET /api/v1/sessions` | sessões gravadas: alvo, data, integração, miniatura | parcial (`core/session_store`) |
| `GET /api/v1/sessions/{id}` | detalhes e métricas (subs, FWHM, SNR ao longo da sessão) | parcial |
| `GET /api/v1/sessions/{id}/image?format=jpg\|tif\|fits` | baixar o resultado | existe (`/download`), só JPEG |
| `POST /api/v1/sessions/{id}/render` | prévia com os controles do estúdio | existe (`/render`) |
| `GET /api/v1/render/presets` | presets e limites de cada controle | parcial (`postproc/render`) |
| `DELETE /api/v1/sessions/{id}` | apagar | novo |

### Equipamento

| Rota | O quê | Estado |
|---|---|---|
| `GET /api/v1/mount` | conectada, posição, rastreio, estacionada | existe (dentro de `/api/state`) |
| `POST /api/v1/mount/slew` · `/stop` | mover à mão: direção e velocidade | novo |
| `POST /api/v1/mount/park` · `/unpark` · `/home` · `/tracking` | estados da montagem | novo |
| `GET` · `POST /api/v1/focuser` | posição; mover N passos | parcial (`IndiFocuser`) |
| `GET /api/v1/drivers` | saúde dos drivers dos motores | parcial (`:GXU` no firmware) |

### Sistema

| Rota | O quê | Estado |
|---|---|---|
| `GET /api/v1/system` | temperatura, disco, versões, tempo ligado | novo |
| `POST /api/v1/system/shutdown` · `/restart` | desligar com segurança | novo |
| `GET` · `POST /api/v1/network` | modo (casa/campo), rede conhecida, nome e senha do WiFi do telescópio | novo |
| `GET /api/v1/logs` | registro para suporte | novo |

## 4. WebSocket: mensagens

Da Jetson para o app, sempre com tipo e número de sequência:

```json
{"seq": 4812, "type": "state",    "data": {"state": "STACKING", "backend": "CuPy/GPU (Orin)"}}
{"seq": 4813, "type": "progress", "data": {"job": "j-91", "phase": "solving", "pct": 40}}
{"seq": 4814, "type": "stack",    "data": {"accepted": 42, "rejected": 3, "snr": 18.4, "fwhm_px": 2.9}}
{"seq": 4815, "type": "mount",    "data": {"connected": true, "ra_deg": 83.82, "dec_deg": -5.39}}
{"seq": 4816, "type": "error",    "data": {"code": "solve_failed", "job": "j-91"}}
```

Do app para a Jetson:

```json
{"id": "c-17", "cmd": "observe.stop"}
{"id": "c-18", "cmd": "mount.slew", "args": {"dir": "N", "rate": 3}}
```

Hoje o canal manda o estado inteiro a cada mudança e aceita `{"cmd": "start:stack"}`. A v1
separa por tipo para o app não redesenhar tudo a cada mensagem.

## 5. Capacidades (`/info`)

```json
{
  "id": "tele-0b04", "name": "Telescópio", "api": 1, "software": "0.9.0",
  "capabilities": {
    "mount": "indi", "camera": "sim", "focuser": "sim", "filter_wheel": false,
    "modes": ["stack", "goto", "scheduler", "mosaic", "tracking", "night", "planetary"],
    "gpu": "CuPy/GPU (Orin)"
  },
  "clock": {"utc": "2026-10-09T20:47:18Z", "synced": true},
  "site": {"lat": -23.55, "lon": -46.63, "elev_m": 760, "source": "phone"}
}
```

`"camera": "sim"` é o caso de hoje: a montagem é real, a câmera ainda é o simulador. O app
mostra isso com clareza em vez de fingir.

## 6. Formatos das rotas do MVP

O bastante para começar a escrever os dois lados. Campos novos podem aparecer; os que estão
aqui não mudam de nome nem de unidade dentro da v1.

**Pareamento**

```json
POST /api/v1/pair/start    {"client_name": "Pixel do Guilherme"}
                        -> {"nonce": "b64…", "expires_s": 60}

POST /api/v1/pair/finish   {"client_name": "Pixel do Guilherme", "proof": "b64…"}
                        -> {"token": "b64…", "client_id": "c-3f2a", "role": "owner", "device_id": "tele-0b04"}
```

`proof = HMAC-SHA256(segredo_do_QR, nonce + impressão_digital + client_name)`.

**Hora e local**

```json
POST /api/v1/site   {"utc": "2026-10-09T20:47:18Z", "lat": -23.55, "lon": -46.63, "elev_m": 760, "accuracy_m": 12}
                 -> {"clock_set": true, "clock_offset_s": -0.6, "mount_updated": true}
```

**Estado** (`GET /state`, e a primeira mensagem do WebSocket)

```json
{"seq": 4811, "state": "IDLE", "backend": "CuPy/GPU (Orin)",
 "job": null,
 "mount":  {"source": "indi", "connected": true, "ra_deg": 83.82, "dec_deg": -5.39, "tracking": false, "parked": false},
 "camera": {"source": "sim", "connected": true},
 "stack":  {"target": "", "accepted": 0, "rejected": 0, "snr": 0.0, "fwhm_px": 0.0, "integration_s": 0},
 "system": {"temp_c": 41.5, "disk_free_gb": 200.1}}
```

**Alvos**

```json
GET /api/v1/targets?visible=1&fits=1&limit=50
 -> {"total": 474, "items": [
      {"id": "M8", "name": "Lagoa", "type": "nebula", "ra_deg": 270.92, "dec_deg": -24.38,
       "catalog": "NGC6523", "mag": 5.8, "size_arcmin": 45.0, "alt_deg": 52.1, "fits": true, "has_thumb": true}]}

GET /api/v1/targets/M8
 -> {"id": "M8", "…": "…",
     "night": {"best_from": "2026-10-09T23:10:00Z", "best_to": "2026-10-10T02:40:00Z",
               "altitude": [{"utc": "2026-10-09T22:00:00Z", "alt_deg": 61.0}]},
     "framing": {"fov_deg": [2.57, 1.44], "fills": 0.58}}
```

**Comandos e trabalhos**

```json
POST /api/v1/observe/goto    {"id": "c-17", "target": "M8"}
POST /api/v1/observe/stack   {"id": "c-18", "exposure_s": 30, "gain": 120, "frames": 0}
POST /api/v1/observe/stop    {"id": "c-19"}
                          -> {"job": "j-91", "state": "accepted"}
```

O mesmo `id` reenviado devolve o mesmo `job`, sem executar de novo. `frames: 0` é "até eu parar".

Progresso pelo WebSocket:

```json
{"seq": 4813, "type": "progress", "data": {"job": "j-91", "kind": "goto",
  "steps": [{"name": "slew", "state": "done"}, {"name": "solve", "state": "running"},
            {"name": "center", "state": "pending"}, {"name": "focus", "state": "pending"}]}}
```

**Sessões e estúdio**

```json
GET /api/v1/sessions
 -> {"items": [{"id": "s-20261009-m8", "target": "M8", "started": "2026-10-09T23:12:00Z",
                "integration_s": 1260, "frames": 42, "has_fits": true}]}

POST /api/v1/sessions/s-20261009-m8/render
     {"preset": "vivido", "stretch": 13.0, "saturation": 2.3, "denoise": 0.45, "full": false}
 -> image/jpeg
```

**Erros** — sempre o mesmo formato, com o código HTTP correspondente:

```json
{"error": {"code": "mount_disconnected", "message": "a montagem parou de responder"}}
```

| Código HTTP | Quando |
|---|---|
| 400 | entrada inválida (`invalid_argument`) |
| 401 | sem token ou token revogado (`unauthorized`) |
| 403 | o papel não permite, ou a vez é de outro celular (`forbidden`, `not_controller`) |
| 409 | o telescópio está ocupado com outra coisa (`busy`) |
| 503 | falta uma peça (`mount_disconnected`, `camera_unavailable`) |

## 7. O telescópio falso

Para desenvolver o app sem a Jetson ligada:

- **O próprio software da Jetson roda no PC** com os simuladores (`py -3.11 run_console.py`).
  É o falso mais fiel: mesmo código, mesma API.
- **Um falso em Dart**, dentro do app, alimenta os testes de tela e o **modo demonstração**
  (o app funcionando sem telescópio nenhum, para quem está conhecendo o produto).

Os dois obedecem ao mesmo contrato; um teste de contrato roda contra ambos.

## 8. Como ficou na implementação (2026-10-09)

O contrato acima foi escrito antes do código. Construindo, algumas coisas ficaram mais precisas.
O que vale é o que está aqui e nos arquivos de `app/test/fixtures` (respostas reais da API,
regravadas por `scripts/export_api_fixtures.py`).

**Onde está:** `src/api/` — `identity.py` (chave, certificado, QR), `pairing.py` (janela, prova,
tokens), `jobs.py` (trabalhos), `audit.py`, `sky.py` (alvos), `app.py` (rotas), `server.py`
(liga às peças reais e serve por TLS), `cli.py` (comandos do dono). Sobe com
`py -3.11 run_console.py --api`, no mesmo processo do console: é o mesmo `Controller`.

**Rotas no ar**

| Rota | Observação |
|---|---|
| `GET /info` | sem token. `capabilities.goto` diz quem executa o apontamento (`sim` hoje, mesmo com a montagem real ligada); `pairing_open` diz se a janela está aberta |
| `POST /pair/start` · `/pair/finish` | sem token; corpo de no máximo 64 KiB |
| `GET /clients` · `DELETE /clients/{id}` | dono. Cada celular traz `current` (é este?) |
| `POST /site` | devolve `clock_set`, `clock_offset_s`, `mount_updated`. A Jetson guarda a DIFERENÇA para o relógio do sistema; não o acerta |
| `GET /state` · `/mount` · `/system` | `system.power` diz se desligar pelo app está habilitado |
| `POST /system/shutdown` · `/restart` | dono. Responde 501 `not_enabled` enquanto não for habilitado no aparelho |
| `GET /logs` | dono. Registro de auditoria: quem comandou o quê |
| `GET /openapi.json` | a descrição da API gerada pelo servidor; pede token |
| `GET /targets` | `q`, `type`, `visible`, `fits`, `limit` (até 200), `offset`. Com `q`, vem primeiro o que casa melhor; sem `q`, o mais alto |
| `GET /targets/{id}` · `/thumb` | o `id` é o número Messier quando existe (`M8`), senão o do catálogo (`NGC253`); `catalog` traz sempre o do catálogo |
| `POST /observe/target` | **novo.** A "noite rápida": aponta, centraliza e, se deu certo, empilha até alguém parar — um comando só, para a sequência seguir na Jetson se o celular perder o sinal |
| `POST /observe/goto` | por `target` ou por `ra_deg` + `dec_deg` |
| `POST /observe/stack` | devolve `ignored`: os parâmetros que ainda não são aplicados (câmera simulada) |
| `POST /observe/run` | qualquer modo do `Controller` (`mode`, `target`) |
| `POST /observe/stop` | sempre aceito |
| `GET /frame.jpg` · `/preview.mjpg` | `max_side` reduz o quadro para a tela do celular (o cheio passa de 1 MB) |
| `GET /histogram` | 40 faixas, de 0 a 1 |
| `GET /sessions` · `/sessions/{id}` · `/image` | hoje são os empilhamentos de referência (`source: reference`) |
| `POST /sessions/{id}/render` · `GET /render/presets` | controles conferidos por nome, tipo e faixa; `full: true` rende em resolução cheia |
| `WS /ws` | token no cabeçalho, ou `{"auth": "<token>"}` como primeira mensagem |

**Ainda não existem:** `/observe/focus`, `/clients/invite`, `/control`, `/plan`, `/mosaic`,
`/mount/slew` e companhia, `/focuser`, `/drivers`, `/network`, `DELETE /sessions/{id}`, e a
imagem em TIFF ou FITS.

**Trabalhos.** `{"job", "kind", "state", "target", "steps", "error"}`. Estados:
`accepted` → `running` → `done` | `failed` | `stopped`. `steps` lista as etapas já vistas, na
ordem (`slew`, `solve`, `focus`, `stack`, `schedule`, `track`), cada uma `running`, `done`,
`failed` ou `stopped`. `error`: `not_converged` ou `internal`. Um comando novo interrompe o
trabalho anterior (que termina `stopped`). O `Controller` publica de qual comando é o estado
(`job`) e como terminou (`outcome`); é por aí que a API sabe que acabou.

**Estado.** Além do que está no §6: `phase` (o texto de estado do `Controller`), `filter`,
`focus_pos`, `pointing` (`error`, `unit`), `queue` (`done`, `total`) e `mount.error`.
`mount.tracking` e `mount.parked` existem e vêm nulos (a API ainda não os lê da montagem).
`stack.integration_s` vem nulo com a câmera simulada: não há exposição de verdade para somar.

**Canal em tempo real.** Tipos enviados: `state` (o retrato inteiro: ao conectar e quando muda
o estado geral), e depois só a parte que mudou — `progress` (o trabalho), `stack`, `mount`,
`camera`, `pointing`, `queue`, `system`. Comandos pelo canal: só `observe.stop`, respondido com
`ack` (ou `error`). Token revogado: a Jetson fecha com o código 4401.

**Erros.** Além dos do §6: 413 `payload_too_large`, 429 `pairing_locked`, 501 `not_enabled` e
`not_supported`, 404 `not_found`.

## 9. Fases 3 e 4 (2026-10-10)

O que o §8 listava como "ainda não existem" entrou, com exceção de `/control` (a vez de
comandar) e `/drivers`. Os formatos de verdade estão em `app/test/fixtures`
(`state_night`, `focuser`, `camera`, `plan`, `mosaic`, `solar`, `invite`, `network`, `clients`).

| Rota | Observação |
|---|---|
| `POST /observe/preview` | a câmera ao vivo, sem apontar e sem empilhar. Estado `PREVIEW`; `stack.fwhm_px` traz a nitidez de cada quadro |
| `POST /observe/focus` | autofoco, como trabalho. A curva chega em `focus.curve`; sem estrelas termina `failed` com `focus_failed` |
| `POST /observe/body` | Lua, planeta ou Sol (`body`). O Sol exige `filter_confirmed` (`400 solar_filter_required`) |
| `GET /solar` | Lua, planetas e Sol com a altitude de agora; `phase` é a fração iluminada da Lua |
| `POST /mount/slew` | `{dir: N\|S\|E\|W, rate: 1..3, hold_ms: 100..2000}`. Tem **prazo**: sem renovar, a montagem para |
| `POST /mount/stop` · `/park` · `/unpark` · `/home` · `/tracking` | `stop` é sempre aceito. Estacionada: `409 parked`. Com trabalho rodando: `409 busy` |
| `GET` · `POST /focuser` | posição e limites; `{delta}` ou `{position}`. Devolve `at_limit` no fim de curso |
| `GET` · `POST /camera` | exposição, ganho, offset e os limites. Com a câmera simulada, `applied: false` |
| `GET` · `PUT /plan` | a fila da noite. Cada item volta com `start`, `end`, `duration_s` e `status` (`ok`, `never_up`, `after_dawn`, `sets_early`, `unknown`). `PUT` troca a fila inteira |
| `POST /plan/start` · `/skip` · `/stop` | a noite autônoma. O andamento chega em `night` (um registro por item) |
| `POST /mosaic` | só calcula: os painéis (RA/DEC), o quanto cobrem e se o alvo cabe. O mosaico entra no plano como `mosaic: [linhas, colunas]` |
| `POST /clients/invite` · `PATCH /clients/{id}` | convite de uso único com papel (`07-seguranca.md` §14); mudar papel |
| `PUT /device` | o nome do telescópio (dono). Fica guardado na pasta da identidade |
| `GET /network` | como o aparelho está na rede; `enabled: false` enquanto trocar pelo app não existe (ver §10) |
| `GET /sessions/{id}/export?format=jpg\|tif\|fits&max_side=` | JPEG tratado, TIFF de 16 bits linear, ou o FITS como está no disco (enviado em pedaços) |
| `DELETE /sessions/{id}` | dono. As imagens de referência respondem `409 protected` |

**Estado.** Além do que já havia: `focus` (`position`, `min`, `max`, `curve`, `best`), `night`
(o andamento do plano: `id`, `target`, `status`, `accepted`, `snr`, `reason`), `camera` com os
ajustes, e em `mount`: `tracking`, `parked`, `moving` e `features` — o que dá para fazer à mão
nesta montagem. Com a montagem real, `features` vem vazio: ela é lida, não comandada.

**Canal em tempo real.** Tipos novos: `focus` e `night` (este é uma lista). Mexer no foco manda
só `focus`, não o retrato inteiro.

**Erros novos.** 409 `busy`, `parked`, `not_running`, `protected`, `last_owner`.

**O que continua simulado.** Câmera, apontamento, focalizador e o movimento manual. A API diz
isso em `/info`, em `camera.applied` e em `mount.features`; o app repete na tela.

## 10. O que faltava para o app ficar completo (2026-10-10)

Os formatos de verdade estão em `app/test/fixtures` (`network_field`, `network_home`,
`network_scan`, `network_join`, `update_available`, `update_installing`, `state_capture`,
`job_planetary`).

| Rota | Observação |
|---|---|
| `POST /observe/planetary` | `{id, body, frames: 50..3000, keep_percent: 5..50, point}`. Lua e planetas (o Sol responde `404`). Trabalho `planetary`: aponta (se `point`), grava e empilha os mais nítidos. Etapa nova `capture`; o andamento chega em `capture` |
| `POST /observe/polar` | mede o erro do eixo polar em três campos. Trabalho `polar`; o resultado chega em `polar`. Falha: `polar_failed`. Com a montagem real: `501 not_supported` |
| `POST /mount/polar/adjust` | `{alt_arcmin, az_arcmin}`: os parafusos da montagem **simulada**. A medida anterior passa a `stale` |
| `GET /network` | `mode` (`home`, `field`), `wifi` (`ssid`, `signal`), `hotspot` (`ssid`, `active`, `address`, e `psk` **só para o dono**), `known`, `last_error`, `switching` |
| `GET /network/scan` | dono. As redes que o **telescópio** enxerga: `ssid`, `signal` (0 a 100), `secure`, `known` |
| `POST /network/join` | dono. `{ssid, psk}`; a senha é dispensada em rede aberta ou já guardada. Responde `{accepted, reconnect_s}` **antes** de trocar |
| `POST /network/mode` | dono. `{mode: home\|field}`. Para `home` usa a rede guardada mais forte ao alcance (`409 no_known_network` se não há) |
| `POST /network/hotspot` | dono. `{psk}` de 8 a 63 caracteres: a senha do WiFi próprio |
| `DELETE /network/known/{ssid}` | dono. `409 in_use` para a rede em que ele está |
| `GET /system/update` | `current`, `available` (`version`, `notes`) ou nulo, `state` (`idle`, `checking`, `downloading`, `installing`, `restarting`, `failed`), `progress`, `error` |
| `POST /system/update/check` · `/install` | dono. `409 busy` com outra em andamento ou com trabalho rodando; `409 nothing_to_install` |

**O contrato da troca de rede**, que qualquer adapter tem de cumprir porque o app depende dele
(conferido por `tests/test_api_phase4.py::test_network_adapter_contract`, onde o adapter de
verdade entra quando existir):

1. a resposta sai **antes** da troca, com `reconnect_s`: quanto esperar para procurar de novo;
2. um pedido aceito limpa o `last_error` anterior, e `switching` fica verdadeiro até a troca
   acabar;
3. se a rede nova não der certo (senha errada, sumiu), o aparelho **volta para onde estava** e
   conta o motivo em `last_error` (`wrong_password`, `not_found`). Ele nunca fica mudo.

**Guardas.** Durante a captura (`CAPTURING`) a montagem é do modo: `/mount/slew`, `/park` e
`/home` respondem `409 busy`. `/observe/run` não aceita `polar` nem `planetary` pelo nome: só as
rotas próprias, que conferem a montagem e o corpo. Reenviar `/observe/polar` com o mesmo `id`
devolve o mesmo trabalho. `/network/join` recusa senha fora de 8 a 63 caracteres e nome de rede
em branco ou com mais de 32 bytes. O número de quadros guardados na captura tem teto em memória
(256 MB): com quadros grandes, `kept` pode ficar abaixo do percentual pedido. A medida do
alinhamento polar termina com o aparelho em `STOPPED`, como o goto.

**Estado.** `capture` (`body`, `frames`, `total`, `kept`, `keep`, `done`) e `polar` (`step`,
`points`, `measured`, `alt_arcmin`, `az_arcmin`, `total_arcmin`, `aligned`, `stale`, `lat`). Os
dois vêm nulos quando não há o que dizer. Sinais do erro polar: `alt_arcmin` positivo é eixo alto
demais; `az_arcmin` positivo é eixo a leste do polo. `mount.features` ganhou `polar`. Estado novo
do aparelho: `CAPTURING`.

**Canal em tempo real.** Tipos novos: `capture` e `polar`. Os dois também chegam com `data`
nulo — o fim da captura é notícia.

**O que é de verdade e o que é de mentira.** A captura planetária usa o pipeline real de
`src/planetary` sobre quadros simulados; o alinhamento polar usa a geometria real sobre uma
montagem simulada. A rede e a atualização só têm adapters de mentira (`SimNetwork`,
`SimUpdater`), ligados por `TELE_NETWORK=sim` e `TELE_UPDATES=sim`: sem as variáveis — e é assim
na Jetson — `GET /network` e `GET /system/update` respondem `enabled: false` e as rotas que
mudam algo respondem `501 not_enabled`.

**Anúncio na rede.** Na Jetson o avahi anuncia `_telescope._tcp` com `id=<identificador>`
(`scripts/jetson_setup_api.sh`). No PC, `run_console.py --advertise` faz o mesmo com o pacote
`zeroconf`. O anúncio só poupa digitar endereço: a confiança continua vindo do certificado.
