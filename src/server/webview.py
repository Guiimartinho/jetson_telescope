"""Painel de controle no navegador — stream MJPEG + estatísticas, SEM dependências extras.

Usa apenas a stdlib (http.server) e o design system `ui_kit` (tema coerente + ícones SVG, NUNCA emoji).
O orquestrador publica o frame empilhado atual no FrameHub; o navegador mostra `/stream.mjpg` e consulta
`/stats`. Roda todos os modos (empilhar, auto-find, agendador, mosaico, rastrear, noite). Ver docs/19, 33.
"""
from __future__ import annotations
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import ui_kit as uik


class FrameHub:
    """Estado compartilhado thread-safe entre o pipeline e o servidor web (frames, stats, comandos)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._jpeg = None
        self._stats = {}
        self._cmds = []

    def update(self, jpeg: bytes, stats: dict):
        with self._lock:
            if jpeg:
                self._jpeg = jpeg
            self._stats = dict(stats)

    def get(self):
        with self._lock:
            return self._jpeg, dict(self._stats)

    def push_command(self, cmd: str):
        with self._lock:
            self._cmds.append(cmd)

    def pop_commands(self):
        with self._lock:
            c, self._cmds = self._cmds, []
            return c


_PANEL_CSS = """
#page{max-width:1180px;margin:0 auto}
header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;padding:13px 20px;
  border-bottom:1px solid var(--line);position:sticky;top:0;background:rgba(6,8,14,.85);backdrop-filter:blur(8px);z-index:5}
header .r{display:flex;align-items:center;gap:12px}
.pill{font:700 11px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:#04120e;background:var(--mut);
  border-radius:99px;padding:6px 15px;transition:background .3s}
.strip{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:11px 20px;border-bottom:1px solid var(--line);background:var(--surf2)}
.strip .ph{font:600 12px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}.strip .ph b{color:var(--tx)}
.q{display:flex;align-items:center;gap:10px;margin-left:auto}
.qbar{width:170px;height:8px;border-radius:99px;background:var(--surf);border:1px solid var(--line);overflow:hidden}
.qfill{height:100%;width:0;background:linear-gradient(90deg,var(--vi),var(--ac));transition:width .5s}
.qtxt{font:600 12px var(--mono);color:var(--mut)}
.ctrl{padding:16px 20px;display:flex;flex-direction:column;gap:11px}
.cg{display:flex;gap:9px;flex-wrap:wrap;align-items:center;padding:13px 15px;border:1px solid var(--line);
  border-left:3px solid var(--ac);border-radius:var(--r);background:var(--surf)}
