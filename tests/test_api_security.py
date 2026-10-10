"""Segurança da API do app: identidade do aparelho, pareamento e tokens (app/docs/07-seguranca.md).

Roda sem rede e sem aparelho. O que estes testes travam é o que, se quebrar, abre a porta:
quem não tem o segredo não pareia; a prova não é reaproveitável; tentativa repetida fecha a
janela; e o token nunca fica guardado em claro.
"""
import hashlib
import os
import ssl
import sys
from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("cryptography")

from src.api.identity import DeviceIdentity, b64u, b64u_decode                    # noqa: E402
from src.api.pairing import (MAX_FAILURES, NONCE_TTL_S, PairingError, PairingService,  # noqa: E402
                             pairing_proof)


class Clock:
    """Relógio de teste: o tempo só anda quando o teste manda."""
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


@pytest.fixture
def ident(tmp_path):
    return DeviceIdentity.load_or_create(tmp_path / "identity")


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def svc(ident, clock):
    return PairingService(ident, clock=clock)


def _proof(ident, nonce_b64, name):
    return b64u(pairing_proof(ident.pairing_secret, b64u_decode(nonce_b64),
                              ident.fingerprint_bytes, name))


def _pair(svc, ident, name="Pixel de teste"):
    svc.open_window()
    nonce, _ = svc.start(name)
    return svc.finish(name, _proof(ident, nonce, name))


# ---- identidade -----------------------------------------------------------
def test_identity_is_created_once_and_survives_reload(tmp_path):
    a = DeviceIdentity.load_or_create(tmp_path / "id")
    b = DeviceIdentity.load_or_create(tmp_path / "id")
    assert a.fingerprint == b.fingerprint and a.pairing_secret == b.pairing_secret
    assert a.fingerprint_bytes == hashlib.sha256(a.cert_der).digest()
    assert a.device_id.startswith("tele-") and len(a.device_id) == 9
    assert len(a.pairing_secret) == 16, "128 bits: adivinhar por força bruta é inviável"


def test_two_devices_never_share_an_identity(tmp_path):
    a = DeviceIdentity.load_or_create(tmp_path / "a")
    b = DeviceIdentity.load_or_create(tmp_path / "b")
    assert a.fingerprint != b.fingerprint and a.pairing_secret != b.pairing_secret


def test_certificate_does_not_depend_on_the_clock(ident):
    """No campo a Jetson pode ligar achando que é o ano 2000. A confiança é a chave fixada;
    as datas do certificado têm de cobrir qualquer relógio plausível."""
    from cryptography import x509
    cert = x509.load_der_x509_certificate(ident.cert_der)
    antes = getattr(cert, "not_valid_before_utc", None) or cert.not_valid_before   # cryptography < 42
    depois = getattr(cert, "not_valid_after_utc", None) or cert.not_valid_after
    assert antes.year <= 2000 and depois.year >= 2090


def test_server_only_speaks_tls_1_3(ident):
    ctx = ident.ssl_context()
    assert ctx.minimum_version == ssl.TLSVersion.TLSv1_3


def test_qr_carries_what_the_app_needs_to_trust_the_device(ident):
    uri = urlparse(ident.pairing_uri(port=8443, ssid="Telescopio-0b04", psk="senha-do-wifi"))
    q = {k: v[0] for k, v in parse_qs(uri.query).items()}
    assert (uri.scheme, uri.netloc) == ("tele", "pair")
    assert q["id"] == ident.device_id and q["fp"] == ident.fingerprint and q["port"] == "8443"
    assert b64u_decode(q["s"]) == ident.pairing_secret
    assert q["ssid"] == "Telescopio-0b04" and q["psk"] == "senha-do-wifi"


def test_rotating_the_secret_invalidates_old_qr_codes(tmp_path):
    a = DeviceIdentity.load_or_create(tmp_path / "id")
    old = a.pairing_secret
    a.rotate_pairing_secret()
    assert a.pairing_secret != old
    assert DeviceIdentity.load_or_create(tmp_path / "id").pairing_secret == a.pairing_secret


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_private_files_are_owner_only(ident):
    for p in (ident.key_path, ident.directory / "pairing-secret"):
        assert os.stat(p).st_mode & 0o077 == 0, f"{p.name} legível por outros usuários"


