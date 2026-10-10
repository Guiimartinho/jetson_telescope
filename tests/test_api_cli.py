"""O comando do dono (`src.api.cli`): parear, listar, revogar e zerar — sem rede.

O comando roda em outro processo que o serviço; aqui o "serviço" é um `PairingService` na
mesma pasta de identidade, exatamente como na Jetson.
"""
import io
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("cryptography")

from src.api import cli                                                      # noqa: E402
from src.api.identity import DeviceIdentity, b64u, b64u_decode               # noqa: E402
from src.api.pairing import PairingService, pairing_proof                    # noqa: E402


def run(tmp_path, *argv):
    out = io.StringIO()
    code = cli.main(["--identity-dir", str(tmp_path / "id"), *argv], out=out)
    return code, out.getvalue()


def _service(tmp_path):
    ident = DeviceIdentity.load_or_create(tmp_path / "id")
    return ident, PairingService(ident)


def _pair_with(uri, svc, name="Pixel"):
    """O que o app faz com o código lido do QR."""
    q = {k: v[0] for k, v in parse_qs(urlparse(uri).query).items()}
    nonce, _ = svc.start(name)
    proof = pairing_proof(b64u_decode(q["s"]), b64u_decode(nonce), b64u_decode(q["fp"]), name)
    return svc.finish(name, b64u(proof))


def test_pair_opens_the_window_and_prints_a_code_that_really_pairs(tmp_path):
    ident, svc = _service(tmp_path)
    assert not svc.window_open
    code, text = run(tmp_path, "pair", "--host", "192.168.3.221", "--minutes", "2")
    assert code == 0 and svc.window_open, "o serviço enxerga a janela aberta pelo comando"
    uri = next(line for line in text.splitlines() if line.startswith("tele://pair?"))
    q = {k: v[0] for k, v in parse_qs(urlparse(uri).query).items()}
    assert (q["id"], q["host"], q["port"]) == (ident.device_id, "192.168.3.221", "8443")
    token, client = _pair_with(uri, svc)
    assert svc.authenticate(token).id == client.id


def test_pair_draws_the_qr_when_the_library_is_there(tmp_path):
    pytest.importorskip("segno")
    _, text = run(tmp_path, "pair", "--host", "10.0.0.2")
    assert "█" in text or "▀" in text or "▄" in text, "QR desenhado com blocos"


def test_pair_without_the_qr_library_still_gives_the_code(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "qr_text", lambda data: None)
    code, text = run(tmp_path, "pair", "--host", "10.0.0.2")
    assert code == 0 and "tele://pair?" in text and "pip install segno" in text


def test_clients_and_revoke(tmp_path):
    ident, svc = _service(tmp_path)
    assert "Nenhum celular" in run(tmp_path, "clients")[1]
    _, text = run(tmp_path, "pair", "--host", "10.0.0.2")
    uri = next(line for line in text.splitlines() if line.startswith("tele://pair?"))
    token, client = _pair_with(uri, svc, "Pixel do Guilherme")
    code, text = run(tmp_path, "clients")
    assert code == 0 and client.id in text and "Pixel do Guilherme" in text and "owner" in text
    assert token not in text
    assert run(tmp_path, "revoke", client.id)[0] == 0
    assert svc.authenticate(token) is None, "revogado pelo comando: o serviço já recusa"
    assert run(tmp_path, "revoke", client.id)[0] == 1


def test_reset_needs_confirmation_and_then_invalidates_everything(tmp_path):
    ident, svc = _service(tmp_path)
    _, text = run(tmp_path, "pair", "--host", "10.0.0.2")
    antigo = next(line for line in text.splitlines() if line.startswith("tele://pair?"))
    token, _ = _pair_with(antigo, svc)
    assert run(tmp_path, "reset")[0] == 2 and svc.authenticate(token) is not None
    assert run(tmp_path, "reset", "--yes")[0] == 0
    assert svc.authenticate(token) is None
    depois = DeviceIdentity.load_or_create(tmp_path / "id")
    assert depois.pairing_secret != ident.pairing_secret, "os QR antigos param de valer"
    assert depois.fingerprint == ident.fingerprint, "o certificado é o mesmo: só o segredo muda"


def test_info_shows_no_secret(tmp_path):
    ident, _ = _service(tmp_path)
    code, text = run(tmp_path, "info")
    assert code == 0 and ident.device_id in text and ident.fingerprint in text
    assert b64u(ident.pairing_secret) not in text
    assert run(tmp_path, "info", "--id-only")[1].strip() == ident.device_id
