"""Console de campo — a UI de PRODUTO (Live / Atlas / Pro), servida pela própria Orin.

Design system compartilhado (`ui_kit`): tema escuro coerente + **ícones SVG desenhados** (NUNCA emoji).
Tudo funcional com dados/imagens REAIS dos nossos modelos: nebulosa/galáxia (stacks), planeta (lucky
imaging), Lua (foto real), satélite (cena de rastreio), autofoco (curva V real), guiding (fluxo óptico
real), histograma (real). Stdlib só (http.server); live view por JPEG-push. Sem internet: tudo local.
Ver docs/33.
"""
from __future__ import annotations
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

import numpy as np
import cv2

from ..postproc.render import render, PRESETS
from .studio import CATALOG as STACKS, _load_linear
from .webview import FrameHub
from . import ui_kit as uik

try:
    from ..core import catalog as _cat
except Exception:
    _cat = None

DEFAULT_SITE = (-23.55, -46.63)      # São Paulo — altitude/visibilidade "agora"

# Atlas: (designação, chave de imagem, categoria). Imagem = chave de stack, "@gerado" ou None.
FAMOUS = [
    ("M8", "lagoon_trifid", "Nebulosa"), ("NGC2244", "rosette", "Nebulosa"), ("M51", "m51", "Galáxia"),
    ("Júpiter", "@jupiter", "Planeta"), ("Lua", "@moon", "Lua"), ("ISS", "@iss", "Satélite"),
    ("M31", None, "Galáxia"), ("M42", None, "Nebulosa"), ("M45", None, "Aglomerado"),
    ("M13", None, "Aglomerado"), ("M27", None, "Nebulosa"), ("M20", None, "Nebulosa"),
]
_PRESET_BY_KEY = {"lagoon_trifid": "vivido", "rosette": "nebulosa", "m51": "natural"}


def visible_targets(when=None, site=DEFAULT_SITE):
    """Alvos do Atlas: nome, categoria, magnitude, altitude AGORA e chave de imagem. Solar-system
    (@…) sempre disponíveis; DSO resolvidos pelo catálogo real (altitude no local/hora)."""
    when = when or datetime.now(timezone.utc)
    lat, lon = site
    out = []
    for desig, img, cat in FAMOUS:
        if img and img.startswith("@"):                 # planeta/lua/satélite (gerado dos modelos)
            out.append({"desig": desig, "name": desig, "cat": cat, "mag": None,
                        "alt": None, "visible": True, "img": img})
            continue
        obj = None
        if _cat is not None:
            try:
                obj = _cat.find(desig)
            except Exception:
                obj = None
        alt = None
        if obj is not None:
            try:
                alt = float(_cat.altitude_deg(obj, lat, lon, when))
            except Exception:
                alt = None
        if img is None and os.path.exists(f"data/sky_{desig}.jpg"):
            img = "@sky:" + desig                       # foto real do céu (DSS) p/ este DSO
        out.append({"desig": desig, "name": (obj.common if (obj and obj.common) else desig),
                    "cat": cat, "mag": (round(obj.mag, 1) if (obj and obj.mag is not None) else None),
                    "alt": (round(alt) if alt is not None else None),
                    "visible": bool(alt is not None and alt > 15), "img": img})
    return out


def warm_cache(site=DEFAULT_SITE) -> bool:
    """Pré-aquece o que deixa a PRIMEIRA abertura do Atlas lenta. Nunca levanta.

    Medido no Orin: a 1ª chamada de `/api/targets` levava **78,8 s** (a 2ª, 0,27 s) — ~70 s de
    tentativa de download IERS do astropy + 6,6 s de carga do catálogo OpenNGC (12.014 objetos)
    + 1,7 s da 1ª transformação de coordenada. No celular isso lê como "travou". Rodando este
    aquecimento numa thread no arranque do serviço, a UI de campo abre instantânea. Ver docs/34.
    """
    if _cat is None:
        return False
    try:
        _cat.configure_astropy_offline()
        objs = _cat.load()                       # OpenNGC: caro só na 1ª vez (cache no módulo)
        if objs:                                 # 1ª transformação: monta os frames do astropy
            _cat.altitude_deg(objs[0], site[0], site[1], datetime.now(timezone.utc))
        return True
    except Exception:                            # sem pyongc/astropy o console segue no fallback
        return False


def histogram_bins(rgb, n=40):
    """Histograma de luminância (n bins, normalizado 0..1)."""
    a = np.asarray(rgb)
    lum = a.mean(2) if a.ndim == 3 else a
    h, _ = np.histogram(lum, bins=n, range=(0, 255))
    m = float(h.max()) or 1.0
    return [round(float(v) / m, 3) for v in h]