.cg.real{border-left-color:var(--gr)}
.cg .t{font:700 10px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--ac);margin-right:4px}.cg.real .t{color:var(--gr)}
select{background:var(--elev);color:var(--tx);border:1px solid var(--line);border-radius:var(--r2);padding:9px 12px;font:600 13px var(--mono)}
.btn svg.ic{width:17px;height:17px}
.cg.real .btn:hover{border-color:var(--gr)}
main{display:grid;grid-template-columns:1fr 320px;gap:18px;padding:0 20px 30px}
@media(max-width:820px){main{grid-template-columns:1fr}.qbar{width:120px}}
.view{position:relative;overflow:hidden;background:#000}.view img{width:100%;display:block;min-height:240px}
.livebadge{position:absolute;top:12px;left:12px;display:flex;align-items:center;gap:7px;font:700 11px var(--mono);
  letter-spacing:.14em;background:rgba(4,7,14,.55);border:1px solid var(--line);border-radius:99px;padding:5px 12px}
.livebadge .d{width:8px;height:8px;border-radius:50%;background:var(--bad);animation:pl 1.4s infinite}
@keyframes pl{0%,100%{opacity:1}50%{opacity:.25}}@media(prefers-reduced-motion:reduce){.livebadge .d{animation:none}}
aside{display:flex;flex-direction:column;gap:12px}
.hero{padding:18px 20px}.hero .k{font:600 11px var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
.hero .v{font:800 2.7rem var(--mono);color:var(--gr);font-variant-numeric:tabular-nums;line-height:1.1}
.sg{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.stat{padding:13px 15px}.stat .k{font:600 10px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--mut)}
.stat .v{font:700 1.55rem var(--mono);color:var(--tx);font-variant-numeric:tabular-nums}.stat.ok .v{color:var(--ac)}.stat.warn .v{color:var(--warn)}
.foc{display:flex;justify-content:space-between;align-items:center;padding:13px 16px;font:600 12px var(--mono);color:var(--mut)}
.foc b{color:var(--tx);font-size:1.05rem}
footer{color:var(--dim);text-align:center;padding:16px;font:600 10px var(--mono);letter-spacing:.14em}
"""


def _modebtns():
    b = [("goto", "reticle", "GOTO (RA/DEC)"), ("stack", "layers", "Empilhar"), ("autofind", "search", "Auto-find")]
    c = [("scheduler", "list", "Agendador"), ("mosaic", "grid", "Mosaico"),
         ("tracking", "satellite", "Rastrear"), ("night", "moon", "Noite")]
    def mk(mode, ic, lab, use_go):
        call = f"go('{mode}')" if use_go else f"cmd('start:{mode}')"
        return f'<button class="btn" onclick="{call}">{uik.icon(ic, 17)}{lab}</button>'
    h = mk("goto", "reticle", "GOTO (RA/DEC)", True) + mk("stack", "layers", "Empilhar", True) \
        + mk("autofind", "search", "Auto-find", True)
    for mode, ic, lab in c:
        h += mk(mode, ic, lab, False)
    return h


_TEMPLATE = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#04060c">
<title>Jetson Telescopio · Painel</title><style>__CSS__</style></head><body><div id="page">
<header>__BRAND__<div class="r"><div class="pill" id="pill">—</div>
  <button class="btn" onclick="cmd('stop')">__IC_STOP__ Parar</button></div></header>
<div class="strip"><div class="ph">FASE: <b id="phase">—</b></div>
  <div class="ph">BACKEND: <b id="backend">—</b></div>
  <div class="q" id="qwrap" style="display:none"><div class="qbar"><div class="qfill" id="qfill"></div></div><span class="qtxt" id="qtxt"></span></div></div>
<div class="ctrl">
  <div class="cg"><span class="t">Simulador · céu de teste</span>
    <select id="tgt"><option>M31</option><option>M42</option><option>M45</option></select>__MODEBTNS__</div>
  <div class="cg real"><span class="t">Foto real · dado astronômico</span>
    <button class="btn" onclick="cmd('start:realdata')">__IC_CAM__ Dados reais (M67)</button></div>
</div>
<main>
  <section class="card view"><div class="livebadge"><span class="d"></span>AO VIVO</div><img src="/stream.mjpg" alt="stack ao vivo"></section>
  <aside>
    <div class="card hero"><div class="k">Ganho de SNR</div><div class="v" id="snr">—</div></div>
    <div class="sg">
      <div class="card stat"><div class="k">FWHM (px)</div><div class="v" id="fwhm">—</div></div>
      <div class="card stat"><div class="k">Erro apont.</div><div class="v" id="err">—</div></div>
      <div class="card stat ok"><div class="k">Empilhados</div><div class="v" id="acc">0</div></div>
      <div class="card stat warn"><div class="k">Rejeitados</div><div class="v" id="rej">0</div></div>
    </div>
    <div class="card foc"><span>FOCALIZADOR</span><b id="focus">—</b></div>
  </aside>
</main>
<footer>JETSON TELESCOPIO · PAINEL DE CONTROLE</footer></div>
<script>
function cmd(x){fetch('/cmd/'+x);}
function go(m){cmd('start:'+m+':'+document.getElementById('tgt').value);}
const COL={IDLE:'#8492b0',SLEWING:'#33ddc4',SOLVING:'#33ddc4',FOCUSING:'#f5b95c',STACKING:'#49d17e',
  SCHEDULING:'#9aa2ff',TRACKING:'#f5b95c',ERROR:'#ff5d6c',STOPPED:'#8492b0'};
async function poll(){try{const s=await(await fetch('/stats')).json();const p=document.getElementById('pill');
  p.textContent=s.phase||'—';p.style.background=COL[s.state]||'#8492b0';
  document.getElementById('phase').textContent=(s.phase||'—')+(s.target?(' · '+s.target):'');
  document.getElementById('backend').textContent=((s.backend||'').indexOf('GPU')>=0)?'GPU (CuPy)':'CPU (NumPy)';
  document.getElementById('snr').textContent=s.snr?(s.snr.toFixed(2)+'x'):'—';
  document.getElementById('fwhm').textContent=s.fwhm?s.fwhm.toFixed(2):'—';
  document.getElementById('err').textContent=(s.error_px||s.error_px===0)?(s.error_px.toFixed(1)+' '+(s.err_unit||'px')):'—';
  document.getElementById('acc').textContent=s.accepted||0;document.getElementById('rej').textContent=s.rejected||0;
  document.getElementById('focus').textContent=s.focus_pos||'—';
  const qt=s.queue_total||0,qd=s.queue_done||0;document.getElementById('qwrap').style.display=qt?'flex':'none';
  document.getElementById('qfill').style.width=qt?((qd/qt*100)+'%'):'0%';document.getElementById('qtxt').textContent=qt?(qd+'/'+qt+' alvos'):'';
}catch(e){}}
setInterval(poll,700);poll();
</script></body></html>"""


def _build_page():
    return (_TEMPLATE
            .replace("__CSS__", uik.css() + _PANEL_CSS)
            .replace("__BRAND__", uik.brand("PAINEL"))
            .replace("__IC_STOP__", uik.icon("power", 16))
            .replace("__IC_CAM__", uik.icon("camera", 17))
            .replace("__MODEBTNS__", _modebtns())).encode("utf-8")


_PAGE = _build_page()


def _make_handler(hub: FrameHub, on_command=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", _PAGE)
            elif self.path == "/stats":
                _, st = hub.get()
                self._send(200, "application/json", json.dumps(st).encode())
            elif self.path == "/stream.mjpg":
                self._stream()
            elif self.path.startswith("/cmd/"):
                action = self.path[len("/cmd/"):]
                if on_command is not None:              # painel de controle (run_app)
                    on_command(action)
                else:                                   # scripts standalone (só 'stop')
                    hub.push_command(action)
                self._send(200, "application/json", b'{"ok":true}')
            else:
                self._send(404, "text/plain", b"nao encontrado")

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                while True:
                    jpeg, _ = hub.get()
                    if jpeg:
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                         b"Content-Length: " + str(len(jpeg)).encode() +
                                         b"\r\n\r\n" + jpeg + b"\r\n")
                    time.sleep(0.2)
            except (BrokenPipeError, ConnectionResetError):
                pass
    return Handler


class WebView:
    def __init__(self, hub: FrameHub, host="0.0.0.0", port=8000, on_command=None):
        self.httpd = ThreadingHTTPServer((host, port), _make_handler(hub, on_command))
        self.httpd.daemon_threads = True
        self.host, self.port = host, port

    def start(self):
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        try:
            self.httpd.shutdown()
        except Exception:
            pass