# ---- pareamento -----------------------------------------------------------
def test_pairing_is_refused_while_the_window_is_closed(svc):
    with pytest.raises(PairingError) as e:
        svc.start("Pixel")
    assert e.value.code == "pairing_closed"


def test_phone_with_the_secret_pairs_and_gets_a_working_token(svc, ident):
    token, client = _pair(svc, ident)
    assert client.role == "owner" and client.name == "Pixel de teste"
    assert svc.authenticate(token).id == client.id
    assert svc.authenticate("token-inventado") is None
    assert svc.authenticate(None) is None


def test_wrong_secret_is_rejected(svc, ident):
    svc.open_window()
    nonce, _ = svc.start("Pixel")
    errada = b64u(pairing_proof(b"\x00" * 16, b64u_decode(nonce), ident.fingerprint_bytes, "Pixel"))
    with pytest.raises(PairingError) as e:
        svc.finish("Pixel", errada)
    assert e.value.code == "pairing_rejected"
    assert svc.clients() == []


def test_proof_is_single_use(svc, ident):
    """Capturar a prova na rede não serve para nada depois."""
    svc.open_window()
    nonce, _ = svc.start("Pixel")
    prova = _proof(ident, nonce, "Pixel")
    svc.finish("Pixel", prova)
    with pytest.raises(PairingError) as e:                   # a janela fechou com o pareamento
        svc.finish("Pixel", prova)
    assert e.value.code == "pairing_closed"
    svc.open_window()                                        # e mesmo reaberta, o número já foi
    with pytest.raises(PairingError) as e:
        svc.finish("Pixel", prova)
    assert e.value.code == "pairing_expired"


def test_proof_is_bound_to_the_phone_name_and_the_device(svc, ident, tmp_path):
    svc.open_window()
    nonce, _ = svc.start("Pixel")
    with pytest.raises(PairingError):                        # prova feita para outro nome
        svc.finish("Pixel", _proof(ident, nonce, "Outro celular"))
    outro = DeviceIdentity.load_or_create(tmp_path / "outro")
    nonce, _ = svc.start("Pixel")
    falsa = b64u(pairing_proof(ident.pairing_secret, b64u_decode(nonce),
                               outro.fingerprint_bytes, "Pixel"))
    with pytest.raises(PairingError):                        # prova ligada a outro certificado
        svc.finish("Pixel", falsa)


def test_challenge_expires(svc, ident, clock):
    svc.open_window(seconds=600)
    nonce, ttl = svc.start("Pixel")
    assert ttl == NONCE_TTL_S
    clock.advance(NONCE_TTL_S + 1)
    with pytest.raises(PairingError) as e:
        svc.finish("Pixel", _proof(ident, nonce, "Pixel"))
    assert e.value.code == "pairing_expired"


def test_window_closes_by_itself(svc, clock):
    svc.open_window(seconds=120)
    assert svc.window_open
    clock.advance(121)
    assert not svc.window_open


def test_repeated_failures_close_the_window_and_make_the_attacker_wait(svc, ident, clock):
    svc.open_window(seconds=3600)
    for _ in range(MAX_FAILURES):
        svc.start("Pixel")
        with pytest.raises(PairingError):
            svc.finish("Pixel", b64u(b"x" * 32))
    with pytest.raises(PairingError) as e:                   # agora nem a prova certa entra
        svc.start("Pixel")
    assert e.value.code == "pairing_locked"
    svc.open_window(seconds=3600)                            # reabrir não fura a espera
    with pytest.raises(PairingError) as e:
        svc.start("Pixel")
    assert e.value.code == "pairing_locked"
    clock.advance(31)                                        # passada a espera, o dono reabre
    svc.open_window()
    nonce, _ = svc.start("Pixel")
    token, _ = svc.finish("Pixel", _proof(ident, nonce, "Pixel"))
    assert svc.authenticate(token) is not None


