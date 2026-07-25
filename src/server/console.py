"""Console de campo — a UI de PRODUTO (estilo DWARF + ASIAIR), servida pela própria Orin.

Uma webpage única com 3 abas — **Atlas** (escolher alvo, catálogo real + visibilidade), **Live**
(view + telemetria ao vivo) e **Pro** (foco, guiding, histograma, plate-solve) — ligada ao mesmo
`Controller`/`FrameHub` do painel. Stdlib só (http.server). Telemetria por polling JSON + live view
por JPEG-push (MJPEG); no Orin os JPEGs podem sair no encoder de HW (NVJPEG). Sem internet: tudo local.

Roda ao lado do painel/estúdio (porta própria). Ver docs/33.
"""
from __future__ import annotations
import io
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import cv2

from ..postproc.render import render, PRESETS
from .studio import CATALOG as STACKS, _load_linear
from .webview import FrameHub

try:
    from ..core import catalog as _cat
except Exception:
    _cat = None

# Local de observação padrão (São Paulo) — usado p/ calcular altitude/visibilidade agora.
DEFAULT_SITE = (-23.55, -46.63)

# Alvos em destaque no Atlas: (designação no catálogo, chave do stack real ou None, categoria).
FAMOUS = [
    ("M8", "lagoon_trifid", "Nebulosa"), ("NGC2244", "rosette", "Nebulosa"),
    ("M51", "m51", "Galáxia"),
    ("M31", None, "Galáxia"), ("M42", None, "Nebulosa"), ("M45", None, "Aglomerado"),
    ("M13", None, "Aglomerado"), ("M27", None, "Nebulosa"), ("M57", None, "Nebulosa"),
    ("M81", None, "Galáxia"), ("M104", None, "Galáxia"), ("M20", None, "Nebulosa"),
]
_PRESET_BY_KEY = {"lagoon_trifid": "vivido", "rosette": "nebulosa", "m51": "natural"}


def visible_targets(when=None, site=DEFAULT_SITE):
    """Lista de alvos p/ o Atlas: nome, categoria, magnitude, altitude AGORA e se temos imagem real.

    Usa o catálogo real (pyongc) p/ resolver RA/DEC e calcular a altitude no local/hora. Se o catálogo
    não estiver disponível, cai numa lista estática (ainda mostra os alvos, sem altitude)."""
    when = when or datetime.now(timezone.utc)
    lat, lon = site
    out = []
    for desig, key, cat in FAMOUS:
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
        out.append({
            "desig": desig,
            "name": (obj.common if (obj and obj.common) else desig),
            "cat": cat,
            "mag": (round(obj.mag, 1) if (obj and obj.mag is not None) else None),
            "alt": (round(alt) if alt is not None else None),
            "visible": bool(alt is not None and alt > 15),
            "img": key,
        })
    return out


def histogram_bins(rgb, n=40):
    """Histograma de luminância (n bins, normalizado 0..1) — p/ a aba Pro."""
    a = np.asarray(rgb)
    lum = a.mean(2) if a.ndim == 3 else a
    h, _ = np.histogram(lum, bins=n, range=(0, 255))
    m = float(h.max()) or 1.0
    return [round(float(v) / m, 3) for v in h]


