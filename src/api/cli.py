"""Comandos do dono do aparelho: parear um celular, ver quem está pareado, revogar.

    py -3.11 -m src.api.cli pair            # abre a janela e desenha o QR no terminal
    py -3.11 -m src.api.cli clients         # celulares pareados
    py -3.11 -m src.api.cli revoke c-3f2a   # tira um celular
    py -3.11 -m src.api.cli reset --yes     # reinício de fábrica do pareamento
    py -3.11 -m src.api.cli info            # identificador e impressão digital

Roda na própria Jetson (por SSH), com o serviço no ar: os dois conversam pela pasta da
identidade. O QR e o código longo contêm o SEGREDO de pareamento — por isso só aparecem aqui,
no terminal de quem já tem acesso ao aparelho, e nunca numa página da rede.
"""
from __future__ import annotations

import argparse
import socket
import sys
from datetime import datetime

from .identity import API_PORT, DeviceIdentity
from .pairing import PairingService


def lan_address() -> str | None:
    """O endereço desta máquina na rede local (o que o celular usa para chegar aqui). Não
    envia nada: só pergunta ao sistema por qual interface sairia."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
        return None if ip.startswith("127.") else ip
    except OSError:
        return None


def qr_text(data: str) -> str | None:
    """O QR desenhado com caracteres, ou None se a biblioteca `segno` não está instalada."""
    try:
        import io
        import segno
    except ImportError:
        return None
    out = io.StringIO()
    segno.make(data, error="m").terminal(out=out, compact=True, border=2)
    return out.getvalue()


def _when(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def cmd_pair(a, out) -> int:
    identity = DeviceIdentity.load_or_create(a.identity_dir)
    PairingService(identity).open_window(a.minutes * 60.0, shared=True)
    host = a.host or lan_address()
    uri = identity.pairing_uri(port=a.port, host=host, ssid=a.ssid, psk=a.psk)
    qr = qr_text(uri)
    print(f"Aparelho {identity.device_id}  |  janela de pareamento aberta por {a.minutes:g} min", file=out)
    print(f"Endereço no QR: {host or '(nenhum: o app procura na rede)'}:{a.port}", file=out)
    if qr:
        print("\nNo app: Conectar > Ler o QR do telescópio\n", file=out)
        print(qr, file=out)
    else:
        print("\n(sem a biblioteca segno o QR não é desenhado: pip install segno)", file=out)
    print("Sem câmera? No app: Conectar > Digitar o código, e cole a linha abaixo.", file=out)
    print(uri, file=out)
    print("\nEste código dá acesso ao telescópio. Não o envie por mensagem nem o deixe em foto.",
          file=out)
    return 0


def cmd_clients(a, out) -> int:
    clients = PairingService(DeviceIdentity.load_or_create(a.identity_dir)).clients()
    if not clients:
        print("Nenhum celular pareado.", file=out)
        return 0
    print(f"{'id':<8} {'papel':<9} {'pareado em':<17} {'último uso':<17} nome", file=out)
    for c in clients:
        print(f"{c.id:<8} {c.role:<9} {_when(c.created):<17} {_when(c.last_used):<17} {c.name}", file=out)
    return 0


def cmd_revoke(a, out) -> int:
    ok = PairingService(DeviceIdentity.load_or_create(a.identity_dir)).revoke(a.client_id)
    print(f"Celular {a.client_id} revogado." if ok else f"Não há celular {a.client_id}.", file=out)
    return 0 if ok else 1


def cmd_reset(a, out) -> int:
    if not a.yes:
        print("Isto tira TODOS os celulares e invalida os QR antigos. Repita com --yes.", file=out)
        return 2
    identity = DeviceIdentity.load_or_create(a.identity_dir)
    PairingService(identity).revoke_all()
    identity.rotate_pairing_secret()
    print("Pareamento zerado: nenhum celular entra; o segredo é novo. Rode 'pair' para parear.",
          file=out)
    return 0


def cmd_info(a, out) -> int:
    identity = DeviceIdentity.load_or_create(a.identity_dir)
    svc = PairingService(identity)
    if a.id_only:
        print(identity.device_id, file=out)
        return 0
    print(f"Aparelho:           {identity.device_id}", file=out)
    print(f"Impressão digital:  {identity.fingerprint}", file=out)
    print(f"Pasta da identidade: {identity.directory}", file=out)
    print(f"Celulares pareados: {len(svc.clients())}", file=out)
    print(f"Janela de pareamento: {'aberta' if svc.window_open else 'fechada'}", file=out)
    return 0


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    ap = argparse.ArgumentParser(prog="src.api.cli", description="Pareamento do app com o telescópio")
    ap.add_argument("--identity-dir", default=None, help="pasta da identidade (padrão: a do serviço)")
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("pair", help="abre a janela de pareamento e mostra o QR")
    p.add_argument("--minutes", type=float, default=5.0)
    p.add_argument("--port", type=int, default=API_PORT)
    p.add_argument("--host", default=None, help="endereço que vai no QR (padrão: o desta máquina)")
    p.add_argument("--ssid", default=None, help="WiFi do telescópio (modo campo)")
    p.add_argument("--psk", default=None, help="senha desse WiFi")
    p.set_defaults(run=cmd_pair)
    sub.add_parser("clients", help="lista os celulares pareados").set_defaults(run=cmd_clients)
    p = sub.add_parser("revoke", help="tira um celular")
    p.add_argument("client_id")
    p.set_defaults(run=cmd_revoke)
    p = sub.add_parser("reset", help="tira todos os celulares e troca o segredo")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(run=cmd_reset)
    p = sub.add_parser("info", help="identificador e impressão digital do aparelho")
    p.add_argument("--id-only", action="store_true", help="só o identificador (para scripts)")
    p.set_defaults(run=cmd_info)
    a = ap.parse_args(argv)
    return a.run(a, out)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(main())