# ---- tokens ---------------------------------------------------------------
def test_token_is_never_stored_in_clear(svc, ident):
    token, client = _pair(svc, ident)
    guardado = svc.store.read_text("utf-8")
    assert token not in guardado
    assert hashlib.sha256(token.encode()).hexdigest() in guardado
    assert "token_sha256" not in client.public()


def test_tokens_survive_a_restart(svc, ident, clock):
    token, client = _pair(svc, ident)
    depois = PairingService(ident, clock=clock)
    assert depois.authenticate(token).id == client.id


def test_revoked_phone_is_out_immediately(svc, ident):
    token, client = _pair(svc, ident)
    assert svc.revoke(client.id) is True
    assert svc.authenticate(token) is None
    assert svc.revoke(client.id) is False


def test_factory_reset_drops_every_phone(svc, ident):
    t1, _ = _pair(svc, ident, "Pixel")
    t2, _ = _pair(svc, ident, "Tablet")
    svc.revoke_all()
    assert svc.authenticate(t1) is None and svc.authenticate(t2) is None


# ---- o comando de pareamento roda em outro processo -----------------------
def test_window_closes_after_one_phone_pairs(svc, ident):
    """Uma janela, um celular: quem chegar depois precisa que o dono abra de novo."""
    _pair(svc, ident, "Pixel")
    assert not svc.window_open
    with pytest.raises(PairingError) as e:
        svc.start("Outro celular")
    assert e.value.code == "pairing_closed"


def test_pairing_command_opens_the_window_for_the_running_service(ident, clock):
    """O serviço e o comando são processos diferentes; conversam pela pasta da identidade."""
    servico = PairingService(ident, clock=clock)
    comando = PairingService(ident, clock=clock)
    assert not servico.window_open
    comando.open_window(seconds=120, shared=True)
    assert servico.window_open
    nonce, _ = servico.start("Pixel")
    token, _ = servico.finish("Pixel", _proof(ident, nonce, "Pixel"))
    assert not servico.window_open, "pareou: a janela gravada some"
    assert comando.authenticate(token) is not None


def test_shared_window_expires_and_survives_a_clock_going_backwards(ident, clock):
    servico = PairingService(ident, clock=clock)
    PairingService(ident, clock=clock).open_window(seconds=120, shared=True)
    clock.advance(-3600)                       # o relógio voltou (acerto de hora)
    assert not servico.window_open, "relógio atrasado não pode deixar a janela aberta por horas"
    clock.advance(3600 + 121)
    assert not servico.window_open


def test_lockout_also_closes_a_window_opened_by_the_command(ident, clock):
    servico = PairingService(ident, clock=clock)
    PairingService(ident, clock=clock).open_window(seconds=3600, shared=True)
    for _ in range(MAX_FAILURES):
        servico.start("Pixel")
        with pytest.raises(PairingError):
            servico.finish("Pixel", b64u(b"x" * 32))
    clock.advance(10_000)                      # passada a espera, a janela antiga não volta
    assert not servico.window_open


def test_revoking_from_the_command_takes_effect_in_the_running_service(ident, clock):
    servico = PairingService(ident, clock=clock)
    token, client = _pair(servico, ident)
    comando = PairingService(ident, clock=clock)
    assert comando.revoke(client.id) is True
    assert servico.authenticate(token) is None, "o serviço relê o arquivo quando ele muda"


def test_last_use_is_remembered_without_writing_on_every_request(svc, ident, clock):
    token, client = _pair(svc, ident)
    escrito = svc.store.stat().st_mtime_ns
    clock.advance(60)
    svc.authenticate(token)
    assert svc.store.stat().st_mtime_ns == escrito, "uma chamada não pode virar uma escrita"
    clock.advance(3600)
    svc.authenticate(token)
    depois = PairingService(ident, clock=clock)
    assert depois.clients()[0].last_used == pytest.approx(clock())
