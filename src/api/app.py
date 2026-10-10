"""Rotas da API v1 (FastAPI). Contrato em app/docs/04-api.md; segurança em 07-seguranca.md.

Este módulo não conhece hardware nem o Controller: recebe um `ApiContext` com o que precisa
(estado, fila de comandos, imagens) e por isso é testado com objetos simples. Regras gerais:

  * tudo exige o token do celular, menos `/info` e o pareamento;
  * comando longo devolve um trabalho (`job`); reenviar o mesmo `id` não executa de novo;
  * erro sempre no mesmo formato: `{"error": {"code": ..., "message": ...}}`;
  * o que ainda é simulado é DITO (em `/info` e nas respostas), nunca disfarçado.
"""
from __future__ import annotations

import asyncio
import shutil
import socket
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal

import anyio
from fastapi import Depends, FastAPI, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..core import ephem
from . import __version__, plan as planning, sky
from .audit import AuditLog
from .identity import DeviceIdentity
from .jobs import JobBook
from .network import NetworkControl, NetworkError
from .pairing import ROLES, Client, PairingError, PairingService
from .updates import UpdateError, Updater

API_VERSION = 1
MODES = ("stack", "autofind", "goto", "observe", "realdata", "scheduler", "mosaic", "tracking",
         "night", "preview", "focus", "plan", "polar", "planetary")
# o que dá para filmar no modo planetário (o Sol fica de fora: pede outro cuidado)
PLANETARY_BODIES = ("moon", "mercury", "venus", "mars", "jupiter", "saturn", "uranus", "neptune")
# Os modos que `/observe/run` aceita pelo nome. O alinhamento polar e a captura planetária só
# entram pelas rotas próprias: são elas que conferem a montagem e o corpo pedido.
RUN_MODES = tuple(m for m in MODES if m not in ("polar", "planetary"))
MAX_BODY_BYTES = 64 * 1024
_RANK = {"viewer": 0, "operator": 1, "owner": 2}
_ISO = "%Y-%m-%dT%H:%M:%SZ"
# partes do estado que o canal em tempo real manda separadas -> tipo da mensagem
_SECTIONS = {"job": "progress", "mount": "mount", "camera": "camera", "stack": "stack",
             "pointing": "pointing", "queue": "queue", "system": "system",
             "focus": "focus", "night": "night", "capture": "capture", "polar": "polar"}
# campos do retrato que repetem o que já vai numa parte (`focus_pos` é `focus.position`):
# mudança neles não obriga a mandar o retrato inteiro
_MIRRORED = ("focus_pos",)
# o que dá para fazer à mão na montagem (hoje: só na simulada; a real ainda não é comandada daqui)
MOUNT_FEATURES = ("jog", "park", "tracking", "home", "polar")
# estados em que um trabalho é dono da montagem: mexer à mão espera ele acabar
BUSY_STATES = ("SLEWING", "SOLVING", "FOCUSING", "STACKING", "SCHEDULING", "TRACKING", "CAPTURING")
CAMERA_LIMITS = {"exposure_s": (0.001, 600.0), "gain": (0, 600), "offset": (0, 255)}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


# ------------------------------------------------------------------ contexto
class SiteClock:
    """Local e relógio do aparelho. No campo não há internet (sem NTP) nem GPS: quem sabe a
    hora e o lugar é o celular. Guardamos a DIFERENÇA para o relógio do sistema em vez de
    acertá-lo (isso exigiria root); tudo que precisa de hora usa `now()`."""

    def __init__(self, lat=-23.55, lon=-46.63, elev_m=760.0):
        self.lat, self.lon, self.elev_m = float(lat), float(lon), float(elev_m)
        self.source = "default"
        self.offset_s = 0.0

    def now(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.offset_s)

    def set_from_phone(self, utc: datetime, lat: float, lon: float, elev_m: float) -> None:
        self.offset_s = (utc.astimezone(timezone.utc) - datetime.now(timezone.utc)).total_seconds()
        self.lat, self.lon, self.elev_m = float(lat), float(lon), float(elev_m)
        self.source = "phone"

    def as_dict(self) -> dict:
        return {"lat": self.lat, "lon": self.lon, "elev_m": self.elev_m, "source": self.source}


@dataclass
class CameraSettings:
    """O que o app pediu para a câmera. Com a câmera SIMULADA nada disto muda a imagem: fica
    guardado e a API diz `applied: false`. Quando a câmera chegar, o adapter dela lê daqui."""
    exposure_s: float = 30.0
    gain: int = 120
    offset: int = 10


@dataclass
class ApiContext:
    identity: DeviceIdentity
    pairing: PairingService
    hub: object                                   # FrameHub: get() e wait_change()
    submit: Callable[[str, str | None], None]     # fila do Controller: (comando, etiqueta)
    mount_link: object | None = None              # MountLink, ou None = montagem simulada
    site: SiteClock = field(default_factory=SiteClock)
    jobs: JobBook = field(default_factory=JobBook)
    audit: AuditLog = field(default_factory=AuditLog)
    name: str = "Telescópio"
    camera: CameraSettings = field(default_factory=CameraSettings)
    plan: planning.PlanStore = field(default_factory=planning.PlanStore)
    started: float = field(default_factory=time.monotonic)
    # o que depende de imagem/arquivo entra por função, para os testes não precisarem de GPU
    image_jpeg: Callable[[str, bool], bytes | None] | None = None      # (chave, miniatura)
    histogram: Callable[[], list] | None = None
    shrink: Callable[[bytes, int], bytes] | None = None                # (jpeg, lado máximo)
    sessions: Callable[[], list] | None = None
    render_session: Callable[[str, dict], bytes | None] | None = None  # ValueError = entrada ruim
    presets: Callable[[], dict] | None = None
    power: Callable[[str], None] | None = None    # "shutdown" | "restart"; None = desabilitado
    # (sessão, formato, lado máximo) -> (bytes ou caminho de arquivo, tipo, nome); None = não há
    export_session: Callable[[str, str, int], tuple | None] | None = None
    delete_session: Callable[[str], bool] | None = None
    save_name: Callable[[str], None] | None = None        # guarda o nome do aparelho
    qr_svg: Callable[[str], str | None] | None = None     # desenha o QR do convite
    network: NetworkControl | None = None         # porta da rede (`network.py`); None = não habilitada
    updater: Updater | None = None                # porta da atualização (`updates.py`); idem

    def plan_queue(self) -> list[dict]:
        """A fila da noite do jeito que o Controller executa (é o `plan_provider` dele)."""
        return planning.runnable(self.plan.items(), self.site.lat, self.site.lon, self.site.now())


