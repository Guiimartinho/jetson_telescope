#!/usr/bin/env python3
"""Console de campo — a UI de produto (Live/Atlas/Pro), estilo DWARF + ASIAIR.

    py -3.11 run_console.py            # abre em http://localhost:8080
    py -3.11 run_console.py --api      # + a API do app do celular em https://<ip>:8443

Roda ao lado do painel (8000) e do estúdio (8010). Usa o mesmo Controller/FrameHub, o catálogo
real (Atlas) e o render (imagens). Servido pela própria Orin — no campo, via WiFi, sem internet.
Ver docs/33.

Com `--api` sobe também a API protegida que o app consome (TLS 1.3, pareamento por QR, token),
no MESMO processo — ela comanda o mesmo Controller. E o console vira só leitura: comando por
HTTP aberto, ao lado de uma API protegida, seria a porta dos fundos (app/docs/07-seguranca.md).
Na bancada, `--open-commands` mantém os botões do console.

O serviço da Jetson liga a API por variável de ambiente (como faz com a montagem): `TELE_API=1`,
`TELE_API_PORT` (8443) e `TELE_OPEN_COMMANDS=1`. Ver deploy/jetson/telescope-console.api.conf.

Só no PC de desenvolvimento, para as telas do app terem com o que falar: `TELE_NETWORK=sim` e
`TELE_UPDATES=sim` ligam os adapters de MENTIRA da rede e da atualização (sem elas a API responde
"ainda não habilitado", que é o caso da Jetson), e `--advertise` anuncia a API na rede.
"""
from __future__ import annotations
import argparse
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from src.control.mount_link import mount_link_from_env
from src.core.config import SessionConfig
from src.core.controller import Controller
from src.server.webview import FrameHub
from src.server.console import ConsoleServer


def _env_on(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "on", "sim")


def main():
    ap = argparse.ArgumentParser(description="Console de campo do telescopio (Live/Atlas/Pro)")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = acessivel na rede (celular)")
    ap.add_argument("--also-port", type=int, action="append", default=[], metavar="PORTA",
                    help="serve tambem nesta porta (na Jetson: 80, para abrir so com o nome)")
    ap.add_argument("--ws-port", type=int, default=None, metavar="PORTA",
                    help="porta do canal em tempo real (padrao: --port + 1; 0 desliga)")
    ap.add_argument("--api", action="store_true", default=_env_on("TELE_API"),
                    help="liga a API do app (HTTPS/WSS, TLS 1.3, pareamento por QR)")
    ap.add_argument("--api-port", type=int, default=int(os.environ.get("TELE_API_PORT", "8443")),
                    metavar="PORTA")
    ap.add_argument("--open-commands", action="store_true", default=_env_on("TELE_OPEN_COMMANDS"),
                    help="com --api: mantem os comandos abertos do console (so na bancada)")
    ap.add_argument("--advertise", action="store_true", default=_env_on("TELE_ADVERTISE"),
                    help="com --api: anuncia a API na rede (para o app achar sem endereco). So "
                         "no PC: na Jetson quem anuncia e o avahi")
    a = ap.parse_args()
    ws_port = a.port + 1 if a.ws_port is None else (a.ws_port or None)

    if a.api:                                   # falha clara ANTES de subir qualquer coisa
        try:
            from src.api.server import ApiServer, build_context
        except ImportError as e:
            sys.exit(f"--api precisa de fastapi, uvicorn e cryptography ({e}). "
                     "Instale: pip install fastapi uvicorn cryptography segno")

    cfg = SessionConfig(web=True, enhance=True)
    hub = FrameHub()
    ctrl = Controller(cfg, hub=hub)
    ctrl.start()
    # Montagem real: TELE_MOUNT=indi (definido no serviço da Jetson) liga o link automático,
    # que conecta, envia hora/local e reconecta sozinho. Sem a variável, segue no simulador.
    link = mount_link_from_env()
    if link:
        link.start()
        print(">> montagem real: link automatico ligado (INDI)")
    open_commands = a.open_commands or not a.api
    srv = ConsoleServer(hub, host=a.host, port=a.port, on_command=ctrl.submit, mount_link=link,
                        ws_port=ws_port, extra_ports=a.also_port, allow_commands=open_commands)
    srv.start()
    print(f">> Console de campo: http://localhost:{a.port}  (Live / Atlas / Pro)"
          + ("" if open_commands else "  [so leitura: comandos pelo app]"))
    print(f">> portas extras: {srv.extra_ports or 'nenhuma'} | tempo real (WebSocket): "
          f"{srv.ws_port or 'desligado'}")
    api = advert = None
    if a.api:
        ctx = build_context(hub, ctrl.submit, mount_link=link, console=srv.console)
        ctrl.plan_provider = ctx.plan_queue     # o plano da noite, montado pelo app
        ctrl.latitude_provider = lambda: ctx.site.lat   # o alinhamento polar precisa do lugar
        api = ApiServer(ctx, host=a.host, port=a.api_port).start()
        print(f">> API do app: https://localhost:{api.port}/api/v1  (aparelho {ctx.identity.device_id}, "
              f"TLS 1.3, {len(ctx.pairing.clients())} celular(es) pareado(s))")
        print(">> para parear um celular: py -3.11 -m src.api.cli pair")
        if a.advertise:
            from src.api.server import Advertiser
            advert = Advertiser(ctx.identity.device_id, ctx.name, api.port)
            print(">> anunciando na rede: _telescope._tcp" if advert.start() else
                  ">> --advertise pede o pacote zeroconf (pip install zeroconf); seguindo sem anunciar")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n>> encerrando console")
        if advert:
            advert.stop()
        if api:
            api.stop()
        if link:
            link.stop()


if __name__ == "__main__":
    main()
