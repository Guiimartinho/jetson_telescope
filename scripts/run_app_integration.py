#!/usr/bin/env python3
"""O app (Dart) contra o software da Jetson, juntos, no PC — sem aparelho.

    py -3.11 scripts/run_app_integration.py

Sobe `run_console.py --api` em portas livres, com uma identidade descartável; abre a janela de
pareamento com o comando do dono; roda `flutter test test/integration` com o código do QR; e
derruba tudo. É o teste que prova as duas metades conversando: TLS 1.3 com o certificado
fixado, pareamento, token, canal em tempo real e imagem ao vivo. A rede e a atualização entram
com os adapters de mentira (`TELE_NETWORK=sim`, `TELE_UPDATES=sim`): nada no PC é trocado.

Não mexe na identidade de verdade (`~/.config/telescope`), nem nas portas 8080/8443.
"""
from __future__ import annotations

import io
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port: int, seconds: float) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main() -> int:
    flutter = os.environ.get("FLUTTER") or shutil.which("flutter") or shutil.which("flutter.bat")
    if not flutter:
        print("flutter não encontrado: ponha-o no PATH ou defina FLUTTER=<caminho>")
        return 2
    web, ws, api = free_port(), free_port(), free_port()
    with tempfile.TemporaryDirectory() as identity:
        env = dict(os.environ, TELE_IDENTITY_DIR=identity, PYTHONIOENCODING="utf-8",
                   TELE_NETWORK="sim", TELE_UPDATES="sim")
        env.pop("TELE_MOUNT", None)                       # sempre os simuladores
        server = subprocess.Popen(
            [sys.executable, "run_console.py", "--host", "127.0.0.1", "--port", str(web),
             "--ws-port", str(ws), "--api", "--api-port", str(api)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
        try:
            if not wait_port(api, 60):
                print("a API não subiu")
                return 1
            from src.api import cli
            out = io.StringIO()
            cli.main(["--identity-dir", identity, "pair", "--host", "127.0.0.1", "--port", str(api)], out=out)
            uri = next(line for line in out.getvalue().splitlines() if line.startswith("tele://pair?"))
            print(f"servidor no ar (API na porta {api}); rodando os testes do app...")
            result = subprocess.run([flutter, "test", "test/integration", "--reporter", "expanded"],
                                    cwd=ROOT / "app", env=dict(env, TELE_PAIR_URI=uri))
            return result.returncode
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    raise SystemExit(main())