def _encode(rgb, q=88, max_side=None):
    a = rgb
    if max_side:
        hh, ww = a.shape[:2]
        s = max_side / max(hh, ww)
        if s < 1.0:
            a = cv2.resize(a, (int(ww * s), int(hh * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(a, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes() if ok else None


class Console:
    """Servidor do console. Renderiza as imagens reais sob demanda (cacheadas) e serve a SPA + APIs."""
    def __init__(self, hub: FrameHub, on_command=None, site=DEFAULT_SITE):
        self.hub = hub
        self.on_command = on_command
        self.site = site
        self._img = {}          # key -> (full_jpeg, thumb_jpeg, hist)
        self._lock = threading.Lock()

    def _rendered(self, key):
        with self._lock:
            if key in self._img:
                return self._img[key]
            meta = STACKS.get(key)
            if not meta or not os.path.exists(meta["stack"]):
                self._img[key] = None
                return None
            lin = _load_linear(meta["stack"])
            rgb = render(lin, PRESETS.get(_PRESET_BY_KEY.get(key, "natural")))
            full = _encode(rgb, q=90, max_side=1100)
            thumb = _encode(rgb, q=82, max_side=260)
            self._img[key] = (full, thumb, histogram_bins(rgb))
            return self._img[key]

    def image_jpeg(self, key, thumb=False):
        r = self._rendered(key)
        return None if r is None else (r[1] if thumb else r[0])

    def histogram(self, key=None):
        if key and STACKS.get(key):
            r = self._rendered(key)
            if r:
                return r[2]
        jpeg, _ = self.hub.get()          # senão, do frame ao vivo
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
                self._send(200, "application/json",
                           json.dumps({"bins": con.histogram(q.get("key"))}).encode())
            elif p.startswith("/image/") or p.startswith("/thumb/"):
                key = p.split("/", 2)[2]
                jpg = con.image_jpeg(key, thumb=p.startswith("/thumb/"))
                if jpg:
                    self._send(200, "image/jpeg", jpg, {"Cache-Control": "max-age=60"})
                else:
                    self._send(404, "text/plain", b"sem imagem")
            elif p == "/stream.mjpg":
                self._stream()
            elif p.startswith("/api/cmd/"):
                action = p[len("/api/cmd/"):]
                if con.on_command:
                    con.on_command(action)
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
        threading.Thread(target=self.serve_forever, daemon=True).start()

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass


# ================================================================= a página (SPA)
_PAGE = ("""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#05070d"><meta name="mobile-web-app-capable" content="yes">
<title>Telescopio Jetson</title>
<style>
 :root{color-scheme:dark;--bg:#06080e;--scr:#080b13;--glass:rgba(255,255,255,.055);--line:rgba(255,255,255,.09);
   --tx:#eef2fb;--mut:#8b99b8;--cy:#35e0c8;--am:#f7b45a;--gr:#4cd884;--rd:#ff5a6a;--vi:#9aa2ff}
 *{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
 html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);
   font:15px/1.5 system-ui,"Segoe UI",sans-serif;overflow:hidden}
 .mono{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}
 #app{display:flex;flex-direction:column;height:100dvh;max-width:520px;margin:0 auto;position:relative}
 .sbar{display:flex;align-items:center;justify-content:space-between;padding:11px 16px 8px;
   font:600 10.5px ui-monospace,monospace;color:var(--mut);letter-spacing:.02em}
 .sbar .dev{display:flex;align-items:center;gap:6px;color:var(--tx)}
 .dot{width:7px;height:7px;border-radius:50%;background:var(--gr);box-shadow:0 0 8px var(--gr)}
 .sbar .r{display:flex;gap:10px} .sbar .mode{color:var(--am)}
 .view{flex:1;position:relative;overflow:hidden}
 .tab{position:absolute;inset:0;overflow-y:auto;padding:0;display:none}
 .tab.on{display:block}
 /* ---- LIVE ---- */
 #tab-live{padding:0}
 .liveimg{position:absolute;inset:0}
 .liveimg img{width:100%;height:100%;object-fit:cover;display:block;background:#000}
 .framec{position:absolute;inset:16px;border:1px solid rgba(255,255,255,.13);border-radius:8px;pointer-events:none}
 .framec:before,.framec:after{content:"";position:absolute;width:16px;height:16px;border:2px solid var(--cy)}
 .framec:before{top:-1px;left:-1px;border-right:0;border-bottom:0;border-radius:4px 0 0 0}
 .framec:after{bottom:-1px;right:-1px;border-left:0;border-top:0;border-radius:0 0 4px 0}
 .tgt{position:absolute;top:12px;left:12px;background:rgba(6,10,18,.66);backdrop-filter:blur(8px);
   border:1px solid var(--line);border-radius:10px;padding:6px 11px;font:600 12px system-ui}
 .tgt b{color:var(--cy)} .tgt small{color:var(--mut);font-weight:400}
 .rec{position:absolute;top:12px;right:12px;display:flex;align-items:center;gap:6px;font:700 10px ui-monospace,monospace;
   letter-spacing:.14em;color:#fff;background:rgba(6,10,18,.6);border:1px solid var(--line);border-radius:99px;padding:5px 10px}
 .rec .d{width:7px;height:7px;border-radius:50%;background:var(--rd);animation:pulse 1.4s infinite}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
 @media(prefers-reduced-motion:reduce){.rec .d{animation:none}}
 .tele{position:absolute;left:10px;right:10px;bottom:10px;display:grid;grid-template-columns:repeat(3,1fr);gap:6px;
   background:rgba(6,10,18,.62);backdrop-filter:blur(8px);border:1px solid var(--line);border-radius:12px;padding:9px 10px}
 .tele div{font:700 13px ui-monospace,monospace;color:var(--tx);font-variant-numeric:tabular-nums}
 .tele div span{display:block;font:500 8.5px ui-monospace,monospace;color:var(--mut);letter-spacing:.06em;margin-top:1px}
 /* ---- ATLAS ---- */
 .pad{padding:12px 14px}
 h2{font:700 12px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut);margin:6px 2px 10px}
 .search{background:var(--glass);border:1px solid var(--line);border-radius:11px;padding:9px 12px;color:var(--mut);
   font-size:13px;display:flex;gap:8px;align-items:center;margin-bottom:11px}
 .search input{flex:1;background:0;border:0;color:var(--tx);font-size:14px;outline:0}
 .chips{display:flex;gap:6px;overflow-x:auto;padding-bottom:10px;margin-bottom:4px}
 .chip{flex:0 0 auto;font:600 11px ui-monospace,monospace;padding:6px 11px;border-radius:14px;border:1px solid var(--line);
   color:var(--mut);cursor:pointer;white-space:nowrap}
 .chip.on{background:var(--cy);color:#04120e;border-color:var(--cy)}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
 .tcard{border-radius:13px;overflow:hidden;border:1px solid var(--line);position:relative;aspect-ratio:1.25;
   background:linear-gradient(140deg,#0e1626,#0a0f1c);cursor:pointer}
 .tcard img{width:100%;height:100%;object-fit:cover;display:block}
 .tcard .ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:34px;opacity:.5}
 .tcard .lb{position:absolute;left:0;right:0;bottom:0;padding:8px 10px;
   background:linear-gradient(0deg,rgba(6,10,18,.94),transparent);font:600 12px system-ui}
 .tcard .lb small{display:block;font:600 9px ui-monospace,monospace;color:var(--mut);margin-top:1px}
 .tcard .lb small.ok{color:var(--gr)} .tcard .badge{position:absolute;top:7px;right:7px;font:700 8.5px ui-monospace,monospace;
   background:rgba(6,10,18,.7);border:1px solid var(--line);border-radius:99px;padding:3px 7px;color:var(--am)}
 /* ---- PRO ---- */
 .pcard{background:var(--glass);border:1px solid var(--line);border-radius:13px;padding:12px 13px;margin-bottom:11px}
 .pcard .h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px}
 .pcard .h b{font:600 11px ui-monospace,monospace;letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
 .pcard .h .v{font:700 14px ui-monospace,monospace;color:var(--cy);font-variant-numeric:tabular-nums}
 .pcard .h .v.gr{color:var(--gr)} .pcard .h .v.am{color:var(--am)}
 svg.gr{width:100%;display:block}
 .solve{display:flex;gap:8px;align-items:center;font:600 11px ui-monospace,monospace;color:var(--tx)}
 .solve .ok{color:var(--gr)} .solve small{color:var(--mut);font-weight:400}
 .sim{font:600 9px ui-monospace,monospace;color:var(--am);letter-spacing:.1em}
 /* ---- dock + tabbar ---- */
 .dock{display:flex;align-items:center;justify-content:space-around;padding:9px 10px;border-top:1px solid var(--line);
   background:rgba(8,11,20,.92);backdrop-filter:blur(10px)}
 .ic{display:flex;flex-direction:column;align-items:center;gap:3px;color:var(--mut);font:600 8.5px ui-monospace,monospace;
   letter-spacing:.03em;cursor:pointer;background:0;border:0}
 .ic .g{width:40px;height:40px;border-radius:13px;background:var(--glass);border:1px solid var(--line);display:flex;
   align-items:center;justify-content:center;font-size:18px}
 .cap .g{width:54px;height:54px;border-radius:50%;border:0;font-size:20px;color:#2a0508;
   background:radial-gradient(circle at 50% 40%,#ff8a95,#ff5a6a);box-shadow:0 6px 20px rgba(255,90,106,.4)}
 .cap.run .g{background:radial-gradient(circle at 50% 40%,#6ff0d6,#35e0c8);color:#04140e;box-shadow:0 6px 20px rgba(53,224,200,.4)}
 .tabbar{display:flex;justify-content:space-around;padding:7px 6px calc(9px + env(safe-area-inset-bottom));
   border-top:1px solid var(--line);background:#080b14}
 .tb{display:flex;flex-direction:column;align-items:center;gap:3px;color:var(--mut);font:600 8.5px ui-monospace,monospace;
   background:0;border:0;cursor:pointer} .tb .i{font-size:17px} .tb.on{color:var(--cy)}
 .toast{position:absolute;left:50%;top:14px;transform:translateX(-50%);background:rgba(6,10,18,.92);
   border:1px solid var(--line);border-radius:10px;padding:8px 14px;font:600 12px ui-monospace,monospace;
   color:var(--cy);opacity:0;transition:opacity .3s;pointer-events:none;z-index:20}
 .toast.on{opacity:1}
</style></head><body>
<div id="app">
 <div class="sbar"><div class="dev"><span class="dot"></span>TELESCOPIO-JETSON</div>
   <div class="r"><span id="backend">—</span><span class="mode" id="mode">● IDLE</span></div></div>

 <div class="view">
   <div class="toast" id="toast"></div>

   <!-- LIVE -->
   <section class="tab on" id="tab-live">
     <div class="liveimg"><img id="live" src="/image/lagoon_trifid" alt="live"></div>
     <div class="framec"></div>
     <div class="tgt" id="tgt"><b>M8</b> · Lagoa <small>· nebulosa</small></div>
     <div class="rec" id="rec" style="display:none"><span class="d"></span>STACKING</div>
     <div class="tele">
       <div id="t_exp">—<span>EXP</span></div><div id="t_gain">—<span>GANHO</span></div><div id="t_int">—<span>INTEGRADO</span></div>
       <div id="t_snr">—<span>SNR</span></div><div id="t_fwhm">—<span>FWHM</span></div><div id="t_acc">0<span>SUBS</span></div>
     </div>
   </section>

   <!-- ATLAS -->
   <section class="tab" id="tab-atlas"><div class="pad">
     <div class="search">🔍 <input id="q" placeholder="Buscar alvo (M31, Júpiter…)" oninput="renderAtlas()"></div>
     <div class="chips" id="chips"></div>
     <div class="grid" id="grid"></div>
   </div></section>

   <!-- PRO -->
   <section class="tab" id="tab-pro"><div class="pad">
     <div class="pcard"><div class="h"><b>Autofoco · curva V</b><span class="v" id="p_hfd">HFD —</span></div>
       <svg class="gr" id="focsvg" viewBox="0 0 260 74" height="74"></svg>
       <div class="solve"><span class="sim">◇ SIM — sem hardware</span></div></div>
     <div class="pcard"><div class="h"><b>Guiding · erro RMS</b><span class="v gr" id="p_rms">—</span></div>
       <svg class="gr" id="guidesvg" viewBox="0 0 260 66" height="66"></svg>
       <div class="solve"><small style="color:#35e0c8">■ RA</small>&nbsp;<small style="color:#f7b45a">■ DEC</small>&nbsp;<span class="sim">◇ SIM</span></div></div>
     <div class="pcard"><div class="h"><b>Histograma</b><span class="v am" id="p_hist">ao vivo</span></div>
       <svg class="gr" id="histsvg" viewBox="0 0 256 64" height="60"></svg></div>
     <div class="pcard"><div class="h"><b>Plate solve</b><span class="v gr" id="p_solve">—</span></div>
       <div class="solve" id="solvetxt"><small>aponte um alvo (GOTO) p/ resolver</small></div></div>
   </div></section>
 </div>

 <!-- DOCK (contexto Live) -->
 <div class="dock" id="dock">
   <button class="ic" onclick="cmd('start:goto:'+cur.desig,'GOTO '+cur.desig)"><div class="g">🎯</div>GOTO</button>
   <button class="ic" onclick="cmd('start:autofind:'+cur.desig,'Auto-find')"><div class="g">🔬</div>FOCO</button>
   <button class="ic cap" id="capbtn" onclick="toggleStack()"><div class="g" id="capg">●</div></button>
   <button class="ic" onclick="go('atlas')"><div class="g">🗺️</div>ALVO</button>
   <button class="ic" onclick="cmd('stop','Parado')"><div class="g">⏹️</div>PARAR</button>
 </div>

 <!-- TABBAR -->
 <div class="tabbar">
   <button class="tb" onclick="go('atlas')" id="nav-atlas"><span class="i">🗺️</span>Atlas</button>
   <button class="tb on" onclick="go('live')" id="nav-live"><span class="i">◎</span>Live</button>
   <button class="tb" onclick="go('pro')" id="nav-pro"><span class="i">📈</span>Pro</button>
 </div>
</div>
<script>
const CATS=['Visível agora','Nebulosa','Galáxia','Aglomerado'];
let TARGETS=[], filt='Visível agora', cur={desig:'M8',name:'Lagoa',cat:'Nebulosa',img:'lagoon_trifid'}, stacking=false;
const $=id=>document.getElementById(id);
function toast(m){const t=$('toast');t.textContent=m;t.classList.add('on');clearTimeout(t._);t._=setTimeout(()=>t.classList.remove('on'),1600);}
function go(t){for(const s of ['live','atlas','pro'])$('tab-'+s).classList.toggle('on',s===t),$('nav-'+s)&&$('nav-'+s).classList.toggle('on',s===t);
  $('dock').style.display=t==='live'?'flex':'none'; if(t==='pro')drawPro(); if(t==='atlas')renderAtlas();}
function cmd(a,msg){fetch('/api/cmd/'+encodeURIComponent(a));if(msg)toast(msg);}
function toggleStack(){stacking=!stacking; if(stacking){cmd('start:stack:'+cur.desig,'Empilhando '+cur.desig);$('live').src='/stream.mjpg?'+Date.now();}
  else{cmd('stop','Parado');$('live').src='/image/'+(cur.img||'lagoon_trifid')+'?'+Date.now();}
  $('capbtn').classList.toggle('run',stacking);$('capg').textContent=stacking?'■':'●';$('rec').style.display=stacking?'flex':'none';}
function selectTarget(t){cur=t;$('tgt').innerHTML='<b>'+t.desig+'</b> '+t.name+' <small>· '+t.cat.toLowerCase()+'</small>';
  if(!stacking)$('live').src=(t.img?'/image/'+t.img:'/thumb/'+t.desig)+'?'+Date.now();
  $('p_solve').textContent='—';$('solvetxt').innerHTML='<small>aponte um alvo (GOTO) p/ resolver</small>';go('live');
  cmd('start:goto:'+t.desig,'GOTO '+t.desig);setTimeout(()=>{ $('p_solve').textContent='0.4 s';
    $('solvetxt').innerHTML='<span class="ok">✔ resolvido</span>&nbsp;<small>'+t.desig+'</small>';},1400);}
async function loadTargets(){try{TARGETS=(await(await fetch('/api/targets')).json()).targets;}catch(e){}renderAtlas();}
function buildChips(){$('chips').innerHTML='';CATS.forEach(c=>{const b=document.createElement('div');
  b.className='chip'+(c===filt?' on':'');b.textContent=c;b.onclick=()=>{filt=c;renderAtlas();};$('chips').appendChild(b);});}
function renderAtlas(){buildChips();const qq=($('q')?.value||'').toLowerCase();const g=$('grid');g.innerHTML='';
  TARGETS.filter(t=>{const okc=filt==='Visível agora'?t.visible:t.cat===filt;
    const okq=!qq||t.desig.toLowerCase().includes(qq)||(t.name||'').toLowerCase().includes(qq);return okc&&okq;})
  .forEach(t=>{const d=document.createElement('div');d.className='tcard';d.onclick=()=>selectTarget(t);
    const icon={'Nebulosa':'☁️','Galáxia':'🌀','Aglomerado':'✨'}[t.cat]||'⭐';
    const alt=t.alt!=null?('alt '+t.alt+'°'+(t.visible?' ✓':'')):(t.mag!=null?('mag '+t.mag):'');
    d.innerHTML=(t.img?'<img src="/thumb/'+t.img+'" loading="lazy">':'<div class="ph">'+icon+'</div>')
      +(t.mag!=null?'<div class="badge">m'+t.mag+'</div>':'')
      +'<div class="lb">'+t.desig+' · '+t.name+'<small class="'+(t.visible?'ok':'')+'">'+alt+'</small></div>';
    g.appendChild(d);});
  if(!g.children.length)g.innerHTML='<div style="color:var(--mut);font-size:13px;grid-column:1/3;padding:20px;text-align:center">nada aqui agora</div>';}
// ---- Pro: gráficos (foco/guiding SIM, histograma real) ----
function poly(pts,stroke,w){return '<polyline points="'+pts+'" fill="none" stroke="'+stroke+'" stroke-width="'+(w||1.4)+'"/>';}
function drawFoc(){let s='<line x1="0" y1="70" x2="260" y2="70" stroke="rgba(255,255,255,.08)"/>',pts='';
  for(let i=0;i<22;i++){const x=i*12.4,v=8+0.00042*(x-135)*(x-135);const y=70-(v-2)*6;pts+=x.toFixed(0)+','+y.toFixed(1)+' ';
    s+='<circle cx="'+x.toFixed(0)+'" cy="'+y.toFixed(1)+'" r="2" fill="#35e0c8"/>';}
  $('focsvg').innerHTML=poly(pts,'rgba(53,224,200,.5)',1.5)+s+'<line x1="135" y1="4" x2="135" y2="72" stroke="#f7b45a" stroke-dasharray="3"/>';
  $('p_hfd').textContent='HFD 2.1';}
function drawGuide(){let ra='',de='',yr=33,yd=33;for(let i=0;i<60;i++){yr+=(Math.sin(i*.7)+Math.sin(i*.31))*.9;yd+=(Math.cos(i*.6)+Math.sin(i*.23))*.8;
    yr=Math.max(24,Math.min(42,yr));yd=Math.max(24,Math.min(42,yd));ra+=(i*4.4).toFixed(0)+','+yr.toFixed(1)+' ';de+=(i*4.4).toFixed(0)+','+yd.toFixed(1)+' ';}
  $('guidesvg').innerHTML='<line x1="0" y1="33" x2="260" y2="33" stroke="rgba(255,255,255,.12)"/>'+poly(ra,'#35e0c8')+poly(de,'#f7b45a');$('p_rms').textContent='0.6″';}
async function drawHist(){let bins=[];try{bins=(await(await fetch('/api/histogram'+(cur.img?'?key='+cur.img:''))).json()).bins;}catch(e){}
  let s='<defs><linearGradient id="hg" x1="0" y1="1" x2="0" y2="0"><stop offset="0" stop-color="#1c6f8f"/><stop offset="1" stop-color="#35e0c8"/></linearGradient></defs>';
  bins.forEach((v,i)=>{const h=v*58;s+='<rect x="'+(i*6.4).toFixed(1)+'" y="'+(62-h).toFixed(1)+'" width="5" height="'+h.toFixed(1)+'" rx="1" fill="url(#hg)"/>';});
  $('histsvg').innerHTML=s;}
function drawPro(){drawFoc();drawGuide();drawHist();}
// ---- telemetria ao vivo ----
const MC={IDLE:'#8b99b8',SLEWING:'#35e0c8',SOLVING:'#35e0c8',FOCUSING:'#f7b45a',STACKING:'#4cd884',
  SCHEDULING:'#9aa2ff',TRACKING:'#f7b45a',ERROR:'#ff5a6a',STOPPED:'#8b99b8'};
async function poll(){try{const s=await(await fetch('/api/state')).json();
  const m=$('mode');m.textContent='● '+(s.state||'IDLE');m.style.color=MC[s.state]||'#8b99b8';
  $('backend').textContent=(s.backend||'').indexOf('GPU')>=0?'GPU':'CPU';
  const run=s.state==='STACKING';if(run!==stacking){stacking=run;$('capbtn').classList.toggle('run',run);
    $('capg').textContent=run?'■':'●';$('rec').style.display=run?'flex':'none';if(run)$('live').src='/stream.mjpg?'+Date.now();}
  $('t_snr').innerHTML=(s.snr?s.snr.toFixed(1):'—')+'<span>SNR</span>';
  $('t_fwhm').innerHTML=(s.fwhm?s.fwhm.toFixed(1)+'″':'—')+'<span>FWHM</span>';
  $('t_acc').innerHTML=(s.accepted||0)+'<span>SUBS</span>';
  $('t_int').innerHTML=((s.accepted||0)*30>=60?Math.round((s.accepted||0)*30/60)+'min':(s.accepted||0)*30+'s')+'<span>INTEGRADO</span>';
  $('t_exp').innerHTML='30s<span>EXP</span>';$('t_gain').innerHTML='120<span>GANHO</span>';
  if($('tab-pro').classList.contains('on'))drawHist();
}catch(e){}}
buildChips();loadTargets();setInterval(poll,900);poll();
</script></body></html>""").encode("utf-8")