# -------------------------------------------------------------------- estado
_SYS_CACHE: dict = {"t": 0.0, "v": {}}


def system_info() -> dict:
    """Temperatura e disco. Guardado por 2 s: é lido a cada mensagem do canal."""
    now = time.monotonic()
    if now - _SYS_CACHE["t"] < 2.0 and _SYS_CACHE["v"]:
        return _SYS_CACHE["v"]
    temp = None
    try:
        import glob
        vals = []
        for p in glob.glob("/sys/class/thermal/thermal_zone*/temp"):
            with open(p) as f:
                vals.append(int(f.read()) / 1000.0)
        temp = round(max(vals), 1) if vals else None
    except (OSError, ValueError):
        temp = None
    try:
        free = round(shutil.disk_usage(".").free / 1e9, 1)
    except OSError:
        free = None
    _SYS_CACHE.update(t=now, v={"temp_c": temp, "disk_free_gb": free})
    return _SYS_CACHE["v"]


def build_state(ctx: ApiContext) -> dict:
    """O retrato completo: o que `GET /state` devolve e a primeira mensagem do WebSocket."""
    _, st = ctx.hub.get()
    if ctx.mount_link is not None:
        m = ctx.mount_link.status()
        # a montagem real: a API a LÊ; mexer à mão por aqui ainda não existe (sem `features`)
        mount = {"source": "indi", "connected": bool(m.get("connected")),
                 "ra_deg": m.get("ra_deg"), "dec_deg": m.get("dec_deg"),
                 "tracking": None, "parked": None, "moving": None, "features": [],
                 "error": m.get("error")}
    else:
        ctl = st.get("mount_ctl") or {}
        mount = {"source": "sim", "connected": False, "ra_deg": None, "dec_deg": None,
                 "tracking": ctl.get("tracking"), "parked": ctl.get("parked"),
                 "moving": ctl.get("jog"), "features": list(MOUNT_FEATURES) if ctl else [],
                 "error": None}
    focus_range = st.get("focus_range") or [None, None]
    return {"state": st.get("state") or "IDLE", "phase": st.get("phase") or "",
            "backend": st.get("backend") or "", "filter": st.get("filter") or "",
            "focus_pos": int(st.get("focus_pos") or 0),
            "job": ctx.jobs.observe(st),
            "mount": mount,
            "camera": dict(asdict(ctx.camera), source="sim", connected=True,
                           model="simulador de céu", temp_c=None, applied=False),
            "focus": {"source": "sim", "position": int(st.get("focus_pos") or 0),
                      "min": focus_range[0], "max": focus_range[1],
                      "curve": [{"pos": p, "fwhm_px": f} for p, f in (st.get("focus_curve") or [])],
                      "best": st.get("focus_best")},
            # o andamento da noite autônoma: um registro por item do plano
            "night": list(st.get("plan") or []),
            # a captura planetária em curso (quadros recebidos e aproveitados), ou nada
            "capture": st.get("planet"),
            # a última medida do alinhamento polar, ou nada
            "polar": st.get("polar"),
            "stack": {"target": st.get("target") or "", "accepted": int(st.get("accepted") or 0),
                      "rejected": int(st.get("rejected") or 0),
                      "snr": float(st.get("snr") or 0.0), "fwhm_px": float(st.get("fwhm") or 0.0),
                      # com a câmera simulada não há exposição de verdade: não inventar tempo
                      "integration_s": None},
            "pointing": {"error": float(st.get("error_px") or 0.0), "unit": st.get("err_unit") or "px"},
            "queue": {"done": int(st.get("queue_done") or 0), "total": int(st.get("queue_total") or 0)},
            "system": system_info()}


def state_messages(last: dict | None, data: dict) -> list[tuple[str, object]]:
    """O que mandar pelo canal: o retrato inteiro na primeira vez e quando muda o estado
    geral; depois, só as partes que mudaram — o app não redesenha tudo a cada mensagem."""
    if last is None or any(last.get(k) != v for k, v in data.items()
                           if k not in _SECTIONS and k not in _MIRRORED):
        return [("state", data)]
    return [(kind, data[k]) for k, kind in _SECTIONS.items() if last.get(k) != data[k]]


# ------------------------------------------------------------------- modelos
class PairStart(BaseModel):
    client_name: str = Field(min_length=1, max_length=60)


class PairFinish(PairStart):
    proof: str = Field(min_length=1, max_length=200)


class Site(BaseModel):
    utc: datetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    elev_m: float = Field(default=0.0, ge=-500, le=9000)
    accuracy_m: float | None = Field(default=None, ge=0)


class Command(BaseModel):
    id: str = Field(min_length=1, max_length=64)


class Goto(Command):
    target: str | None = Field(default=None, min_length=1, max_length=40)
    ra_deg: float | None = Field(default=None, ge=0, lt=360)
    dec_deg: float | None = Field(default=None, ge=-90, le=90)


class Stack(Command):
    exposure_s: float | None = Field(default=None, gt=0, le=600)
    gain: int | None = Field(default=None, ge=0, le=600)
    frames: int = Field(default=0, ge=0, le=100000)


class Run(Command):
    mode: str = Field(max_length=20)
    target: str | None = Field(default=None, min_length=1, max_length=40)


