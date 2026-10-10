"""Pareamento e tokens: quem pode falar com o telescópio.

O celular lê o QR do aparelho (impressão digital + segredo de 128 bits), abre o canal cifrado,
confere a impressão digital e então PROVA que tem o segredo — sem enviá-lo:

    prova = HMAC-SHA256(segredo, número sorteado pela Jetson + impressão digital + nome do celular)

Conferida a prova, a Jetson devolve um token (256 bits) e guarda só o resumo dele. Daí em
diante toda chamada leva o token. Regras que fecham as portas laterais:

  * só se pareia com a JANELA aberta (o dono abre; fechada por padrão), e ela se fecha
    sozinha depois de um pareamento: uma janela, um celular;
  * o número sorteado vale uma vez e por pouco tempo;
  * cinco provas erradas fecham a janela, com espera crescente.

Os arquivos (celulares pareados, janela) ficam na pasta da identidade. O comando de pareamento
roda em OUTRO processo e conversa com o serviço por eles: quem consegue escrever ali já é o
dono do aparelho. Ver app/docs/07-seguranca.md.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .identity import DeviceIdentity, _write_private, b64u, b64u_decode

NONCE_TTL_S = 60
MAX_FAILURES = 5
SAVE_LAST_USED_EVERY_S = 900.0        # o "último uso" vai ao disco no máximo a cada 15 min
ROLES = ("owner", "operator", "viewer")
_WINDOW_FILE = "pairing-window"


class PairingError(Exception):
    """Falha de pareamento ou autenticação, com um código que o app sabe traduzir."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Client:
    id: str
    name: str
    role: str
    token_sha256: str
    created: float
    last_used: float

    def public(self) -> dict:
        """O que pode aparecer numa tela — nunca o resumo do token."""
        d = asdict(self)
        d.pop("token_sha256")
        return d


def pairing_proof(secret: bytes, nonce: bytes, fingerprint: bytes, client_name: str) -> bytes:
    """A mesma conta dos dois lados (Jetson aqui; app em Dart)."""
    return hmac.new(secret, nonce + fingerprint + client_name.encode("utf-8"),
                    hashlib.sha256).digest()


