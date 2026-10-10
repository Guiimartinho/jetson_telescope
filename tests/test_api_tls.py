"""A API na rede de verdade (só a interface local): TLS 1.3, certificado fixado e impostor.

Sobe o servidor real numa porta livre e fala com ele como o app fará — sem autoridade
certificadora: a confiança é a impressão digital do certificado, lida do QR. São os testes de
`app/docs/07-seguranca.md` §12 que dependem do canal.
"""
import hashlib
import json
import socket
import ssl

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("uvicorn")
pytest.importorskip("cryptography")

from src.api.app import ApiContext                                           # noqa: E402
from src.api.identity import DeviceIdentity, b64u, b64u_decode               # noqa: E402
from src.api.pairing import PairingService, pairing_proof                    # noqa: E402
from src.api.server import ApiServer                                         # noqa: E402
from src.server.webview import FrameHub                                      # noqa: E402


class ImpostorError(Exception):
    pass


def _context(directory):
    ident = DeviceIdentity.load_or_create(directory)
    hub = FrameHub()
    hub.update(b"", {"state": "IDLE", "job": None, "outcome": ""})
    return ApiContext(identity=ident, pairing=PairingService(ident), hub=hub,
                      submit=lambda cmd, tag=None: None)


@pytest.fixture
def server(tmp_path):
    srv = ApiServer(_context(tmp_path / "identity"), host="127.0.0.1", port=0).start()
    yield srv
    srv.stop()


def pinned_request(port, fingerprint, method="GET", path="/api/v1/info", body=None, token=None,
                   maximum=None):
    """Uma chamada como a do app: nenhuma raiz confiável; vale só a impressão digital."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE               # a conferência é a NOSSA, logo abaixo
    if maximum is not None:
        ctx.maximum_version = maximum
    with socket.create_connection(("127.0.0.1", port), timeout=10) as raw:
        with ctx.wrap_socket(raw) as tls:
            if hashlib.sha256(tls.getpeercert(binary_form=True)).digest() != fingerprint:
                raise ImpostorError("o certificado não é o do aparelho pareado")
            data = json.dumps(body).encode() if body is not None else b""
            head = [f"{method} {path} HTTP/1.1", "Host: telescopio.local", "Connection: close",
                    f"Content-Length: {len(data)}"]
            if body is not None:
                head.append("Content-Type: application/json")
            if token:
                head.append(f"Authorization: Bearer {token}")
            tls.sendall(("\r\n".join(head) + "\r\n\r\n").encode() + data)
            raw_response = b""
            while chunk := tls.recv(65536):
                raw_response += chunk
            version = tls.version()
    header, _, payload = raw_response.partition(b"\r\n\r\n")
    return int(header.split()[1]), json.loads(payload), version


def test_api_answers_over_tls_1_3_with_the_device_certificate(server):
    ident = server.ctx.identity
    status, info, version = pinned_request(server.port, ident.fingerprint_bytes)
    assert status == 200 and info["id"] == ident.device_id
    assert version == "TLSv1.3"


def test_older_tls_is_refused(server):
    with pytest.raises((ssl.SSLError, ConnectionError, OSError)):
        pinned_request(server.port, server.ctx.identity.fingerprint_bytes,
                       maximum=ssl.TLSVersion.TLSv1_2)


def test_plain_http_is_not_spoken_on_the_api_port(server):
    with socket.create_connection(("127.0.0.1", server.port), timeout=10) as raw:
        raw.sendall(b"GET /api/v1/info HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
        try:
            resposta = raw.recv(4096)
        except OSError:
            resposta = b""
    assert b"tele-" not in resposta and b"200 OK" not in resposta


def test_impostor_with_another_certificate_is_caught(server, tmp_path):
    """Alguém responde como "telescopio.local" com outro certificado: o app tem de parar
    antes de mandar qualquer coisa — é para isso que serve a impressão digital do QR."""
    impostor = ApiServer(_context(tmp_path / "impostor"), host="127.0.0.1", port=0).start()
    try:
        with pytest.raises(ImpostorError):
            pinned_request(impostor.port, server.ctx.identity.fingerprint_bytes)
    finally:
        impostor.stop()


def test_pairing_and_a_protected_call_through_the_real_channel(server):
    ident, port = server.ctx.identity, server.port
    fp = ident.fingerprint_bytes
    assert pinned_request(port, fp, path="/api/v1/state")[0] == 401
    server.ctx.pairing.open_window()
    _, started, _ = pinned_request(port, fp, "POST", "/api/v1/pair/start", {"client_name": "Pixel"})
    proof = b64u(pairing_proof(ident.pairing_secret, b64u_decode(started["nonce"]), fp, "Pixel"))
    status, paired, _ = pinned_request(port, fp, "POST", "/api/v1/pair/finish",
                                       {"client_name": "Pixel", "proof": proof})
    assert status == 200 and paired["device_id"] == ident.device_id
    status, state, _ = pinned_request(port, fp, path="/api/v1/state", token=paired["token"])
    assert status == 200 and state["state"] == "IDLE"


def test_live_channel_works_over_tls(server):
    """`wss://` na mesma porta: o estado chega empurrado, cifrado, com o token no cabeçalho."""
    websockets_client = pytest.importorskip("websockets.sync.client")
    ident = server.ctx.identity
    server.ctx.pairing.open_window()
    nonce, _ = server.ctx.pairing.start("Pixel")
    token, _ = server.ctx.pairing.finish(
        "Pixel", b64u(pairing_proof(ident.pairing_secret, b64u_decode(nonce), ident.fingerprint_bytes, "Pixel")))
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with websockets_client.connect(f"wss://127.0.0.1:{server.port}/api/v1/ws", ssl=ctx,
                                   additional_headers={"Authorization": f"Bearer {token}"}) as ws:
        der = ws.socket.getpeercert(binary_form=True)
        assert hashlib.sha256(der).digest() == ident.fingerprint_bytes
        first = json.loads(ws.recv(timeout=10))
        assert first["type"] == "state" and first["seq"] == 1
        server.ctx.hub.update(b"", {"state": "STACKING", "job": None, "outcome": ""})
        for _ in range(10):
            msg = json.loads(ws.recv(timeout=10))
            if msg["type"] == "state":
                break
        assert msg["data"]["state"] == "STACKING"


def test_port_already_in_use_fails_with_a_clear_error(server, tmp_path):
    with pytest.raises(OSError):
        ApiServer(_context(tmp_path / "outro"), host="127.0.0.1", port=server.port).start()
