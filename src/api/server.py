"""O servidor da API: junta as peças reais e as serve por TLS 1.3.

Este é o único módulo da API que conhece o resto do projeto (console, estúdio, render). As
rotas (`app.py`) recebem tudo por um `ApiContext`, então continuam testáveis sem GPU nem rede.
"""
from __future__ import annotations

import os
import re
import socket
import sys
import threading
import time
from dataclasses import asdict, replace

from .app import ApiContext, SiteClock, create_app
from .audit import AuditLog
from .identity import API_PORT, DeviceIdentity
from .pairing import PairingService
from .plan import PlanStore

# controles do estúdio: (mínimo, máximo, passo) — os mesmos limites da página do estúdio
RENDER_CONTROLS = {
    "stretch": (1.0, 30.0, 0.5), "black": (0.0, 0.3, 0.005), "white": (98.0, 100.0, 0.05),
    "gamma": (0.5, 2.5, 0.05), "scnr": (0.0, 1.0, 0.05), "saturation": (0.0, 3.0, 0.05),
    "r_gain": (0.5, 2.0, 0.02), "g_gain": (0.5, 2.0, 0.02), "b_gain": (0.5, 2.0, 0.02),
    "deconv": (0.0, 20.0, 1.0), "denoise": (0.0, 1.0, 0.05), "ldenoise": (0.0, 1.0, 0.05),
    "star_reduce": (0.0, 1.0, 0.05), "sharpen": (0.0, 1.0, 0.02),
}
RENDER_TOGGLES = ("remove_grad",)
_KIND = {"nebulosa": "nebula", "galaxia": "galaxy"}


# ------------------------------------------------------------ estúdio e galeria
def render_params(body: dict):
    """Controles vindos do app -> (RenderParams, resolução cheia?). Tudo conferido: nome,
    tipo e faixa. `ValueError` com o nome do campo quando algo não serve."""
    from ..postproc.render import PRESETS
    body = dict(body)
    preset = body.pop("preset", "natural")
    if preset not in PRESETS:
        raise ValueError(f"preset: use um de {', '.join(PRESETS)}")
    full = body.pop("full", False)
    if not isinstance(full, bool):
        raise ValueError("full: use verdadeiro ou falso")
    params = replace(PRESETS[preset])
    for name, value in body.items():
        if name in RENDER_TOGGLES:
            if not isinstance(value, bool):
                raise ValueError(f"{name}: use verdadeiro ou falso")
            setattr(params, name, value)
            continue
        limits = RENDER_CONTROLS.get(name)
        if limits is None:
            raise ValueError(f"{name}: controle desconhecido")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name}: use um número")
        if not limits[0] <= value <= limits[1]:              # também barra NaN
            raise ValueError(f"{name}: fora da faixa {limits[0]:g} a {limits[1]:g}")
        setattr(params, name, float(value))
    return params, full


def render_presets() -> dict:
    """Presets de um toque e os limites de cada controle: o app monta os controles daqui."""
    from ..postproc.render import PRESETS, RenderParams
    default = asdict(RenderParams())
    names = list(RENDER_CONTROLS) + list(RENDER_TOGGLES)
    return {"presets": {k: {n: asdict(p)[n] for n in names} for k, p in PRESETS.items()},
            "controls": {n: {"min": lo, "max": hi, "step": step, "default": default[n]}
                         for n, (lo, hi, step) in RENDER_CONTROLS.items()},
            "toggles": {n: {"default": default[n]} for n in RENDER_TOGGLES}}


def list_sessions() -> list[dict]:
    """O que há para rever. Hoje são os empilhamentos de REFERÊNCIA: dados reais de outros
    instrumentos, processados pelo nosso pipeline (`source: reference`). Quando a câmera
    chegar, as sessões do próprio telescópio entram aqui com `source: telescope`."""
    from ..server.studio import CATALOG
    out = []
    for key, meta in CATALOG.items():
        if not os.path.exists(meta["stack"]):
            continue
        minutes = re.search(r"(\d+)\s*min", meta["exp"])
        out.append({"id": key, "target": meta["name"], "type": _KIND.get(meta["kind"], "other"),
                    "frames": meta["subs"],
                    "integration_s": int(minutes.group(1)) * 60 if minutes else None,
                    "integration_approx": meta["exp"].strip().startswith("~"),
                    "camera": meta["cam"], "source": "reference", "has_fits": True})
    return out