class Jog(BaseModel):
    """Movimento manual. `hold_ms` é o PRAZO: o app renova o comando enquanto o dedo está no
    botão; se parar de renovar (soltou, ou o sinal caiu), a montagem para sozinha."""
    dir: Literal["N", "S", "E", "W"]
    rate: int = Field(default=2, ge=1, le=3)
    hold_ms: int = Field(default=800, ge=100, le=2000)


class Tracking(BaseModel):
    on: bool


class FocusMove(BaseModel):
    delta: int | None = Field(default=None, ge=-5000, le=5000)
    position: int | None = Field(default=None, ge=0, le=1_000_000)


class CameraSet(BaseModel):
    exposure_s: float | None = Field(default=None, ge=CAMERA_LIMITS["exposure_s"][0],
                                     le=CAMERA_LIMITS["exposure_s"][1])
    gain: int | None = Field(default=None, ge=CAMERA_LIMITS["gain"][0], le=CAMERA_LIMITS["gain"][1])
    offset: int | None = Field(default=None, ge=CAMERA_LIMITS["offset"][0], le=CAMERA_LIMITS["offset"][1])


class MosaicGrid(BaseModel):
    target: str = Field(min_length=1, max_length=40)
    rows: int = Field(default=2, ge=1, le=6)
    cols: int = Field(default=2, ge=1, le=6)
    overlap: float = Field(default=0.15, ge=0.05, le=0.5)


class BodyGoto(Command):
    body: str = Field(min_length=1, max_length=12)
    filter_confirmed: bool = False