class PairingService:
    def __init__(self, identity: DeviceIdentity, store: Path | str | None = None, clock=time.time):
        self.identity = identity
        self.store = Path(store) if store else identity.directory / "clients.json"
        self._clock = clock
        self._lock = threading.Lock()
        self._window_until = 0.0
        self._invite: tuple[bytes, float, str] | None = None  # convite: (segredo, validade, papel)
        self._locked_until = 0.0
        self._failures = 0
        self._lockouts = 0
        self._nonces: dict[str, tuple[bytes, float]] = {}     # nome do celular -> (nonce, validade)
        self._clients: dict[str, Client] = {}
        self._window_file = identity.directory / _WINDOW_FILE
        self._store_sig: tuple | None = None                  # para notar quando o arquivo muda
        self._saved_at = clock()
        self._load()

    # ------------------------------------------------------------------ janela
    def open_window(self, seconds: float = 300.0, shared: bool = False) -> None:
        """O dono autoriza parear durante `seconds`. Sem isso ninguém pareia. `shared`: grava
        a janela em arquivo, para o serviço (outro processo) enxergá-la — é o que o comando
        de pareamento usa. Quem entra pela janela prova o segredo DO APARELHO e vira dono."""
        with self._lock:
            self._window_until = self._clock() + seconds
            self._failures = 0
            if shared:
                _write_private(self._window_file, json.dumps(
                    {"opened": self._clock(), "seconds": float(seconds)}).encode("ascii"))

    def close_window(self) -> None:
        with self._lock:
            self._close_window()

    def invite(self, seconds: float = 300.0, role: str = "operator") -> bytes:
        """Convite de um dono para OUTRO celular: sorteia um segredo NOVO, de uso único, que
        vale `seconds` e dá o papel `role`. É ele que vai no QR mostrado na tela do dono — o
        segredo do aparelho (o da etiqueta) nunca sai daqui. Um convite novo cancela o anterior."""
        if role not in ROLES:
            raise PairingError("invalid_argument", f"papel: use um de {', '.join(ROLES)}")
        with self._lock:
            secret = secrets.token_bytes(16)
            self._invite = (secret, self._clock() + float(seconds), role)
            self._failures = 0
            return secret

    def _invite_active(self, now: float) -> bool:
        return self._invite is not None and now < self._invite[1]

    def _close_window(self) -> None:
        self._window_until = 0.0
        self._nonces.clear()
        try:
            self._window_file.unlink()
        except OSError:
            pass

    def _open_until(self) -> float:
        """Até quando a janela vale: a aberta neste processo ou a gravada pelo comando. A do
        arquivo só conta dentro do próprio prazo — se o relógio voltar, ela não fica aberta."""
        until = self._window_until
        try:
            d = json.loads(self._window_file.read_text("ascii"))
            opened, seconds = float(d["opened"]), float(d["seconds"])
            if 0.0 <= self._clock() - opened < seconds:
                until = max(until, opened + seconds)
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return until

    @property
    def window_open(self) -> bool:
        """Dá para parear agora? Pela janela do dono ou por um convite ainda válido."""
        now = self._clock()
        return now >= self._locked_until and (now < self._open_until() or self._invite_active(now))

    # -------------------------------------------------------------- pareamento
    def start(self, client_name: str) -> tuple[str, int]:
        """Passo 1: devolve um número sorteado (base64) e por quantos segundos ele vale."""
        name = _clean_name(client_name)
        with self._lock:
            self._require_window()
            nonce = secrets.token_bytes(32)
            self._nonces[name] = (nonce, self._clock() + NONCE_TTL_S)
            return b64u(nonce), NONCE_TTL_S

    def finish(self, client_name: str, proof_b64: str, role: str | None = None) -> tuple[str, Client]:
        """Passo 2: confere a prova e emite o token. O token só existe nesta resposta.

        Há dois jeitos de provar, e cada um dá um papel: o segredo DO APARELHO, com a janela do
        dono aberta, faz um dono; o segredo de um CONVITE faz o papel que o dono escolheu, uma
        vez só. Um não vale no lugar do outro."""
        name = _clean_name(client_name)
        with self._lock:
            self._require_window()
            now = self._clock()
            nonce, expires = self._nonces.pop(name, (b"", 0.0))        # uso único
            if not nonce or now > expires:
                raise PairingError("pairing_expired", "peça um novo número: o anterior expirou")
            try:
                proof = b64u_decode(proof_b64)
            except Exception:
                proof = b""
            ways = []                                          # (segredo, papel, é convite)
            if self._invite_active(now):
                ways.append((self._invite[0], self._invite[2], True))
            if now < self._open_until():
                ways.append((self.identity.pairing_secret, "owner", False))
            matched = None
            for secret, granted, by_invite in ways:
                expected = pairing_proof(secret, nonce, self.identity.fingerprint_bytes, name)
                if hmac.compare_digest(expected, proof):
                    matched = (granted, by_invite)
            if matched is None:
                self._register_failure()
                raise PairingError("pairing_rejected", "o código de pareamento não confere")
            token = secrets.token_urlsafe(32)
            client = Client(id="c-" + secrets.token_hex(2), name=name, role=role or matched[0],
                            token_sha256=_digest(token), created=now, last_used=now)
            self._refresh()
            self._clients[client.id] = client
            self._failures = 0
            self._save()
            if matched[1]:
                self._invite = None                            # um convite, um celular
                self._nonces.clear()
            else:
                self._close_window()                           # uma janela, um celular
            return token, client

    def _require_window(self) -> None:
        now = self._clock()
        if now < self._locked_until:
            raise PairingError("pairing_locked", "muitas tentativas erradas; aguarde")
        if now >= self._open_until() and not self._invite_active(now):
            raise PairingError("pairing_closed", "a janela de pareamento está fechada")

    def _register_failure(self) -> None:
        self._failures += 1
        if self._failures >= MAX_FAILURES:                     # fecha e faz esperar, cada vez mais
            self._lockouts += 1
            self._close_window()
            self._invite = None
            self._locked_until = self._clock() + 30.0 * (2 ** (self._lockouts - 1))
            self._failures = 0

    # ------------------------------------------------------------ autenticação
    def authenticate(self, token: str | None) -> Client | None:
        """O celular dono deste token, ou None. Comparação em tempo constante."""
        if not token:
            return None
        digest = _digest(token)
        with self._lock:
            self._refresh()
            for c in self._clients.values():
                if hmac.compare_digest(c.token_sha256, digest):
                    c.last_used = now = self._clock()
                    if now - self._saved_at > SAVE_LAST_USED_EVERY_S:
                        self._save()
                    return c
        return None

    def clients(self) -> list[Client]:
        with self._lock:
            self._refresh()
            return sorted(self._clients.values(), key=lambda c: c.created)

    def revoke(self, client_id: str) -> bool:
        with self._lock:
            self._refresh()
            if self._clients.pop(client_id, None) is None:
                return False
            self._save()
            return True

    def set_role(self, client_id: str, role: str) -> bool:
        """Muda o papel de um celular. Recusa (`last_owner`) tirar o último dono: sem dono,
        ninguém mais administra o aparelho pelo app."""
        if role not in ROLES:
            raise PairingError("invalid_argument", f"papel: use um de {', '.join(ROLES)}")
        with self._lock:
            self._refresh()
            client = self._clients.get(client_id)
            if client is None:
                return False
            owners = [c for c in self._clients.values() if c.role == "owner"]
            if client.role == "owner" and role != "owner" and len(owners) <= 1:
                raise PairingError("last_owner", "este é o único dono: escolha outro dono antes")
            client.role = role
            self._save()
            return True

    def revoke_all(self) -> None:
        """Reinício de fábrica do lado dos celulares: ninguém mais entra sem parear de novo."""
        with self._lock:
            self._clients.clear()
            self._save()
            self._close_window()
            self._invite = None

    # ------------------------------------------------------------ persistência
    def _signature(self) -> tuple | None:
        try:
            st = self.store.stat()
            return (st.st_mtime_ns, st.st_size)
        except OSError:
            return None

    def _load(self) -> None:
        self._store_sig = self._signature()
        seen = self._clients                                   # o "último uso" em memória vale
        self._clients = {}
        if self._store_sig is None:
            return
        try:
            for d in json.loads(self.store.read_text("utf-8")):
                c = Client(**d)
                if c.id in seen:
                    c.last_used = max(c.last_used, seen[c.id].last_used)
                self._clients[c.id] = c
        except (OSError, ValueError, KeyError, TypeError):
            self._clients = {}                                 # arquivo corrompido: ninguém entra

    def _refresh(self) -> None:
        """Relê os celulares se o arquivo mudou por fora (o comando revogou alguém)."""
        if self._signature() != self._store_sig:
            self._load()

    def _save(self) -> None:
        data = json.dumps([asdict(c) for c in self._clients.values()], indent=1)
        _write_private(self.store, data.encode("utf-8"))
        self._store_sig = self._signature()
        self._saved_at = self._clock()


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _clean_name(name: str) -> str:
    name = " ".join(str(name or "").split())[:60]
    if not name:
        raise PairingError("invalid_argument", "informe o nome do celular")
    return name