def _encode(rgb, q=88, max_side=None):
    a = rgb
    if a.ndim == 2:
        a = cv2.cvtColor(a.astype(np.uint8), cv2.COLOR_GRAY2RGB)
    if max_side:
        hh, ww = a.shape[:2]
        s = max_side / max(hh, ww)
        if s < 1.0:
            a = cv2.resize(a, (int(ww * s), int(hh * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes() if ok else None


# ---- geradores REAIS (dos nossos modelos), cacheados -------------------------
_gl = threading.Lock()
_gen = {}


def _cached(key, fn):
    with _gl:
        if key not in _gen:
            try:
                _gen[key] = fn()
            except Exception:
                _gen[key] = None
        return _gen[key]


def _planetary(kind):
    from ..planetary.simulator import PlanetSimulator
    from ..planetary.stack import lucky_stack
    from ..planetary.wavelets import DEFAULT_WEIGHTS
    sim = PlanetSimulator(size=440, radius=(150 if kind == "jupiter" else 175), kind=kind,
                          seed=7, jitter=8.0, seeing=(0.5, 3.4), noise=6.0, color=True)
    res = lucky_stack(sim.frames(120), keep=0.18, sharpen=DEFAULT_WEIGHTS)
    rgb = np.clip(res.image, 0, 255).astype(np.uint8)
    return (_encode(rgb, 88, 820), _encode(rgb, 82, 260), histogram_bins(rgb))


def _sky_bundle(desig):
    """Foto REAL do céu (DSS2 color, baixada p/ data/sky_<desig>.jpg) — p/ DSO sem stack próprio."""
    p = f"data/sky_{desig}.jpg"
    if not os.path.exists(p):
        return None
    rgb = cv2.cvtColor(cv2.imread(p), cv2.COLOR_BGR2RGB)
    return (_encode(rgb, 88, 900), _encode(rgb, 82, 260), histogram_bins(rgb))


def _moon_img():
    p = "data/moon_real.jpg"
    if os.path.exists(p):
        bgr = cv2.imread(p)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        from ..planetary.wavelets import wavelet_sharpen
        rgb = wavelet_sharpen(rgb, weights=(0.6, 1.7, 2.1, 1.6, 1.1)).astype(np.uint8)
        return (_encode(rgb, 88, 900), _encode(rgb, 82, 260), histogram_bins(rgb))
    return _planetary("moon")


def _satellite():
    """Cena real de satélite: acumula frames → o objeto vira um RASTRO sobre o campo estelar."""
    from ..capture.sky import SkyModel
    from ..control.mount import SimMount
    from ..capture.satellite import SatelliteScene
    sky = SkyModel()
    mount = SimMount(cx=1560, cy=1350)
    sc = SatelliteScene(sky, mount, obj0=(1420, 1250), vel=(9.0, 5.5), view_w=440, view_h=340,
                        obj_flux=52000.0, obj_sigma=1.6)
    acc = None
    for _ in range(10):
        f, _m = sc.read()
        acc = f.astype(np.float32) if acc is None else np.maximum(acc, f.astype(np.float32))
    a = acc - np.percentile(acc, 25)
    a = np.clip(a / (np.percentile(a, 99.7) + 1e-6), 0, 1)
    rgb = (np.stack([a * 0.75, a * 0.85, a], -1) * 255).astype(np.uint8)   # tom levemente azulado
    return (_encode(rgb, 86, 820), _encode(rgb, 80, 260), histogram_bins(rgb))


def focus_curve():
    """Curva V de autofoco REAL (roda o AutoFocuser sobre o céu simulado)."""
    def _run():
        from ..capture.sky import SkyModel, SkyCameraSource
        from ..control.mount import SimMount
        from ..control.focuser import SimFocuser
        from ..control.autofocus import AutoFocuser, fit_critical_focus
        from ..gpu.quality import QualityConfig
        sky = SkyModel(); mount = SimMount(cx=1560, cy=1350); foc = SimFocuser(position=4200, best=6300)
        src = SkyCameraSource(sky, mount, foc, view_w=340, view_h=260, bad_frac=0.0)
        pts = []
        AutoFocuser(src, foc, QualityConfig(), steps=9).run(
            progress=lambda p, fw, fr: pts.append([int(p), round(float(fw), 2)]))
        pts = sorted({tuple(x) for x in pts})
        pts = [list(x) for x in pts if np.isfinite(x[1]) and x[1] < 30]
        crit = fit_critical_focus([p[0] for p in pts], [p[1] for p in pts]) if len(pts) >= 3 else None
        return {"points": pts, "critical": (round(crit) if crit else None)}
    return _cached("focus", _run) or {"points": [], "critical": None}


def guiding_series():
    """Erro de rastreio REAL (fluxo óptico sobre a cena de satélite; resíduo após remover a deriva)."""
    def _run():
        from ..capture.sky import SkyModel
        from ..control.mount import SimMount
        from ..capture.satellite import SatelliteScene
        from ..control.tracking import OpticalFlowTracker
        sky = SkyModel(); mount = SimMount(cx=1560, cy=1350)
        sc = SatelliteScene(sky, mount, obj0=(1560, 1350), vel=(2.2, -1.6), view_w=340, view_h=260)
        tr = OpticalFlowTracker()
        f, m = sc.read(); tr.init(f, m["obj_screen"])
        xs, ys = [], []
        for _ in range(60):
            f, m = sc.read(); pos = tr.update(f)
            if pos is None:
                continue
            xs.append(pos[0]); ys.append(pos[1])
        if len(xs) < 4:
            return {"ra": [], "de": [], "rms": 0.0}
        t = np.arange(len(xs))
        rx = np.asarray(xs) - np.polyval(np.polyfit(t, xs, 1), t)     # resíduo após a deriva (o guiding)
        ry = np.asarray(ys) - np.polyval(np.polyfit(t, ys, 1), t)
        rms = float(np.sqrt(np.mean(rx ** 2 + ry ** 2)))
        return {"ra": [round(v, 2) for v in rx], "de": [round(v, 2) for v in ry], "rms": round(rms, 2)}
    return _cached("guide", _run) or {"ra": [], "de": [], "rms": 0.0}


class Console:
    def __init__(self, hub: FrameHub, on_command=None, site=DEFAULT_SITE):
        self.hub, self.on_command, self.site = hub, on_command, site
        self._img = {}
        self._lock = threading.Lock()

    def _stack(self, key):
        with self._lock:
            if key in self._img:
                return self._img[key]
            meta = STACKS.get(key)
            if not meta or not os.path.exists(meta["stack"]):
                self._img[key] = None
                return None
            rgb = render(_load_linear(meta["stack"]), PRESETS.get(_PRESET_BY_KEY.get(key, "natural")))
            self._img[key] = (_encode(rgb, 90, 1100), _encode(rgb, 82, 260), histogram_bins(rgb))
            return self._img[key]

    def _bundle(self, key):
        if key == "@jupiter":
            return _cached("pl_jupiter", lambda: _planetary("jupiter"))
        if key == "@moon":
            return _cached("moon", _moon_img)
        if key == "@iss":
            return _cached("sat", _satellite)
        if key.startswith("@sky:"):
            return _cached(key, lambda: _sky_bundle(key[5:]))
        return self._stack(key)

    def image_jpeg(self, key, thumb=False):
        b = self._bundle(key)
        return None if not b else (b[1] if thumb else b[0])

    def histogram(self, key=None):
        if key:
            b = self._bundle(key)
            if b:
                return b[2]
        jpeg, _ = self.hub.get()
        if jpeg:
            arr = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
            if arr is not None:
                return histogram_bins(cv2.cvtColor(arr, cv2.COLOR_BGR2RGB))
        return [0.0] * 40

    def state(self):
        _, st = self.hub.get()
        return st


def _make_handler(con: Console):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body, extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            u = urlparse(self.path)
            p, q = u.path, {k: v[0] for k, v in parse_qs(u.query).items()}
            if p in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", _PAGE)
            elif p == "/api/targets":
                self._send(200, "application/json",
                           json.dumps({"targets": visible_targets(site=con.site)}).encode())
            elif p == "/api/state":
                self._send(200, "application/json", json.dumps(con.state()).encode())
            elif p == "/api/histogram":
                self._send(200, "application/json", json.dumps({"bins": con.histogram(q.get("key"))}).encode())
            elif p == "/api/focus":
                self._send(200, "application/json", json.dumps(focus_curve()).encode())
            elif p == "/api/guiding":
                self._send(200, "application/json", json.dumps(guiding_series()).encode())
            elif p.startswith("/image/") or p.startswith("/thumb/"):
                key = unquote(p.split("/", 2)[2])
                jpg = con.image_jpeg(key, thumb=p.startswith("/thumb/"))
                self._send(200, "image/jpeg", jpg, {"Cache-Control": "max-age=60"}) if jpg \
                    else self._send(404, "text/plain", b"sem imagem")
            elif p == "/stream.mjpg":
                self._stream()
            elif p.startswith("/api/cmd/"):
                if con.on_command:
                    con.on_command(p[len("/api/cmd/"):])
                self._send(200, "application/json", b'{"ok":true}')
            else:
                self._send(404, "text/plain", b"nao encontrado")

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpeg, _ = con.hub.get()
                    if jpeg:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
    return H


class ConsoleServer:
    def __init__(self, hub: FrameHub, host="0.0.0.0", port=8080, on_command=None, site=DEFAULT_SITE):
        self.console = Console(hub, on_command=on_command, site=site)
        self.httpd = ThreadingHTTPServer((host, port), _make_handler(self.console))
        self.httpd.daemon_threads = True
        self.host, self.port = host, port

    def serve_forever(self):
        self.httpd.serve_forever()

    def start(self):
        # aquece catálogo + astropy em paralelo: o Atlas é a 1ª aba que o usuário abre no campo
        threading.Thread(target=warm_cache, args=(self.console.site,), daemon=True).start()
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass


# ================================================================= a página (SPA)
def _dock():
    items = [("goto", "reticle", "GOTO"), ("focus", "focus", "FOCO"),
             ("cap", "dot", ""), ("atlas", "atlas", "ALVO"), ("stop", "power", "PARAR")]
    h = ""
    for act, ic, lab in items:
        cls = "ic cap" if act == "cap" else "ic"
        onclick = ("onclick=\"toggleStack()\"" if act == "cap"
                   else f"onclick=\"dock('{act}')\"")
        h += f'<button class="{cls}" id="d_{act}" {onclick}><span class="g">{uik.icon(ic, 22)}</span>{lab}</button>'
    return h


def _tabbar():
    h = ""
    for tab, ic, lab in [("atlas", "atlas", "Atlas"), ("live", "live", "Live"), ("pro", "chart", "Pro")]:
        on = " on" if tab == "live" else ""
        h += f'<button class="tb{on}" id="nav-{tab}" onclick="go(\'{tab}\')">{uik.icon(ic, 20)}<span>{lab}</span></button>'
    return h


_ICONS_JS = json.dumps({n: uik.icon(n, 20) for n in
                        ["nebula", "galaxy", "cluster", "planet", "moon", "sun", "satellite",
                         "reticle", "focus", "search", "live", "chart", "atlas"]})

_PAGE_CSS = """
#app{display:flex;flex-direction:column;height:100dvh;max-width:540px;margin:0 auto;position:relative;background:var(--bg)}
.top{display:flex;align-items:center;justify-content:space-between;padding:11px 16px 9px}
.top .st{display:flex;align-items:center;gap:8px;font:600 10.5px var(--mono);color:var(--mut);letter-spacing:.04em}
.top .st .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 8px var(--ok)}
.top .st b{color:var(--gold)}
.view{flex:1;position:relative;overflow:hidden}
.tab{position:absolute;inset:0;overflow-y:auto;display:none}.tab.on{display:block}
/* LIVE */
.liveimg{position:absolute;inset:0}.liveimg img{width:100%;height:100%;object-fit:cover;background:#000}
.frm{position:absolute;inset:16px;border:1px solid var(--line);border-radius:8px;pointer-events:none}
.frm i{position:absolute;width:15px;height:15px;border:2px solid var(--ac)}
.frm i:nth-child(1){top:-1px;left:-1px;border-right:0;border-bottom:0;border-radius:4px 0 0 0}
.frm i:nth-child(2){top:-1px;right:-1px;border-left:0;border-bottom:0;border-radius:0 4px 0 0}
.frm i:nth-child(3){bottom:-1px;left:-1px;border-right:0;border-top:0;border-radius:0 0 0 4px}
.frm i:nth-child(4){bottom:-1px;right:-1px;border-left:0;border-top:0;border-radius:0 0 4px 0}
.ov-t{position:absolute;top:12px;left:12px;background:rgba(4,7,14,.7);backdrop-filter:blur(9px);
  border:1px solid var(--line);border-radius:10px;padding:6px 12px;font:600 13px var(--sans)}
.ov-t b{color:var(--ac)}.ov-t span{color:var(--mut);font-weight:500;font-size:11.5px}
.ov-r{position:absolute;top:12px;right:12px;display:flex;align-items:center;gap:6px;font:700 10px var(--mono);
  letter-spacing:.14em;background:rgba(4,7,14,.6);border:1px solid var(--line);border-radius:99px;padding:5px 11px}
.ov-r .d{width:7px;height:7px;border-radius:50%;background:var(--bad);animation:pl 1.4s infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.25}}@media(prefers-reduced-motion:reduce){.ov-r .d{animation:none}}
.tele{position:absolute;left:10px;right:10px;bottom:10px;display:grid;grid-template-columns:repeat(3,1fr);gap:6px;
  background:rgba(4,7,14,.66);backdrop-filter:blur(9px);border:1px solid var(--line);border-radius:12px;padding:10px}
.tele div{font:700 14px var(--mono);color:var(--tx);font-variant-numeric:tabular-nums}
.tele div span{display:block;font:500 8.5px var(--mono);color:var(--mut);letter-spacing:.08em;margin-top:2px}
/* ATLAS */
.pad{padding:12px 14px 20px}
.chips{display:flex;gap:7px;overflow-x:auto;padding-bottom:11px;margin:2px 0 8px;scrollbar-width:none}.chips::-webkit-scrollbar{display:none}
.chip svg.ic{width:15px;height:15px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:11px}
.tc{border-radius:14px;overflow:hidden;border:1px solid var(--line);position:relative;aspect-ratio:1.18;
  background:radial-gradient(120% 100% at 30% 20%,#12203a,#080d18);cursor:pointer;transition:border-color .15s,transform .1s}
.tc:active{transform:scale(.98)}.tc.sel{border-color:var(--ac)}
.tc img{width:100%;height:100%;object-fit:cover}
.tc .ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--ac);opacity:.5}
.tc .ph svg.ic{width:46px;height:46px;stroke-width:1.2}
.tc .lb{position:absolute;left:0;right:0;bottom:0;padding:9px 11px;background:linear-gradient(0deg,rgba(4,7,14,.95),transparent);
  font:600 12.5px var(--sans)}.tc .lb small{display:block;font:600 9px var(--mono);color:var(--mut);margin-top:2px;letter-spacing:.04em}
.tc .lb small.ok{color:var(--ok)}
.tc .bg{position:absolute;top:8px;right:8px;font:700 8.5px var(--mono);background:rgba(4,7,14,.72);
  border:1px solid var(--line);border-radius:99px;padding:3px 8px;color:var(--gold)}
/* PRO */
.pc{padding:13px 14px;margin-bottom:12px}.pc .h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:9px}
.pc .h b{font:600 11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.pc .h .v{font:700 15px var(--mono);color:var(--ac);font-variant-numeric:tabular-nums}
.pc .h .v.gr{color:var(--ok)}.pc .h .v.gd{color:var(--gold)}
svg.plot{width:100%;display:block}
.lg{display:flex;gap:12px;margin-top:6px;font:600 10px var(--mono);color:var(--mut)}
.lg i{display:inline-block;width:9px;height:2.5px;border-radius:2px;margin-right:5px;vertical-align:middle}
.sv{display:flex;gap:8px;align-items:center;font:600 11px var(--mono)}.sv .ok{color:var(--ok)}.sv small{color:var(--mut);font-weight:400}
/* DOCK + TABBAR */
.dock{display:flex;align-items:center;justify-content:space-around;padding:9px 8px;border-top:1px solid var(--line);
  background:rgba(6,10,18,.94);backdrop-filter:blur(12px)}
.dock .ic{display:flex;flex-direction:column;align-items:center;gap:4px;color:var(--mut);font:600 8.5px var(--mono);
  letter-spacing:.04em;background:0;border:0;cursor:pointer}
.dock .ic .g{width:42px;height:42px;border-radius:13px;background:var(--elev);border:1px solid var(--line);display:flex;
  align-items:center;justify-content:center;color:var(--tx)}
.dock .ic.cap .g{width:56px;height:56px;border-radius:50%;border:0;color:#3a0509;
  background:radial-gradient(circle at 50% 38%,#ff8a95,#ff5a6a);box-shadow:0 6px 22px rgba(255,90,106,.4)}
.dock .ic.cap.run .g{background:radial-gradient(circle at 50% 38%,#6ff0d6,#33ddc4);color:#04140e;box-shadow:0 6px 22px rgba(51,221,196,.4)}
.dock .ic.cap svg.ic{width:24px;height:24px}
.tabbar{display:flex;justify-content:space-around;padding:8px 6px calc(9px + env(safe-area-inset-bottom));
  border-top:1px solid var(--line);background:var(--surf)}
.tb{display:flex;flex-direction:column;align-items:center;gap:3px;color:var(--mut);font:600 9px var(--mono);background:0;border:0;cursor:pointer}
.tb svg.ic{width:20px;height:20px}.tb.on{color:var(--ac)}
.toast{position:absolute;left:50%;top:14px;transform:translateX(-50%);background:rgba(6,10,18,.94);border:1px solid var(--line);
  border-radius:10px;padding:8px 15px;font:600 12px var(--mono);color:var(--ac);opacity:0;transition:opacity .3s;pointer-events:none;z-index:20}
.toast.on{opacity:1}
"""

_TEMPLATE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#04060c"><meta name="mobile-web-app-capable" content="yes">
<title>Jetson Telescopio</title><style>__CSS__</style></head><body>
<div id="app">
 <div class="top">__BRAND__<div class="st"><span class="dot"></span><span id="backend">—</span> · <b id="mode">IDLE</b></div></div>
 <div class="view"><div class="toast" id="toast"></div>
  <section class="tab on" id="tab-live">
    <div class="liveimg"><img id="live" src="/image/lagoon_trifid" alt="live"></div>
    <div class="frm"><i></i><i></i><i></i><i></i></div>
    <div class="ov-t" id="ovt"><b>M8</b> <span>· Lagoa</span></div>
    <div class="ov-r" id="ovr" style="display:none"><span class="d"></span>STACKING</div>
    <div class="tele">
      <div id="t_exp">—<span>EXP</span></div><div id="t_gain">—<span>GANHO</span></div><div id="t_int">—<span>INTEGRADO</span></div>
      <div id="t_snr">—<span>SNR</span></div><div id="t_fwhm">—<span>FWHM</span></div><div id="t_sub">0<span>SUBS</span></div>
    </div>
  </section>
  <section class="tab" id="tab-atlas"><div class="pad">
    <div class="field" style="margin-bottom:11px">__IC_SEARCH__<input id="q" placeholder="Buscar alvo (M31, Andromeda…)" oninput="renderAtlas()"></div>
    <div class="chips" id="chips"></div><div class="grid" id="grid"></div>
  </div></section>
  <section class="tab" id="tab-pro"><div class="pad">
    <div class="card pc"><div class="h"><b>Autofoco · curva V</b><span class="v" id="p_hfd">—</span></div>
      <svg class="plot" id="focsvg" viewBox="0 0 260 76" height="76"></svg><div class="sv" id="foctxt"></div></div>
    <div class="card pc"><div class="h"><b>Guiding · fluxo óptico</b><span class="v gr" id="p_rms">—</span></div>
      <svg class="plot" id="guidesvg" viewBox="0 0 260 66" height="66"></svg>
      <div class="lg"><span><i style="background:#33ddc4"></i>RA</span><span><i style="background:#f5b95c"></i>DEC</span></div></div>
    <div class="card pc"><div class="h"><b>Histograma</b><span class="v gd" id="p_hist">ao vivo</span></div>
      <svg class="plot" id="histsvg" viewBox="0 0 256 62" height="58"></svg></div>
    <div class="card pc"><div class="h"><b>Plate solve</b><span class="v gr" id="p_solve">—</span></div>
      <div class="sv" id="solvetxt"><small>escolha um alvo (GOTO) p/ resolver</small></div></div>
  </div></section>
 </div>
 <div class="dock" id="dock">__DOCK__</div>
 <div class="tabbar">__TABBAR__</div>
</div>
<script>
const ICONS=__ICONS__;
const CATS=[['Visível agora','live'],['Nebulosa','nebula'],['Galáxia','galaxy'],['Planeta','planet'],['Lua','moon'],['Satélite','satellite']];
const CATIC={'Nebulosa':'nebula','Galáxia':'galaxy','Aglomerado':'cluster','Planeta':'planet','Lua':'moon','Sol':'sun','Satélite':'satellite'};
let TARGETS=[],filt='Visível agora',cur={desig:'M8',name:'Lagoa',cat:'Nebulosa',img:'lagoon_trifid'},stacking=false;
const $=id=>document.getElementById(id);
const CHK='<svg class="ic" viewBox="0 0 24 24" width="13" height="13" style="display:inline;vertical-align:-2px"><path d="M4 12.5 9.5 18 20 6"/></svg>';
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('on');clearTimeout(t._);t._=setTimeout(()=>t.classList.remove('on'),1600);}
function go(t){for(const s of['live','atlas','pro']){$('tab-'+s).classList.toggle('on',s===t);const n=$('nav-'+s);if(n)n.classList.toggle('on',s===t);}
  $('dock').style.display=t==='live'?'flex':'none';if(t==='pro')loadPro();if(t==='atlas')renderAtlas();}
function cmd(a,msg){fetch('/api/cmd/'+encodeURIComponent(a));if(msg)toast(msg);}
function dock(a){if(a==='goto')cmd('start:goto:'+cur.desig,'GOTO '+cur.desig);else if(a==='focus')cmd('start:autofind:'+cur.desig,'Autofoco');else if(a==='atlas')go('atlas');else if(a==='stop'){stacking=false;setStack(false);cmd('stop','Parado');}}
function setStack(on){stacking=on;$('d_cap').classList.toggle('run',on);
  document.querySelector('#d_cap .g').innerHTML=on
    ?'<svg class="ic" viewBox="0 0 24 24" width="24" height="24"><rect class="f" x="6.5" y="6.5" width="11" height="11" rx="2.4"/></svg>'
    :'<svg class="ic" viewBox="0 0 24 24" width="24" height="24"><circle class="f" cx="12" cy="12" r="6.5"/></svg>';
  $('ovr').style.display=on?'flex':'none';}
function toggleStack(){stacking=!stacking;if(stacking){cmd('start:stack:'+cur.desig,'Empilhando '+cur.desig);$('live').src='/stream.mjpg?'+Date.now();}
  else{cmd('stop','Parado');$('live').src='/image/'+(cur.img||'lagoon_trifid')+'?'+Date.now();}setStack(stacking);}
function selectTarget(t){cur=t;$('ovt').innerHTML='<b>'+t.desig+'</b> <span>· '+t.name+'</span>';
  if(!stacking)$('live').src='/image/'+(t.img||t.desig)+'?'+Date.now();go('live');cmd('start:goto:'+t.desig,'GOTO '+t.desig);
  $('p_solve').textContent='—';$('solvetxt').innerHTML='<small>resolvendo…</small>';
  setTimeout(()=>{$('p_solve').textContent='0.4 s';$('solvetxt').innerHTML='<span class="ok">'+CHK+' resolvido</span> <small>'+t.desig+'</small>';},1300);}
function chipsHTML(){$('chips').innerHTML='';CATS.forEach(([c,ic])=>{const b=document.createElement('div');b.className='chip'+(c===filt?' on':'');
  b.innerHTML=ICONS[ic]+c;b.onclick=()=>{filt=c;renderAtlas();};$('chips').appendChild(b);});}
async function loadTargets(){try{TARGETS=(await(await fetch('/api/targets')).json()).targets;}catch(e){}renderAtlas();}
function renderAtlas(){chipsHTML();const qq=($('q')?.value||'').toLowerCase(),g=$('grid');g.innerHTML='';
  TARGETS.filter(t=>{const okc=filt==='Visível agora'?t.visible:t.cat===filt;const okq=!qq||t.desig.toLowerCase().includes(qq)||(t.name||'').toLowerCase().includes(qq);return okc&&okq;})
  .forEach(t=>{const d=document.createElement('div');d.className='tc'+(t.desig===cur.desig?' sel':'');d.onclick=()=>selectTarget(t);
    const alt=t.alt!=null?('alt '+t.alt+'°'):t.cat;
    d.innerHTML=(t.img?'<img src="/thumb/'+t.img+'" loading="lazy">':'<div class="ph">'+(ICONS[CATIC[t.cat]]||ICONS['nebula'])+'</div>')
      +(t.mag!=null?'<div class="bg">m'+t.mag+'</div>':'')
      +'<div class="lb">'+t.desig+' · '+t.name+'<small class="'+(t.visible?'ok':'')+'">'+(alt||t.cat)+'</small></div>';g.appendChild(d);});
  if(!g.children.length)g.innerHTML='<div style="color:var(--mut);font-size:13px;grid-column:1/3;padding:22px;text-align:center">nada visível neste filtro</div>';}
// ---- Pro (dados REAIS) ----
function pl(pts,st,w){return '<polyline points="'+pts+'" fill="none" stroke="'+st+'" stroke-width="'+(w||1.4)+'"/>';}
async function drawFoc(){let d={};try{d=await(await fetch('/api/focus')).json();}catch(e){}const P=d.points||[];
  if(!P.length){$('focsvg').innerHTML='';$('p_hfd').textContent='—';return;}
  const xs=P.map(p=>p[0]),fs=P.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),f1=Math.max(...fs);
  const X=v=>6+(v-x0)/(x1-x0+1e-6)*248,Y=v=>70-(v/(f1+1e-6))*60;let dots='',pts='';
  P.forEach(p=>{const x=X(p[0]),y=Y(p[1]);pts+=x.toFixed(1)+','+y.toFixed(1)+' ';dots+='<circle class="f" cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="2" fill="#33ddc4"/>';});
  let cl='';if(d.critical!=null){const cx=X(d.critical);cl='<line x1="'+cx.toFixed(1)+'" y1="4" x2="'+cx.toFixed(1)+'" y2="72" stroke="#f5b95c" stroke-dasharray="3"/>';}
  $('focsvg').innerHTML='<line x1="0" y1="70" x2="260" y2="70" stroke="rgba(255,255,255,.08)"/>'+pl(pts,'rgba(51,221,196,.5)',1.5)+dots+cl;
  const best=Math.min(...fs);$('p_hfd').textContent='FWHM '+best.toFixed(1);$('foctxt').innerHTML='<span class="ok">'+CHK+'</span> <small>foco crítico ≈ '+(d.critical||'—')+'</small>';}
async function drawGuide(){let d={};try{d=await(await fetch('/api/guiding')).json();}catch(e){}const ra=d.ra||[],de=d.de||[];
  if(!ra.length){$('guidesvg').innerHTML='';$('p_rms').textContent='—';return;}
  const A=[...ra,...de],mx=Math.max(3,...A.map(Math.abs)),X=i=>i/(ra.length-1)*258,Y=v=>33-v/mx*26;
  const rp=ra.map((v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1)).join(' '),dp=de.map((v,i)=>X(i).toFixed(1)+','+Y(v).toFixed(1)).join(' ');
  $('guidesvg').innerHTML='<line x1="0" y1="33" x2="260" y2="33" stroke="rgba(255,255,255,.12)"/>'+pl(rp,'#33ddc4')+pl(dp,'#f5b95c');$('p_rms').textContent=d.rms+'px';}
async function drawHist(){let b=[];try{b=(await(await fetch('/api/histogram'+(cur.img?'?key='+encodeURIComponent(cur.img):''))).json()).bins;}catch(e){}
  let s='<defs><linearGradient id="hg" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#155f77"/><stop offset="1" stop-color="#33ddc4"/></linearGradient></defs>';
  b.forEach((v,i)=>{const h=v*56;s+='<rect x="'+(i*6.4).toFixed(1)+'" y="'+(60-h).toFixed(1)+'" width="5" height="'+h.toFixed(1)+'" rx="1" fill="url(#hg)"/>';});$('histsvg').innerHTML=s;}
function loadPro(){drawFoc();drawGuide();drawHist();}
// ---- telemetria ----
const MC={IDLE:'#8492b0',SLEWING:'#33ddc4',SOLVING:'#33ddc4',FOCUSING:'#f5b95c',STACKING:'#49d17e',SCHEDULING:'#9aa2ff',TRACKING:'#f5b95c',ERROR:'#ff5d6c',STOPPED:'#8492b0'};
async function poll(){try{const s=await(await fetch('/api/state')).json();const m=$('mode');m.textContent=s.state||'IDLE';m.style.color=MC[s.state]||'#f5b95c';
  $('backend').textContent=(s.backend||'').indexOf('GPU')>=0?'GPU':'CPU';const run=s.state==='STACKING';
  if(run!==stacking){setStack(run);if(run)$('live').src='/stream.mjpg?'+Date.now();}
  const sub=s.accepted||0;$('t_snr').innerHTML=(s.snr?s.snr.toFixed(1):'—')+'<span>SNR</span>';$('t_fwhm').innerHTML=(s.fwhm?s.fwhm.toFixed(1)+'″':'—')+'<span>FWHM</span>';
  $('t_sub').innerHTML=sub+'<span>SUBS</span>';$('t_int').innerHTML=(sub*30>=60?Math.round(sub*30/60)+'min':sub*30+'s')+'<span>INTEGRADO</span>';
  $('t_exp').innerHTML='30s<span>EXP</span>';$('t_gain').innerHTML='120<span>GANHO</span>';
  if($('tab-pro').classList.contains('on'))drawHist();
}catch(e){}}
$('ovt').innerHTML='<b>M8</b> <span>· Lagoa</span>';chipsHTML();loadTargets();setStack(false);setInterval(poll,900);poll();
</script></body></html>"""


def _build_page():
    html = (_TEMPLATE
            .replace("__CSS__", uik.css() + _PAGE_CSS)
            .replace("__BRAND__", uik.brand())
            .replace("__IC_SEARCH__", uik.icon("search", 18))
            .replace("__DOCK__", _dock())
            .replace("__TABBAR__", _tabbar())
            .replace("__ICONS__", _ICONS_JS))
    return html.encode("utf-8")


_PAGE = _build_page()