class Shrinker:
    """Reduz o quadro ao vivo para a tela do celular. O quadro cheio (1600x1200) passa de 1 MB;
    no celular bastam ~1000 px. Guarda o último resultado: vários pedidos do mesmo quadro
    custam uma conta só."""

    def __init__(self, quality: int = 82):
        self.quality = quality
        self._lock = threading.Lock()
        self._src, self._side, self._out = None, 0, b""

    def __call__(self, jpeg: bytes, max_side: int) -> bytes:
        import cv2
        import numpy as np
        with self._lock:
            if self._src is jpeg and self._side == max_side:
                return self._out
            out = jpeg
            img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if img is not None:
                h, w = img.shape[:2]
                scale = max_side / max(h, w)
                if scale < 1.0:
                    small = cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))),
                                       interpolation=cv2.INTER_AREA)
                    ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, self.quality])
                    out = buf.tobytes() if ok else jpeg
            self._src, self._side, self._out = jpeg, max_side, out
            return out


def _resized(img, max_side: int):
    """A imagem com o lado maior em `max_side` (0 ou maior que ela: como está)."""
    import cv2
    h, w = img.shape[:2]
    if not max_side or max(h, w) <= max_side:
        return img
    scale = max_side / max(h, w)
    return cv2.resize(img, (max(1, round(w * scale)), max(1, round(h * scale))),
                      interpolation=cv2.INTER_AREA)


class _Studio:
    """O estúdio, criado só quando alguém pede um render (carrega os empilhamentos lineares),
    e com um render por vez: são pesados, e o celular manda vários ao arrastar um controle."""

    def __init__(self):
        self._studio = None
        self._lock = threading.Lock()

    def _get(self):
        if self._studio is None:
            from ..server.studio import Studio
            self._studio = Studio()
        return self._studio

    def render(self, session_id: str, body: dict) -> bytes | None:
        params, full = render_params(body)
        with self._lock:
            return self._get().render_jpeg(session_id, params, full=full)

    def export(self, session_id: str, fmt: str, max_side: int = 0):
        """O resultado para levar: (bytes ou caminho, tipo, nome do arquivo), ou None.

        `jpg`: a imagem tratada (preset natural), para mostrar. `tif`: 16 bits LINEAR (sem
        esticar), para processar em outro programa. `fits`: o empilhamento como está no
        disco — pode passar de 300 MB, por isso vai como arquivo, não pela memória."""
        import cv2
        import numpy as np
        from ..postproc.render import PRESETS, render
        from ..server.studio import CATALOG
        meta = CATALOG.get(session_id)
        if meta is None or not os.path.exists(meta["stack"]):
            return None
        if fmt == "fits":
            return meta["stack"], "application/fits", f"{session_id}.fits"
        with self._lock:
            studio = self._get()
            if not studio._ensure(session_id):
                return None
            linear = _resized(studio._full[session_id], max_side)
            if fmt == "jpg":
                rgb = render(linear, PRESETS["natural"])
                ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                                       [cv2.IMWRITE_JPEG_QUALITY, 95])
                return (buf.tobytes(), "image/jpeg", f"{session_id}.jpg") if ok else None
            lo, hi = float(np.min(linear)), float(np.percentile(linear, 99.999))
            scaled = np.clip((linear - lo) / max(hi - lo, 1e-9), 0.0, 1.0)
            ok, buf = cv2.imencode(".tif", cv2.cvtColor((scaled * 65535.0).astype(np.uint16),
                                                        cv2.COLOR_RGB2BGR))
            return (buf.tobytes(), "image/tiff", f"{session_id}.tif") if ok else None


def qr_svg(text: str) -> str | None:
    """O QR do convite, em SVG (o app só desenha). Sem a biblioteca, o app mostra o código."""
    try:
        import io

        import segno
    except ImportError:
        return None
    out = io.BytesIO()
    segno.make(text, error="m").save(out, kind="svg", scale=8, border=2, dark="#000", light="#fff",
                                     xmldecl=False, svgns=True, nl=False)
    return out.getvalue().decode("utf-8")