class DeviceName(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class Role(BaseModel):
    role: Literal["owner", "operator", "viewer"]


class Invite(BaseModel):
    role: Literal["owner", "operator", "viewer"] = "operator"
    minutes: int = Field(default=5, ge=1, le=30)


class Planetary(Command):
    """Captura planetária: `frames` quadros curtos, dos quais ficam os `keep_percent`% mais
    nítidos. `point`: apontar e centralizar antes de gravar."""
    body: str = Field(min_length=1, max_length=12)
    frames: int = Field(default=300, ge=50, le=3000)
    keep_percent: int = Field(default=15, ge=5, le=50)
    point: bool = True


class PolarAdjust(BaseModel):
    alt_arcmin: float = Field(ge=-600, le=600)
    az_arcmin: float = Field(ge=-600, le=600)


class NetJoin(BaseModel):
    ssid: str = Field(min_length=1, max_length=32)
    # senha de WiFi tem de 8 a 63 caracteres; sem ela, só rede aberta ou já guardada
    psk: str | None = Field(default=None, min_length=8, max_length=63)

    @field_validator("ssid")
    @classmethod
    def _real_name(cls, value: str) -> str:
        if not value.strip() or len(value.encode("utf-8")) > 32:   # o limite do WiFi é em bytes
            raise ValueError("nome de rede inválido")
        return value


class NetMode(BaseModel):
    mode: Literal["home", "field"]


class NetHotspot(BaseModel):
    psk: str = Field(min_length=8, max_length=63)


# ---------------------------------------------------------------- utilitários
def _bearer(header: str | None) -> str | None:
    if header and header.lower().startswith("bearer "):
        return header[7:].strip()
    return None


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


class BodyLimit:
    """Recusa corpo grande antes de qualquer outra coisa. As rotas de pareamento são abertas:
    sem isto, qualquer um na rede poderia encher a memória da Jetson mandando um corpo enorme."""

    def __init__(self, app, max_bytes: int = MAX_BODY_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            return await _error(413, "payload_too_large", "corpo grande demais")(scope, receive, send)
        seen = 0

        async def limited():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:                # corpo em pedaços, sem tamanho declarado
                    raise StarletteHTTPException(413, "corpo grande demais")
            return message

        await self.app(scope, limited, send)


# ----------------------------------------------------------------- aplicação
def create_app(ctx: ApiContext) -> FastAPI:
    # sem páginas de documentação: elas buscam arquivos na internet, e o aparelho vive sem ela
    app = FastAPI(title="API do telescópio", version=str(API_VERSION),
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    app.add_middleware(BodyLimit)

    # ---- erros: um formato só ----
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError):
        return _error(e.status, e.code, e.message)

    @app.exception_handler(PairingError)
    async def _pairing_error(_: Request, e: PairingError):
        status = {"invalid_argument": 400, "pairing_locked": 429, "last_owner": 409}.get(e.code, 403)
        return _error(status, e.code, str(e))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        first = e.errors()[0] if e.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path"))
        return _error(400, "invalid_argument", f"{where}: {first.get('msg', 'entrada inválida')}")

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed",
                413: "payload_too_large"}.get(e.status_code, "error")
        return _error(e.status_code, code, str(e.detail))

    # ---- quem é ----
    def auth(request: Request) -> Client:
        client = ctx.pairing.authenticate(_bearer(request.headers.get("authorization")))
        if client is None:
            raise ApiError(401, "unauthorized", "pareie o celular com o telescópio")
        return client

    def at_least(role: str):
        def dep(client: Client = Depends(auth)) -> Client:
            if _RANK.get(client.role, -1) < _RANK[role]:
                raise ApiError(403, "forbidden", f"esta ação exige o papel {role}")
            return client
        return dep

    operator, owner = at_least("operator"), at_least("owner")

    # ---- aparelho ----
    @app.get("/api/v1/info")
    def info():
        from ..backend import backend_name
        return {"id": ctx.identity.device_id, "name": ctx.name, "api": API_VERSION,
                "software": __version__,
                "capabilities": {
                    # `mount`: o LINK com a montagem (real por INDI, ou nenhum). `goto`: quem
                    # executa o apontamento hoje — ainda o simulador, mesmo com a montagem real.
                    "mount": "indi" if ctx.mount_link is not None else "sim",
                    "goto": "sim", "camera": "sim", "focuser": "sim", "filter_wheel": False,
                    "modes": list(MODES), "gpu": backend_name()},
                "clock": {"utc": ctx.site.now().strftime(_ISO), "synced": ctx.site.source == "phone"},
                "site": ctx.site.as_dict(), "pairing_open": ctx.pairing.window_open}

    @app.post("/api/v1/pair/start")
    def pair_start(body: PairStart):
        nonce, ttl = ctx.pairing.start(body.client_name)
        return {"nonce": nonce, "expires_s": ttl}

    @app.post("/api/v1/pair/finish")
    def pair_finish(body: PairFinish):
        try:
            token, client = ctx.pairing.finish(body.client_name, body.proof)
        except PairingError as e:
            ctx.audit.record(body.client_name, "pair_failed", code=e.code)
            raise
        ctx.audit.record(client.name, "pair", client_id=client.id)
        return {"token": token, "client_id": client.id, "role": client.role,
                "device_id": ctx.identity.device_id}

    @app.get("/api/v1/clients")
    def clients(me: Client = Depends(owner)):
        return {"items": [dict(c.public(), current=(c.id == me.id)) for c in ctx.pairing.clients()]}

    @app.delete("/api/v1/clients/{client_id}")
    def revoke(client_id: str, me: Client = Depends(owner)):
        if not ctx.pairing.revoke(client_id):
            raise ApiError(404, "not_found", "celular não encontrado")
        ctx.audit.record(me.name, "revoke", client_id=client_id)
        return {"revoked": client_id}

    @app.patch("/api/v1/clients/{client_id}")
    def set_role(client_id: str, body: Role, me: Client = Depends(owner)):
        if not ctx.pairing.set_role(client_id, body.role):
            raise ApiError(404, "not_found", "celular não encontrado")
        ctx.audit.record(me.name, "role", client_id=client_id, role=body.role)
        return {"id": client_id, "role": body.role}

    @app.post("/api/v1/clients/invite")
    def invite(body: Invite, request: Request, me: Client = Depends(owner)):
        """Um dono convida outro celular: sorteia um segredo de USO ÚNICO, com o papel escolhido,
        e devolve o código para mostrar na tela do dono. O segredo do aparelho não sai daqui. O
        endereço que vai no código é o mesmo por onde este dono está falando com o aparelho."""
        seconds = body.minutes * 60
        secret = ctx.pairing.invite(seconds=seconds, role=body.role)
        uri = ctx.identity.pairing_uri(port=request.url.port or 443, host=request.url.hostname,
                                       secret=secret)
        ctx.audit.record(me.name, "invite", role=body.role, minutes=body.minutes)
        return {"uri": uri, "role": body.role, "expires_s": seconds,
                "qr_svg": ctx.qr_svg(uri) if ctx.qr_svg else None}

    @app.put("/api/v1/device")
    def rename(body: DeviceName, me: Client = Depends(owner)):
        name = " ".join(body.name.split())
        if not name or not all(ch.isprintable() for ch in name):
            raise ApiError(400, "invalid_argument", "name: use um nome com letras ou números")
        ctx.name = name
        if ctx.save_name:
            ctx.save_name(name)
        ctx.audit.record(me.name, "rename", name=name)
        return {"name": name}

    @app.post("/api/v1/site")
    def site(body: Site, me: Client = Depends(operator)):
        if body.utc.tzinfo is None:
            raise ApiError(400, "invalid_argument", "utc: informe o fuso (termine com Z)")
        ctx.site.set_from_phone(body.utc, body.lat, body.lon, body.elev_m)
        sent = False
        if ctx.mount_link is not None:
            sent = bool(ctx.mount_link.update_site((body.lat, body.lon, body.elev_m), now=ctx.site.now))
        ctx.audit.record(me.name, "site", lat=round(body.lat, 3), lon=round(body.lon, 3))
        return {"clock_set": True, "clock_offset_s": round(ctx.site.offset_s, 3), "mount_updated": sent}

    @app.get("/api/v1/state")
    def state(_: Client = Depends(auth)):
        return build_state(ctx)

    @app.get("/api/v1/mount")
    def mount(_: Client = Depends(auth)):
        return build_state(ctx)["mount"]

    # ---- montagem à mão ----
    def _manual_mount(need_idle: bool = True) -> dict:
        """O estado do Controller, para mexer na montagem à mão. Hoje isso só existe na
        montagem SIMULADA: a real ainda não é comandada pela API (a mecânica não está montada,
        e movimento sem validar na bancada não se libera)."""
        if ctx.mount_link is not None:
            raise ApiError(501, "not_supported", "mover a montagem real pelo app ainda não existe")
        _, st = ctx.hub.get()
        if need_idle and (st.get("state") or "IDLE") in BUSY_STATES:
            raise ApiError(409, "busy", "pare o trabalho em andamento antes de mexer na montagem")
        return st

    motion_seen: dict[str, float] = {}

    def _audit_motion(me: Client, **detail) -> None:
        """O movimento manual chega em rajada (o app renova o comando): registra o começo."""
        now = time.monotonic()
        if now - motion_seen.get(me.id, -1e9) > 10.0:
            ctx.audit.record(me.name, "mount_slew", **detail)
        motion_seen[me.id] = now

    @app.post("/api/v1/mount/slew")
    def mount_slew(body: Jog, me: Client = Depends(operator)):
        st = _manual_mount()
        if (st.get("mount_ctl") or {}).get("parked"):
            raise ApiError(409, "parked", "a montagem está estacionada")
        ctx.submit(f"mount:jog:{body.dir}:{body.rate}:{body.hold_ms}", None)
        _audit_motion(me, dir=body.dir, rate=body.rate)
        return {"moving": body.dir, "rate": body.rate, "hold_ms": body.hold_ms}

    @app.post("/api/v1/mount/stop")
    def mount_stop(_: Client = Depends(operator)):
        ctx.submit("mount:halt", None)               # parar nunca é recusado
        return {"moving": None}

    @app.post("/api/v1/mount/tracking")
    def mount_tracking(body: Tracking, me: Client = Depends(operator)):
        st = _manual_mount(need_idle=False)
        if (st.get("mount_ctl") or {}).get("parked"):
            raise ApiError(409, "parked", "a montagem está estacionada")
        ctx.submit("mount:tracking:" + ("on" if body.on else "off"), None)
        ctx.audit.record(me.name, "mount_tracking", on=body.on)
        return {"tracking": body.on}

    @app.post("/api/v1/mount/{action}")
    def mount_action(action: str, me: Client = Depends(operator)):
        if action not in ("park", "unpark", "home"):
            raise ApiError(404, "not_found", "ação desconhecida")
        _manual_mount(need_idle=action != "unpark")
        ctx.submit(f"mount:{action}", None)
        ctx.audit.record(me.name, f"mount_{action}")
        return {"accepted": action}

    # ---- foco e câmera ----
    @app.get("/api/v1/focuser")
    def focuser(_: Client = Depends(auth)):
        return build_state(ctx)["focus"]

    @app.post("/api/v1/focuser")
    def focuser_move(body: FocusMove, me: Client = Depends(operator)):
        if (body.delta is None) == (body.position is None):
            raise ApiError(400, "invalid_argument", "informe delta OU position")
        _, st = ctx.hub.get()
        if (st.get("state") or "IDLE") == "FOCUSING":
            raise ApiError(409, "busy", "o autofoco está rodando")
        lo, hi = st.get("focus_range") or [None, None]
        want = int(st.get("focus_pos") or 0) + body.delta if body.delta is not None else body.position
        clamped = want if lo is None else max(int(lo), min(int(hi), want))
        ctx.submit(f"focus:move:{body.delta}" if body.delta is not None else f"focus:goto:{body.position}", None)
        return {"position": clamped, "at_limit": clamped != want}      # at_limit: fim de curso

    @app.get("/api/v1/camera")
    def camera(_: Client = Depends(auth)):
        return dict(build_state(ctx)["camera"], limits={k: list(v) for k, v in CAMERA_LIMITS.items()})

    @app.post("/api/v1/camera")
    def camera_set(body: CameraSet, me: Client = Depends(operator)):
        changed = {k: v for k, v in body.model_dump().items() if v is not None}
        for key, value in changed.items():
            setattr(ctx.camera, key, value)
        if changed:
            ctx.audit.record(me.name, "camera", **changed)
        return dict(build_state(ctx)["camera"], limits={k: list(v) for k, v in CAMERA_LIMITS.items()})

    # ---- rede ----
    def _net():
        """A porta da rede, ou 501: trocar de rede pelo app só é ligado no aparelho depois de
        testado na bancada (uma troca malfeita corta o acesso a ele)."""
        if ctx.network is None:
            raise ApiError(501, "not_enabled", "trocar de rede pelo app não está habilitado neste aparelho")
        return ctx.network

    def _net_call(fn, *args):
        try:
            return fn(*args)
        except NetworkError as e:
            status = {"not_found": 404, "invalid_argument": 400}.get(e.code, 409)
            raise ApiError(status, e.code, str(e)) from None

    @app.get("/api/v1/network")
    def network(request: Request, me: Client = Depends(auth)):
        """Como o aparelho está na rede. `enabled` diz se dá para trocar por aqui. A senha do
        WiFi próprio só vai para o dono."""
        server = request.scope.get("server") or (None, None)
        base = {"hostname": socket.gethostname(), "address": server[0], "port": server[1]}
        if ctx.network is None:
            return dict(base, enabled=False, mode="unknown", wifi=None, hotspot=None, known=[],
                        last_error=None, switching=False)
        return dict(base, **ctx.network.status(owner=me.role == "owner"))

    @app.get("/api/v1/network/scan")
    def network_scan(_: Client = Depends(owner)):
        """As redes que o TELESCÓPIO enxerga (não o celular): é nelas que ele pode entrar."""
        return {"items": _net_call(_net().scan)}

    @app.post("/api/v1/network/join")
    def network_join(body: NetJoin, me: Client = Depends(owner)):
        net = _net()
        ctx.audit.record(me.name, "network_join", ssid=body.ssid)       # a senha nunca vai ao registro
        return _net_call(net.join, body.ssid, body.psk)

    @app.post("/api/v1/network/mode")
    def network_mode(body: NetMode, me: Client = Depends(owner)):
        net = _net()
        ctx.audit.record(me.name, "network_mode", mode=body.mode)
        return _net_call(net.set_mode, body.mode)

    @app.post("/api/v1/network/hotspot")
    def network_hotspot(body: NetHotspot, me: Client = Depends(owner)):
        net = _net()
        ctx.audit.record(me.name, "network_hotspot_password")
        return _net_call(net.set_hotspot_psk, body.psk)

    @app.delete("/api/v1/network/known/{ssid}")
    def network_forget(ssid: str, me: Client = Depends(owner)):
        net = _net()
        ctx.audit.record(me.name, "network_forget", ssid=ssid[:32])
        return _net_call(net.forget, ssid)

    # ---- sistema ----
    @app.get("/api/v1/system")
    def system(_: Client = Depends(auth)):
        return dict(system_info(), software=__version__, api=API_VERSION,
                    device_id=ctx.identity.device_id, power=ctx.power is not None,
                    uptime_s=int(time.monotonic() - ctx.started),
                    # o firmware da montagem ainda não é lido
                    firmware=None, update={"enabled": ctx.updater is not None})

    @app.get("/api/v1/system/update")
    def update_status(_: Client = Depends(auth)):
        if ctx.updater is None:
            return {"enabled": False, "current": __version__, "available": None, "state": "idle",
                    "progress": None, "error": None}
        return ctx.updater.status()

    @app.post("/api/v1/system/update/{action}")
    def update_action(action: str, me: Client = Depends(owner)):
        if action not in ("check", "install"):
            raise ApiError(404, "not_found", "ação desconhecida")
        if ctx.updater is None:
            raise ApiError(501, "not_enabled", "atualizar pelo app não está habilitado neste aparelho")
        if action == "install" and (ctx.hub.get()[1].get("state") or "IDLE") not in ("IDLE", "STOPPED", "ERROR"):
            raise ApiError(409, "busy", "pare o trabalho em andamento antes de atualizar")
        try:
            getattr(ctx.updater, action)()
        except UpdateError as e:
            raise ApiError(409, e.code, str(e)) from None
        ctx.audit.record(me.name, f"update_{action}")
        return ctx.updater.status()

    @app.post("/api/v1/system/{action}")
    def power(action: str, me: Client = Depends(owner)):
        if action not in ("shutdown", "restart"):
            raise ApiError(404, "not_found", "ação desconhecida")
        if ctx.power is None:
            raise ApiError(501, "not_enabled", "desligar pelo app não está habilitado neste aparelho")
        ctx.audit.record(me.name, action)
        ctx.power(action)
        return {"accepted": action}

    @app.get("/api/v1/logs")
    def logs(limit: int = Query(50, ge=1, le=200), _: Client = Depends(owner)):
        return {"items": ctx.audit.recent(limit)}

    @app.get("/api/v1/openapi.json")
    def openapi(_: Client = Depends(auth)):
        return app.openapi()

    # ---- céu ----
    @app.get("/api/v1/targets")
    def targets(q: str = Query("", max_length=60), type: str = Query("", max_length=10),
                visible: bool = False, fits: bool = False,
                limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000),
                _: Client = Depends(auth)):
        if type and type not in sky.TYPES:
            raise ApiError(400, "invalid_argument", f"type: use um de {', '.join(sky.TYPES)}")
        return sky.list_targets(ctx.site.lat, ctx.site.lon, ctx.site.now(), q=q, type_=type,
                                visible=visible, fits=fits, limit=limit, offset=offset)

    @app.get("/api/v1/targets/{target_id}")
    def target(target_id: str, _: Client = Depends(auth)):
        d = sky.target_detail(target_id, ctx.site.lat, ctx.site.lon, ctx.site.now())
        if d is None:
            raise ApiError(404, "not_found", "alvo fora do catálogo")
        return d

    def _jpeg(data: bytes | None, what: str, cache: str = "max-age=60") -> Response:
        if not data:
            raise ApiError(404, "not_found", f"sem {what}")
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": cache})

    @app.get("/api/v1/targets/{target_id}/thumb")
    def target_thumb(target_id: str, _: Client = Depends(auth)):
        obj = sky.find(target_id)
        key = sky.thumb_key(obj) if obj is not None else None
        return _jpeg(ctx.image_jpeg(key, True) if (key and ctx.image_jpeg) else None, "miniatura")

    # ---- observar ----
    def _command(me: Client, cmd_id: str, kind: str, command: str, target: str | None = None) -> dict:
        def action(job_id: str) -> None:
            ctx.audit.record(me.name, kind, job=job_id, **({"target": target} if target else {}))
            ctx.submit(command, job_id)
        return ctx.jobs.run(cmd_id, kind, action, target=target)

    @app.post("/api/v1/observe/goto")
    def goto(body: Goto, me: Client = Depends(operator)):
        if body.target:
            tid = sky.resolve_id(body.target)
            if tid is None:
                raise ApiError(404, "not_found", "alvo fora do catálogo")
            return _command(me, body.id, "goto", f"start:goto:{tid}", target=tid)
        if body.ra_deg is None or body.dec_deg is None:
            raise ApiError(400, "invalid_argument", "informe target, ou ra_deg e dec_deg")
        return _command(me, body.id, "goto", f"start:goto:@{body.ra_deg:.5f},{body.dec_deg:.5f}",
                        target=f"{body.ra_deg:.3f}, {body.dec_deg:+.3f}")

    @app.post("/api/v1/observe/target")
    def observe_target(body: Goto, me: Client = Depends(operator)):
        """A "noite rápida": aponta, centraliza e, se deu certo, empilha até alguém parar. É um
        comando só para a sequência seguir na Jetson mesmo que o celular perca o sinal."""
        tid = sky.resolve_id(body.target) if body.target else None
        if tid is None:
            raise ApiError(404 if body.target else 400, "not_found" if body.target else "invalid_argument",
                           "alvo fora do catálogo" if body.target else "informe target")
        return _command(me, body.id, "observe", f"start:observe:{tid}", target=tid)

    @app.post("/api/v1/observe/stack")
    def stack(body: Stack, me: Client = Depends(operator)):
        job = _command(me, body.id, "stack", "start:stack")
        # a câmera é simulada: estes parâmetros ainda não chegam a lugar nenhum — dizer isso
        job["ignored"] = [k for k, on in (("exposure_s", body.exposure_s is not None),
                                          ("gain", body.gain is not None),
                                          ("frames", body.frames > 0)) if on]
        return job

    @app.post("/api/v1/observe/run")
    def run(body: Run, me: Client = Depends(operator)):
        if body.mode not in RUN_MODES:
            raise ApiError(400, "invalid_argument", f"mode: use um de {', '.join(RUN_MODES)}")
        target = None
        if body.target:                              # só nomes simples chegam ao Controller
            if not body.target.replace(" ", "").isalnum():
                raise ApiError(400, "invalid_argument", "target: use o nome do alvo (ex.: M31)")
            target = body.target.replace(" ", "")
        return _command(me, body.id, body.mode, f"start:{body.mode}" + (f":{target}" if target else ""),
                        target=target)

    @app.post("/api/v1/observe/stop")
    def stop(body: Command, me: Client = Depends(operator)):
        return _command(me, body.id, "stop", "stop")

    @app.post("/api/v1/observe/preview")
    def observe_preview(body: Command, me: Client = Depends(operator)):
        """A câmera ao vivo, sem apontar e sem empilhar: enquadrar e focar à mão."""
        return _command(me, body.id, "preview", "start:preview")

    @app.post("/api/v1/observe/focus")
    def observe_focus(body: Command, me: Client = Depends(operator)):
        """Autofoco: varre o focalizador e vai ao foco crítico. A curva chega em `focus`."""
        return _command(me, body.id, "focus", "start:focus")

    # ---- Lua, planetas e Sol ----
    @app.get("/api/v1/solar")
    def solar(_: Client = Depends(auth)):
        return {"items": ephem.bodies(ctx.site.lat, ctx.site.lon, ctx.site.now())}

    @app.post("/api/v1/observe/body")
    def observe_body(body: BodyGoto, me: Client = Depends(operator)):
        """Aponta para a Lua, um planeta ou o Sol. O Sol só com a confirmação do filtro: sem
        ele, o sensor (e o olho de quem espiar) não sobrevive."""
        names = {i: n for i, n, _ in ephem.BODIES}
        if body.body not in names:
            raise ApiError(404, "not_found", "corpo desconhecido")
        if body.body == "sun" and not body.filter_confirmed:
            raise ApiError(400, "solar_filter_required", "confirme que o filtro solar está na frente")
        ra, dec = ephem.body_radec(body.body, ctx.site.now())
        if body.body == "sun":
            ctx.audit.record(me.name, "sun_filter_confirmed")
        return _command(me, body.id, "goto", f"start:goto:@{ra:.5f},{dec:.5f}", target=names[body.body])

    @app.post("/api/v1/observe/planetary")
    def observe_planetary(body: Planetary, me: Client = Depends(operator)):
        """Captura planetária (Lua e planetas): muitos quadros curtos, dos quais só os mais
        nítidos são empilhados. O andamento chega em `capture`."""
        names = {i: n for i, n, _ in ephem.BODIES}
        if body.body not in PLANETARY_BODIES:
            raise ApiError(404, "not_found", "corpo desconhecido para a captura planetária")
        spec = f"start:planetary:{body.body}|{body.frames}|{body.keep_percent}"
        if body.point:
            ra, dec = ephem.body_radec(body.body, ctx.site.now())
            spec += f"|{ra:.5f}|{dec:.5f}"
        return _command(me, body.id, "planetary", spec, target=names[body.body])

    # ---- alinhamento polar ----
    @app.post("/api/v1/observe/polar")
    def observe_polar(body: Command, me: Client = Depends(operator)):
        """Mede o erro do eixo polar em três pontos. O resultado chega em `polar`. Como o resto
        do apontamento, hoje é feito com a montagem simulada."""
        known = ctx.jobs.known(body.id)
        if known is not None:                        # reenvio (o sinal caiu): o mesmo trabalho, e não
            return known                             # "ocupado" por causa da própria medida
        _manual_mount()
        return _command(me, body.id, "polar", "start:polar")

    @app.post("/api/v1/mount/polar/adjust")
    def polar_adjust(body: PolarAdjust, me: Client = Depends(operator)):
        """Os parafusos da montagem SIMULADA (na real, quem gira os parafusos é a pessoa). A
        medida anterior deixa de valer: é preciso medir de novo."""
        _manual_mount()
        ctx.submit(f"polar:adjust:{body.alt_arcmin:.3f}:{body.az_arcmin:.3f}", None)
        ctx.audit.record(me.name, "polar_adjust", alt_arcmin=body.alt_arcmin, az_arcmin=body.az_arcmin)
        return {"adjusted": True}

    # ---- plano da noite e mosaico ----
    def _plan_running() -> bool:
        job = ctx.jobs.observe(ctx.hub.get()[1])
        return bool(job and job["kind"] == "plan" and job["state"] in ("accepted", "running"))

    def _plan_view() -> dict:
        view = planning.schedule(ctx.plan.items(), ctx.site.lat, ctx.site.lon, ctx.site.now())
        view["running"] = _plan_running()
        return view

    @app.get("/api/v1/plan")
    def plan_get(_: Client = Depends(auth)):
        return _plan_view()

    @app.put("/api/v1/plan")
    def plan_put(body: dict, me: Client = Depends(operator)):
        """Troca a fila inteira (é assim que se reordena). Com a noite rodando, não."""
        if _plan_running():
            raise ApiError(409, "busy", "pare a noite antes de mudar o plano")
        try:
            items = planning.normalize(body.get("items"))
        except ValueError as e:
            raise ApiError(400, "invalid_argument", str(e)) from None
        ctx.plan.replace(items)
        ctx.audit.record(me.name, "plan", items=len(items))
        return _plan_view()

    @app.post("/api/v1/plan/start")
    def plan_start(body: Command, me: Client = Depends(operator)):
        if not ctx.plan.items():
            raise ApiError(400, "invalid_argument", "o plano está vazio")
        return _command(me, body.id, "plan", "start:plan")

    @app.post("/api/v1/plan/skip")
    def plan_skip(me: Client = Depends(operator)):
        if not _plan_running():
            raise ApiError(409, "not_running", "não há noite em andamento")
        ctx.submit("skip", None)
        ctx.audit.record(me.name, "plan_skip")
        return {"skipped": True}

    @app.post("/api/v1/plan/stop")
    def plan_stop(body: Command, me: Client = Depends(operator)):
        return _command(me, body.id, "stop", "stop")

    @app.post("/api/v1/mosaic")
    def mosaic(body: MosaicGrid, _: Client = Depends(auth)):
        """A grade de painéis sobre um alvo. Só calcula; para fotografar, o item entra no
        plano com `mosaic: [linhas, colunas]`."""
        grid = planning.mosaic(body.target, body.rows, body.cols, body.overlap)
        if grid is None:
            raise ApiError(404, "not_found", "alvo fora do catálogo")
        return grid

    def _sized(jpeg: bytes | None, max_side: int) -> bytes | None:
        """`max_side` > 0: o quadro reduzido para a tela do celular (o cheio passa de 1 MB)."""
        return ctx.shrink(jpeg, max_side) if (jpeg and max_side and ctx.shrink) else jpeg

    @app.get("/api/v1/frame.jpg")
    def frame(max_side: int = Query(0, ge=0, le=4096), _: Client = Depends(auth)):
        jpeg, _stats = ctx.hub.get()
        return _jpeg(_sized(jpeg, max_side), "imagem ao vivo", cache="no-store")

    @app.get("/api/v1/preview.mjpg")
    def preview(request: Request, max_side: int = Query(0, ge=0, le=4096), _: Client = Depends(auth)):
        token = _bearer(request.headers.get("authorization"))

        def frames():
            version, last = -1, None
            while ctx.pairing.authenticate(token) is not None:      # revogado: a imagem para
                version = ctx.hub.wait_change(version, 1.0)
                jpeg, _stats = ctx.hub.get()
                if jpeg and jpeg is not last:
                    last = jpeg
                    jpeg = _sized(jpeg, max_side)
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                           + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
        return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/histogram")
    def histogram(_: Client = Depends(auth)):
        return {"bins": ctx.histogram() if ctx.histogram else []}

    # ---- galeria e estúdio ----
    def _session(session_id: str) -> dict:
        for s in (ctx.sessions() if ctx.sessions else []):
            if s["id"] == session_id:
                return s
        raise ApiError(404, "not_found", "sessão não encontrada")

    @app.get("/api/v1/sessions")
    def sessions(_: Client = Depends(auth)):
        return {"items": ctx.sessions() if ctx.sessions else []}

    @app.get("/api/v1/sessions/{session_id}")
    def session(session_id: str, _: Client = Depends(auth)):
        return _session(session_id)

    @app.get("/api/v1/sessions/{session_id}/image")
    def session_image(session_id: str, thumb: bool = False, _: Client = Depends(auth)):
        _session(session_id)
        return _jpeg(ctx.image_jpeg(session_id, thumb) if ctx.image_jpeg else None, "imagem")

    @app.get("/api/v1/sessions/{session_id}/export")
    def session_export(session_id: str, format: str = Query("jpg", pattern="^(jpg|tif|fits)$"),
                       max_side: int = Query(0, ge=0, le=20000), me: Client = Depends(auth)):
        """O resultado para levar: JPEG (para mostrar), TIFF de 16 bits ou o FITS linear (para
        processar em outro programa). `max_side` reduz JPEG e TIFF; 0 = tamanho cheio."""
        _session(session_id)
        if ctx.export_session is None:
            raise ApiError(501, "not_supported", "exportar ainda não existe neste aparelho")
        out = ctx.export_session(session_id, format, max_side)
        if out is None:
            raise ApiError(404, "not_found", "sem imagem para exportar")
        data, media, name = out
        ctx.audit.record(me.name, "export", session=session_id, format=format)
        headers = {"Cache-Control": "no-store", "Content-Disposition": f'attachment; filename="{name}"'}
        if isinstance(data, (bytes, bytearray)):
            return Response(bytes(data), media_type=media, headers=headers)
        return FileResponse(str(data), media_type=media, headers=headers)     # arquivo grande: em pedaços

    @app.delete("/api/v1/sessions/{session_id}")
    def session_delete(session_id: str, me: Client = Depends(owner)):
        found = _session(session_id)
        if found.get("source") == "reference":
            raise ApiError(409, "protected", "as imagens de referência não são apagadas pelo app")
        if ctx.delete_session is None or not ctx.delete_session(session_id):
            raise ApiError(501, "not_supported", "apagar sessões ainda não existe neste aparelho")
        ctx.audit.record(me.name, "session_delete", session=session_id)
        return {"deleted": session_id}

    @app.post("/api/v1/sessions/{session_id}/render")
    def session_render(session_id: str, body: dict, _: Client = Depends(auth)):
        _session(session_id)
        if len(body) > 40 or not all(isinstance(v, (bool, int, float, str)) for v in body.values()):
            raise ApiError(400, "invalid_argument", "controles: use números, verdadeiro/falso ou texto")
        try:
            data = ctx.render_session(session_id, body) if ctx.render_session else None
        except ValueError as e:
            raise ApiError(400, "invalid_argument", str(e)) from None
        return _jpeg(data, "render", cache="no-store")

    @app.get("/api/v1/render/presets")
    def presets(_: Client = Depends(auth)):
        return ctx.presets() if ctx.presets else {"presets": {}, "controls": {}}

    # ---- canal em tempo real ----
    @app.websocket("/api/v1/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        token = _bearer(websocket.headers.get("authorization"))
        if ctx.pairing.authenticate(token) is None:
            try:                                 # quem não manda cabeçalho autentica na 1ª mensagem
                first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                token = first.get("auth") if isinstance(first, dict) else None
            except Exception:
                token = None
        client = ctx.pairing.authenticate(token if isinstance(token, str) else None)
        if client is None:
            await websocket.close(code=4401)
            return

        async def push():
            seq, last, version = 0, None, -1
            while True:
                version = await anyio.to_thread.run_sync(ctx.hub.wait_change, version, 0.25)
                if ctx.pairing.authenticate(token) is None:      # revogado no meio da sessão
                    await websocket.close(code=4401)
                    return
                data = build_state(ctx)
                messages = state_messages(last, data)
                for kind, payload in messages:
                    seq += 1
                    await websocket.send_json({"seq": seq, "type": kind, "data": payload})
                last = data
                if messages:
                    await asyncio.sleep(0.1)                     # no máximo ~10 rajadas/s

        async def listen():
            while True:
                msg = await websocket.receive_json()
                if not isinstance(msg, dict) or not isinstance(msg.get("id"), str) or len(msg["id"]) > 64:
                    continue
                cmd, cid = msg.get("cmd"), msg["id"]
                if _RANK.get(client.role, -1) < _RANK["operator"]:
                    await websocket.send_json({"type": "error", "id": cid, "code": "forbidden"})
                elif cmd == "observe.stop":
                    job = await anyio.to_thread.run_sync(_command, client, cid, "stop", "stop")
                    await websocket.send_json({"type": "ack", "id": cid, **job})
                else:
                    await websocket.send_json({"type": "error", "id": cid, "code": "not_supported"})

        tasks = [asyncio.create_task(push()), asyncio.create_task(listen())]
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                t.result()
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            for t in tasks:
                t.cancel()

    return app
