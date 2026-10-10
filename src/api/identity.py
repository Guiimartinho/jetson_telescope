"""Identidade do aparelho: a chave que prova que a Jetson é ela mesma.

Não há autoridade certificadora nem internet. Na primeira vez que liga, o aparelho cria:

  * uma chave privada ECDSA P-256 e um certificado autoassinado de validade longa;
  * a IMPRESSÃO DIGITAL desse certificado (SHA-256) — é o que o app fixa no pareamento;
  * um segredo de pareamento de 128 bits — só quem o tem (lendo o QR) pode parear.

A confiança do app é a chave fixada, não as datas do certificado: no campo a Jetson pode ligar
achando que é o ano 2000, e a conexão tem de funcionar assim mesmo (é por ela que o celular
acerta a hora). Nada daqui é versionado nem sai do aparelho. Ver app/docs/07-seguranca.md.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

API_PORT = 8443
_CERT, _KEY, _SECRET = "device-cert.pem", "device-key.pem", "pairing-secret"


def default_dir() -> Path:
    """Onde a identidade mora. `TELE_IDENTITY_DIR` troca o lugar (testes, bancada)."""
    env = os.environ.get("TELE_IDENTITY_DIR")
    return Path(env) if env else Path.home() / ".config" / "telescope" / "identity"


def b64u(data: bytes) -> str:
    """base64 seguro para URL, sem preenchimento — o formato de tudo que vai no QR e na API."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64u_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _write_private(path: Path, data: bytes) -> None:
    """Grava com acesso só do dono (0600) e de uma vez só: escreve ao lado e troca, para que
    outro processo nunca leia o arquivo pela metade. No Windows o chmod é limitado; vale na
    Jetson."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


class DeviceIdentity:
    def __init__(self, directory: Path, cert_der: bytes, pairing_secret: bytes):
        self.directory = Path(directory)
        self.cert_der = cert_der
        self.pairing_secret = pairing_secret

    # ------------------------------------------------------------ criação/carga
    @classmethod
    def load_or_create(cls, directory: Path | str | None = None) -> "DeviceIdentity":
        d = Path(directory) if directory else default_dir()
        cert_p, key_p, secret_p = d / _CERT, d / _KEY, d / _SECRET
        if not (cert_p.exists() and key_p.exists()):
            cert_pem, key_pem = _new_certificate()
            _write_private(key_p, key_pem)
            _write_private(cert_p, cert_pem)
        if not secret_p.exists():
            _write_private(secret_p, secrets.token_bytes(16))
        cert_der = ssl.PEM_cert_to_DER_cert(cert_p.read_text("ascii"))
        return cls(d, cert_der, secret_p.read_bytes())

    # ----------------------------------------------------------------- leitura
    @property
    def cert_path(self) -> Path:
        return self.directory / _CERT

    @property
    def key_path(self) -> Path:
        return self.directory / _KEY

    @property
    def fingerprint_bytes(self) -> bytes:
        """SHA-256 do certificado (DER). O app compara ESTE valor a cada conexão."""
        return hashlib.sha256(self.cert_der).digest()

    @property
    def fingerprint(self) -> str:
        return b64u(self.fingerprint_bytes)

    @property
    def device_id(self) -> str:
        """Curto e estável, derivado da impressão digital: nome do aparelho na rede e no QR."""
        return "tele-" + self.fingerprint_bytes[:2].hex()

    # ------------------------------------------------------------- pareamento
    def pairing_uri(self, port: int = API_PORT, host: str | None = None,
                    ssid: str | None = None, psk: str | None = None,
                    secret: bytes | None = None) -> str:
        """O conteúdo do QR: tudo que o app precisa para confiar no aparelho ANTES de falar com
        ele. Contém o segredo — mostrar só por canal local (terminal, etiqueta), nunca por HTTP.

        `secret`: o segredo de um CONVITE (uso único, sorteado na hora), no lugar do segredo do
        aparelho. É o único que viaja pela API, e só para um dono já pareado, pelo canal cifrado."""
        q = {"v": "1", "id": self.device_id, "fp": self.fingerprint,
             "s": b64u(secret if secret is not None else self.pairing_secret), "port": str(port)}
        for k, v in (("host", host), ("ssid", ssid), ("psk", psk)):
            if v:
                q[k] = v
        return "tele://pair?" + urlencode(q)

    def rotate_pairing_secret(self) -> None:
        """Sorteia outro segredo: os QR antigos param de valer (reinício de fábrica, convite)."""
        self.pairing_secret = secrets.token_bytes(16)
        _write_private(self.directory / _SECRET, self.pairing_secret)

    # --------------------------------------------------------------------- TLS
    def ssl_context(self) -> ssl.SSLContext:
        """Contexto de servidor: só TLS 1.3, com a chave e o certificado do aparelho."""
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.minimum_version = ssl.TLSVersion.TLSv1_3
        ctx.load_cert_chain(str(self.cert_path), str(self.key_path))
        return ctx


def _new_certificate() -> tuple[bytes, bytes]:
    """Chave ECDSA P-256 + certificado autoassinado. As datas são largas de propósito: quem
    dá a confiança é a chave fixada pelo app, e o relógio do aparelho pode estar errado."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "telescope")])
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime(2000, 1, 1, tzinfo=timezone.utc))
            .not_valid_after(datetime(2099, 12, 31, tzinfo=timezone.utc))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("telescopio.local"),
                                                        x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    return cert.public_bytes(serialization.Encoding.PEM), key_pem
