"""Live view no navegador — stream MJPEG + estatísticas, SEM dependências extras.

Usa apenas a stdlib (http.server). O orquestrador publica o frame empilhado atual no
FrameHub; o navegador mostra `/stream.mjpg` (atualiza sozinho) e consulta `/stats`.
UI = painel de controle (fase/estado, fila, SNR em destaque). Ver docs/03 e docs/16.
"""
from __future__ import annotations
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


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


_PAGE = b"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telescopio Jetson - Painel</title>
<style>
 :root{color-scheme:dark;
   --bg:#070b14;--panel:#0f1626;--panel2:#0b1120;--line:#1e2842;--tx:#e9eefb;--mut:#7f8bab;
   --cy:#2fe0c0;--am:#f5a94a;--gr:#46d17a;--red:#ff5d6c;--vi:#9aa0ff;--ha:#e5609d}
 *{box-sizing:border-box}
 body{margin:0;font:15px/1.5 system-ui,Segoe UI,sans-serif;color:var(--tx);
   background:radial-gradient(1200px 700px at 80% -10%,#111d33 0,transparent 60%),
     radial-gradient(900px 600px at -10% 110%,#141026 0,transparent 55%),var(--bg)}
 .mono{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}
 header{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;
   padding:14px 20px;border-bottom:1px solid var(--line);background:rgba(9,13,22,.6);
   backdrop-filter:blur(6px);position:sticky;top:0;z-index:5}
 .brand{font-weight:800;letter-spacing:.02em;display:flex;align-items:center;gap:10px}
 .brand .b{font:600 10px ui-monospace,monospace;letter-spacing:.14em;color:#0a0f1a;
   background:var(--cy);border-radius:5px;padding:2px 7px}
 .pill{font:700 12px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;
   color:#08110c;background:var(--mut);border-radius:99px;padding:6px 14px;transition:background .3s}
 .ctrl{display:flex;gap:10px;align-items:center}
 .btn{font:600 12px ui-monospace,monospace;color:var(--tx);background:var(--panel);
   border:1px solid var(--line);border-radius:99px;padding:7px 14px;cursor:pointer}
 .btn:hover{border-color:var(--red);color:var(--red)}
 .cbar{display:flex;flex-direction:column;gap:10px;padding:14px 20px;
   border-bottom:1px solid var(--line);background:var(--panel2)}
 .cgroup{display:flex;gap:8px;flex-wrap:wrap;align-items:center;padding:10px 12px;
   border:1px solid var(--line);border-left:3px solid var(--cy);border-radius:10px;
   background:rgba(47,224,192,.04)}
 .cgroup.real{border-left-color:var(--gr);background:rgba(70,209,122,.05)}
 .cglab{font:700 10px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;
   color:var(--cy);margin-right:4px}
 .cgroup.real .cglab{color:var(--gr)}
 .cbar select{background:var(--panel);color:var(--tx);border:1px solid var(--line);
   border-radius:8px;padding:6px 10px;font:600 12px ui-monospace,monospace}
 .cbtn{font:600 12px ui-monospace,monospace;color:#08110c;background:var(--cy);border:0;
   border-radius:8px;padding:8px 12px;cursor:pointer}
 .cgroup.real .cbtn{background:var(--gr)}
 .cbtn:hover{filter:brightness(1.12)}
 .strip{display:flex;gap:18px;align-items:center;flex-wrap:wrap;padding:12px 20px;
   border-bottom:1px solid var(--line);background:var(--panel2)}
 .strip .phase{font:600 12px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
 .strip .phase b{color:var(--tx)}
 .q{display:flex;align-items:center;gap:10px;margin-left:auto}
 .qbar{width:180px;height:8px;border-radius:99px;background:#0a1020;border:1px solid var(--line);overflow:hidden}
 .qfill{height:100%;width:0;background:linear-gradient(90deg,var(--vi),var(--cy));transition:width .5s}
 .qtxt{font:600 12px ui-monospace,monospace;color:var(--mut)}
 main{display:grid;grid-template-columns:1fr 300px;gap:18px;padding:18px;max-width:1200px;margin:0 auto}
 .view{position:relative;background:#000;border:1px solid var(--line);border-radius:16px;overflow:hidden;
   box-shadow:0 20px 60px rgba(0,0,0,.5)}
 .view img{width:100%;display:block;min-height:220px}
 .live{position:absolute;top:12px;left:12px;display:flex;align-items:center;gap:7px;
   font:700 11px ui-monospace,monospace;letter-spacing:.14em;color:#fff;
   background:rgba(0,0,0,.45);border:1px solid rgba(255,255,255,.15);border-radius:99px;padding:5px 11px}
 .live .dot{width:8px;height:8px;border-radius:50%;background:var(--red);animation:pulse 1.4s infinite}
 @keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
 @media (prefers-reduced-motion:reduce){.live .dot{animation:none}}
 aside{display:flex;flex-direction:column;gap:12px}
 .hero{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);
   border-radius:16px;padding:18px 20px}
 .hero .k{font:600 11px ui-monospace,monospace;letter-spacing:.14em;text-transform:uppercase;color:var(--mut)}
 .hero .v{font:800 2.6rem ui-monospace,monospace;color:var(--gr);font-variant-numeric:tabular-nums;line-height:1.1}
 .grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .stat{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:13px 15px}
 .stat .k{font:600 10px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--mut)}
 .stat .v{font:700 1.6rem ui-monospace,monospace;color:var(--tx);font-variant-numeric:tabular-nums}
 .stat.ok .v{color:var(--cy)} .stat.warn .v{color:var(--am)}
 .foc{display:flex;justify-content:space-between;align-items:center;background:var(--panel);
   border:1px solid var(--line);border-radius:14px;padding:12px 15px;
   font:600 12px ui-monospace,monospace;color:var(--mut)}
 .foc b{color:var(--tx);font-size:1.05rem}
 footer{color:var(--mut);text-align:center;padding:18px;font:600 11px ui-monospace,monospace;letter-spacing:.1em}
 @media (max-width:760px){main{grid-template-columns:1fr}.qbar{width:120px}}
</style></head><body>
<header>
 <div class="brand"><span class="b">&#x1F52D; JETSON</span> Telescopio Robotico</div>
 <div class="ctrl">
   <button class="btn" onclick="fetch('/cmd/stop')" title="Encerrar a sessao">&#9209; Parar</button>
   <div class="pill" id="pill">-</div>
 </div>
</header>
<div class="strip">
 <div class="phase">FASE: <b id="phase">-</b></div>
 <div class="q" id="qwrap" style="display:none">
   <div class="qbar"><div class="qfill" id="qfill"></div></div><span class="qtxt" id="qtxt"></span>
 </div>
 <div class="phase" style="margin-left:auto" id="bwrap">BACKEND: <b id="backend">-</b></div>
</div>
<div class="cbar">
 <div class="cgroup">
   <span class="cglab">Simulador &middot; ceu de teste</span>
   <select id="tgt"><option>M31</option><option>M42</option><option>M45</option></select>
   <button class="cbtn" onclick="go('goto')" title="Aponta em RA/DEC: slew->solve->sync">GOTO (RA/DEC)</button>
   <button class="cbtn" onclick="go('stack')">Empilhar</button>
   <button class="cbtn" onclick="go('autofind')">Auto-find</button>
   <button class="cbtn" onclick="cmd('start:scheduler')">Agendador</button>
   <button class="cbtn" onclick="go('mosaic')">Mosaico</button>
   <button class="cbtn" onclick="cmd('start:tracking')">Rastrear</button>
   <button class="cbtn" onclick="cmd('start:night')">Noite</button>
 </div>
 <div class="cgroup real">
   <span class="cglab">Foto real &middot; nao usa o seletor acima</span>
   <button class="cbtn" onclick="cmd('start:realdata')" title="Empilha uma FOTO REAL do aglomerado M67">Dados reais (M67)</button>
 </div>
</div>
<main>
 <section class="view">
   <div class="live"><span class="dot"></span>AO VIVO</div>
   <img src="/stream.mjpg" alt="stack ao vivo">
 </section>
 <aside>
   <div class="hero"><div class="k">Ganho de SNR</div><div class="v" id="snr">-</div></div>
   <div class="grid">
     <div class="stat"><div class="k">FWHM (px)</div><div class="v" id="fwhm">-</div></div>
     <div class="stat"><div class="k">Erro apont.</div><div class="v" id="err">-</div></div>
     <div class="stat ok"><div class="k">Empilhados</div><div class="v" id="acc">0</div></div>
     <div class="stat warn"><div class="k">Rejeitados</div><div class="v" id="rej">0</div></div>
   </div>
   <div class="foc"><span>FOCALIZADOR</span><b id="focus">-</b></div>
 </aside>
</main>
<footer>TELESCOPIO JETSON &middot; painel ao vivo</footer>
<script>
 function cmd(x){fetch('/cmd/'+x);}
 function go(m){cmd('start:'+m+':'+document.getElementById('tgt').value);}
 const COL={IDLE:'#7f8bab',SLEWING:'#2fe0c0',SOLVING:'#2fe0c0',FOCUSING:'#f5a94a',
   STACKING:'#46d17a',SCHEDULING:'#9aa0ff',TRACKING:'#e5609d',ERROR:'#ff5d6c',STOPPED:'#7f8bab'};
 async function poll(){try{const s=await(await fetch('/stats')).json();
   const p=document.getElementById('pill');
   p.textContent=s.phase||'-'; p.style.background=COL[s.state]||'#7f8bab';
   document.getElementById('phase').textContent=(s.phase||'-')+(s.target?(' \\u00b7 '+s.target):'');
   document.getElementById('backend').textContent=((s.backend||'').indexOf('GPU')>=0)?'GPU (CuPy)':'CPU (NumPy)';
   document.getElementById('snr').textContent=s.snr?(s.snr.toFixed(2)+'x'):'-';
   document.getElementById('fwhm').textContent=s.fwhm?s.fwhm.toFixed(2):'-';
   document.getElementById('err').textContent=(s.error_px||s.error_px===0)?(s.error_px.toFixed(1)+' '+(s.err_unit||'px')):'-';
   document.getElementById('acc').textContent=s.accepted||0;
   document.getElementById('rej').textContent=s.rejected||0;
   document.getElementById('focus').textContent=s.focus_pos||'-';
   const qt=s.queue_total||0,qd=s.queue_done||0;
   document.getElementById('qwrap').style.display=qt?'flex':'none';
   document.getElementById('qfill').style.width=qt?((qd/qt*100)+'%'):'0%';
   document.getElementById('qtxt').textContent=qt?(qd+'/'+qt+' alvos'):'';
 }catch(e){}}
 setInterval(poll,700);poll();
</script></body></html>"""


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