# ------------------------------------------------------------------ montagem
def build_context(hub, submit, mount_link=None, console=None, identity_dir=None,
                  site=None, name: str | None = None) -> ApiContext:
    """Liga a API às peças que já rodam no processo (as mesmas do console)."""
    identity = DeviceIdentity.load_or_create(identity_dir)
    if site is None:
        from ..control.mount_link import _parse_site
        site = mount_link.site if mount_link is not None else _parse_site(os.environ.get("TELE_SITE"))
    if console is None:
        from ..server.console import Console
        console = Console(hub, site=tuple(site[:2]), mount_link=mount_link)
    studio = _Studio()
    name_file = identity.directory / "name.txt"

    def saved_name() -> str | None:
        try:
            return name_file.read_text(encoding="utf-8").strip() or None
        except OSError:
            return None

    def save_name(value: str) -> None:
        name_file.write_text(value, encoding="utf-8")

    # Rede e atualização pelo app: só os adapters de MENTIRA existem, e só entram quando
    # pedidos (`TELE_NETWORK=sim`, `TELE_UPDATES=sim`) — é assim que as telas são testadas no
    # PC. No aparelho ficam desligados até haver o adapter de verdade, testado na bancada.
    network = updater = None
    if os.environ.get("TELE_NETWORK", "").strip().lower() == "sim":
        from .network import SimNetwork
        network = SimNetwork(hotspot_ssid=f"Telescopio-{identity.device_id[-4:]}")
    if os.environ.get("TELE_UPDATES", "").strip().lower() == "sim":
        from . import __version__
        from .updates import SimUpdater
        updater = SimUpdater(current=__version__)

    return ApiContext(
        identity=identity, pairing=PairingService(identity), hub=hub, submit=submit,
        mount_link=mount_link, site=SiteClock(*site), network=network, updater=updater,
        audit=AuditLog(identity.directory / "audit.jsonl"),
        # o nome que o dono deu pelo app vale mais que o da configuração
        name=saved_name() or name or os.environ.get("TELE_NAME", "Telescópio"),
        plan=PlanStore(identity.directory / "plan.json"),
        image_jpeg=console.image_jpeg, histogram=console.histogram, shrink=Shrinker(),
        sessions=list_sessions, render_session=studio.render, presets=render_presets,
        export_session=studio.export, save_name=save_name, qr_svg=qr_svg)


SERVICE_TYPE = "_telescope._tcp.local."


class Advertiser:
    """Anuncia a API na rede local (DNS-SD), para o app achar o aparelho sem saber o endereço.

    Na Jetson quem anuncia é o avahi (`scripts/jetson_setup_api.sh`); isto é para o PC de
    desenvolvimento, e usa o pacote `zeroconf` (livre). Sem ele, `start` devolve False e o
    resto segue: o endereço continua vindo no QR. O anúncio leva o identificador do aparelho
    (`id`); a confiança NÃO vem dele — quem responde tem de apresentar o certificado pareado."""

    def __init__(self, device_id: str, name: str, port: int, address: str | None = None):
        self.device_id, self.name, self.port, self.address = device_id, name, port, address
        self._zeroconf = self._info = None

    def start(self) -> bool:
        try:
            from zeroconf import ServiceInfo, Zeroconf
        except ImportError:
            return False
        if self.address is None:
            from .cli import lan_address
            self.address = lan_address()
        label = "".join(ch for ch in self.name if ch.isalnum() or ch in " -") or "Telescopio"
        self._info = ServiceInfo(
            SERVICE_TYPE, f"{label} {self.device_id}.{SERVICE_TYPE}",
            addresses=[socket.inet_aton(self.address)], port=self.port,
            properties={"id": self.device_id, "api": "1"},
            server=f"{self.device_id}.local.")
        self._zeroconf = Zeroconf()
        self._zeroconf.register_service(self._info)
        return True

    def stop(self) -> None:
        if self._zeroconf is not None:
            try:
                self._zeroconf.unregister_service(self._info)
            finally:
                self._zeroconf.close()
        self._zeroconf = self._info = None


class ApiServer:
    """A API na rede, numa thread: `https://` e `wss://` na mesma porta, só TLS 1.3, com o
    certificado do aparelho."""

    def __init__(self, ctx: ApiContext, host: str = "0.0.0.0", port: int = API_PORT):
        self.ctx, self.host, self.port = ctx, host, port
        self._server = None
        self._thread: threading.Thread | None = None

    def start(self, timeout: float = 15.0) -> "ApiServer":
        import uvicorn
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if sys.platform != "win32":              # no Windows deixaria dois processos na porta
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))        # porta ocupada falha AQUI, com erro claro
        self.port = sock.getsockname()[1]
        identity = self.ctx.identity
        config = uvicorn.Config(create_app(self.ctx), log_level="warning", access_log=False,
                                ssl_certfile=str(identity.cert_path), ssl_keyfile=str(identity.key_path),
                                lifespan="off", server_header=False, timeout_keep_alive=30)
        config.load()
        config.ssl = identity.ssl_context()      # o nosso contexto: mínimo TLS 1.3
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, kwargs={"sockets": [sock]},
                                        name="telescope-api", daemon=True)
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("a API não subiu (veja o erro acima)")
            time.sleep(0.02)
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._server = self._thread = None
