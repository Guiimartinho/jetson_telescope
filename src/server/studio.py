"""Estúdio de Processamento — a experiência de PRODUTO (estilo DWARF, mas aberto e ajustável).

Escolhe um alvo, mostra a imagem REAL empilhada em alta resolução e deixa ajustar ao vivo com
dezenas de controles (stretch, cor, saturação, redução de estrela, denoise, nitidez, presets de
1 clique). Renderiza sempre a partir do stack LINEAR float32 (`postproc/render`), preservando o
dynamic range. Stdlib só (http.server). Na Jetson os passos pesados migram p/ cuCIM/GraXpert→TensorRT.
Ver docs/24.
"""
from __future__ import annotations
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import numpy as np
import cv2

from ..postproc.render import RenderParams, render, PRESETS

# Catálogo de alvos (como o "escolher alvo" da DWARF). "stack" = FITS linear float32 (HxWx3 ou 3xHxW).
CATALOG = {
    "lagoon_trifid": {"name": "M8 Lagoa + M20 Trifida", "kind": "nebulosa",
                      "stack": "data/stacks/lagoon_trifid_linear.fits",
                      "subs": 15, "exp": "45 min", "cam": "ASI2600MC (dado real)"},
    "rosette": {"name": "NGC2244 Roseta", "kind": "nebulosa",
                "stack": "data/stacks/rosette_linear.fits",
                "subs": 50, "exp": "~8 min", "cam": "Stellina IMX178 (dado real)"},
    "m51": {"name": "M51 Whirlpool (galaxia)", "kind": "galaxia",
            "stack": "data/stacks/m51_linear.fits",
            "subs": 50, "exp": "~8 min", "cam": "Stellina IMX178 (dado real)"},
}
# vitrine de produto: alvos que chegam com a câmera (mostrados bloqueados)
LOCKED = [("andromeda", "M31 Andrômeda", "galáxia"), ("orion", "M42 Órion", "nebulosa"),
          ("pleiades", "M45 Plêiades", "aglomerado")]


def _load_linear(path):
    from astropy.io import fits
    arr = np.asarray(fits.open(path)[0].data, dtype=np.float32)
    if arr.ndim == 3 and arr.shape[0] == 3:            # 3xHxW -> HxWx3
        arr = np.moveaxis(arr, 0, 2)
    elif arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    return arr


class Studio:
    """Mantém os stacks lineares em memória e renderiza sob demanda."""
    def __init__(self, preview_max=1500):
        self.preview_max = preview_max
        self._full = {}       # key -> full linear
        self._prev = {}       # key -> preview linear (menor, p/ ajuste rápido)
        self._lock = threading.Lock()

    def _ensure(self, key):
        with self._lock:
            if key in self._prev:
                return True
            meta = CATALOG.get(key)
            if not meta or not os.path.exists(meta["stack"]):
                return False
            full = _load_linear(meta["stack"])
            h, w = full.shape[:2]
            s = self.preview_max / max(h, w)
            prev = (cv2.resize(full, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
                    if s < 1.0 else full.copy())
            self._full[key] = full
            self._prev[key] = prev
            return True

    def render_jpeg(self, key, params: RenderParams, full=False, quality=90):
        if not self._ensure(key):
            return None
        base = self._full[key] if full else self._prev[key]
        rgb = render(base, params)
        ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
                               [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None


def _make_handler(studio: Studio):
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
            if u.path in ("/", "/index.html"):
                self._send(200, "text/html; charset=utf-8", _PAGE)
                return
            if u.path == "/targets":
                # só lista alvos cujo stack já existe (evita 404 em alvo ainda não processado)
                data = {"available": {k: {kk: v[kk] for kk in ("name", "kind", "subs", "exp", "cam")}
                                      for k, v in CATALOG.items() if os.path.exists(v["stack"])},
                        "locked": [{"key": k, "name": n, "kind": kd} for k, n, kd in LOCKED],
                        "presets": list(PRESETS.keys())}
                self._send(200, "application/json", json.dumps(data).encode())
                return
            if u.path in ("/render", "/download"):
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                key = q.pop("target", next(iter(CATALOG)))
                if q.get("preset") in PRESETS:
                    params = PRESETS[q["preset"]]
                else:
                    params = RenderParams.from_query(q)
                full = u.path == "/download"
                jpg = studio.render_jpeg(key, params, full=full, quality=95 if full else 88)
                if jpg is None:
                    self._send(404, "text/plain", b"alvo indisponivel")
                    return
                extra = {"Content-Disposition": f'attachment; filename="{key}.jpg"'} if full else \
                        {"Cache-Control": "no-store"}
                self._send(200, "image/jpeg", jpg, extra)
                return
            self._send(404, "text/plain", b"nao encontrado")
    return H


class StudioServer:
    def __init__(self, host="127.0.0.1", port=8010, preview_max=1500):
        self.studio = Studio(preview_max=preview_max)
        self.httpd = ThreadingHTTPServer((host, port), _make_handler(self.studio))
        self.host, self.port = host, port

    def serve_forever(self):
        self.httpd.serve_forever()

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()


# ------------------------------------------------------------------ a página
_PAGE = b"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telescopio Jetson - Estudio</title>
<style>
 :root{color-scheme:dark;--bg:#05070d;--pan:#0e1524;--pan2:#0a1020;--line:#1d2740;--tx:#eaf0fb;
   --mut:#8090b0;--cy:#31e0c4;--gr:#4cd884;--am:#f6b45a;--vi:#9aa2ff}
 *{box-sizing:border-box} html,body{height:100%}
 body{margin:0;font:14px/1.5 system-ui,"Segoe UI",sans-serif;color:var(--tx);background:var(--bg);
   display:flex;flex-direction:column;overflow:hidden}
 .mono{font-family:ui-monospace,"Cascadia Mono",Consolas,monospace}
 header{display:flex;align-items:center;gap:14px;padding:10px 16px;border-bottom:1px solid var(--line);
   background:rgba(9,13,22,.8);backdrop-filter:blur(6px);flex-wrap:wrap;z-index:5}
 .brand{font-weight:800;letter-spacing:.02em;display:flex;align-items:center;gap:9px}
 .brand .b{font:600 9px ui-monospace,monospace;letter-spacing:.14em;color:#04120e;background:var(--cy);
   border-radius:5px;padding:2px 7px}
 select{background:var(--pan);color:var(--tx);border:1px solid var(--line);border-radius:8px;
   padding:7px 10px;font:600 13px ui-monospace,monospace}
 .presets{display:flex;gap:6px;margin-left:auto;flex-wrap:wrap}
 .chip{font:600 11px ui-monospace,monospace;color:var(--tx);background:var(--pan);border:1px solid var(--line);
   border-radius:20px;padding:6px 12px;cursor:pointer;text-transform:capitalize}
 .chip:hover{border-color:var(--cy);color:var(--cy)}
 .dl{font:600 11px ui-monospace,monospace;color:#04120e;background:var(--gr);border:0;border-radius:20px;
   padding:7px 13px;cursor:pointer}
 main{flex:1;display:flex;min-height:0}
 .view{flex:1;position:relative;display:flex;align-items:center;justify-content:center;overflow:hidden;
   background:radial-gradient(900px 500px at 50% 40%,#0b1526 0,#05070d 70%)}
 .view img{max-width:100%;max-height:100%;object-fit:contain;box-shadow:0 10px 60px rgba(0,0,0,.6)}
 .badge{position:absolute;left:16px;bottom:14px;font:600 11px ui-monospace,monospace;color:var(--mut);
   background:rgba(9,13,22,.7);border:1px solid var(--line);border-radius:8px;padding:7px 11px}
 .badge b{color:var(--tx)} .busy{position:absolute;top:14px;right:16px;font:600 11px ui-monospace,monospace;
   color:var(--cy);opacity:0;transition:opacity .2s} .busy.on{opacity:1}
 aside{width:290px;border-left:1px solid var(--line);background:var(--pan2);overflow-y:auto;padding:14px}
 .grp{margin-bottom:8px} .grp h3{font:700 10px ui-monospace,monospace;letter-spacing:.13em;
   text-transform:uppercase;color:var(--cy);margin:14px 0 8px}
 .row{display:grid;grid-template-columns:1fr auto;gap:4px;align-items:center;margin:9px 0 3px}
 .row label{font-size:12.5px;color:var(--mut)} .row .val{font:600 11px ui-monospace,monospace;color:var(--tx)}
 input[type=range]{width:100%;accent-color:var(--cy);background:transparent}
 .tgl{display:flex;align-items:center;gap:8px;margin:10px 0;font-size:12.5px;color:var(--mut);cursor:pointer}
 .tgl input{accent-color:var(--gr);width:16px;height:16px}
 .reset{width:100%;margin-top:12px;font:600 11px ui-monospace,monospace;color:var(--tx);background:var(--pan);
   border:1px solid var(--line);border-radius:8px;padding:9px;cursor:pointer}
 .reset:hover{border-color:var(--am);color:var(--am)}
 @media(max-width:760px){main{flex-direction:column}aside{width:100%;border-left:0;border-top:1px solid var(--line)}}
</style></head><body>
<header>
 <div class="brand"><span class="b">JETSON</span> Estudio</div>
 <select id="target" title="Alvo"></select>
 <div class="presets" id="presets"></div>
 <button class="dl" onclick="dl()">&#8681; Alta resolucao</button>
</header>
<main>
 <div class="view">
   <img id="img" alt="imagem">
   <div class="busy mono" id="busy">processando...</div>
   <div class="badge mono" id="badge">-</div>
 </div>
 <aside id="ctrl"></aside>
</main>
<script>
const SL=[
 {g:'Brilho e stretch'},
 {k:'stretch',l:'Stretch',min:1,max:30,step:.5},
 {k:'black',l:'Ponto preto',min:0,max:.3,step:.005},
 {k:'white',l:'Ponto branco',min:98,max:100,step:.05},
 {k:'gamma',l:'Gamma',min:.5,max:2.5,step:.05},
 {g:'Cor'},
 {k:'scnr',l:'Remover verde (SCNR)',min:0,max:1,step:.05},
 {k:'saturation',l:'Saturacao',min:0,max:3,step:.05},
 {k:'r_gain',l:'Vermelho',min:.5,max:2,step:.02},
 {k:'g_gain',l:'Verde',min:.5,max:2,step:.02},
 {k:'b_gain',l:'Azul',min:.5,max:2,step:.02},
 {g:'Detalhe e ruido'},
 {k:'deconv',l:'Deconvolucao (detalhe)',min:0,max:20,step:1},
 {k:'denoise',l:'Denoise (croma)',min:0,max:1,step:.05},
 {k:'ldenoise',l:'Denoise (luminancia)',min:0,max:1,step:.05},
 {k:'star_reduce',l:'Reduzir estrelas',min:0,max:1,step:.05},
 {k:'sharpen',l:'Nitidez',min:0,max:1,step:.02},
];
const DEF={stretch:10,black:0,white:99.7,gamma:1,scnr:1,saturation:1.8,r_gain:1.1,g_gain:1,b_gain:1,
 deconv:0,denoise:.35,ldenoise:0,star_reduce:0,sharpen:.12,remove_grad:false};
let P={...DEF}, target='', meta={}, timer=null;

function build(presets){
 const a=document.getElementById('ctrl'); a.innerHTML='';
 for(const s of SL){
   if(s.g){const h=document.createElement('div');h.className='grp';
     h.innerHTML='<h3>'+s.g+'</h3>';a.appendChild(h);continue;}
   const d=document.createElement('div');
   d.innerHTML='<div class="row"><label>'+s.l+'</label><span class="val" id="v_'+s.k+'"></span></div>'+
     '<input type="range" id="r_'+s.k+'" min="'+s.min+'" max="'+s.max+'" step="'+s.step+'">';
   a.appendChild(d);
   const r=d.querySelector('input');
   r.value=P[s.k]; document.getElementById('v_'+s.k).textContent=(+P[s.k]).toFixed(2);
   r.oninput=()=>{P[s.k]=+r.value;document.getElementById('v_'+s.k).textContent=(+r.value).toFixed(2);draw();};
 }
 for(const [k,l] of [['remove_grad','Remover gradiente (extracao de fundo)']]){
   const t=document.createElement('label');t.className='tgl';
   t.innerHTML='<input type="checkbox" id="c_'+k+'"'+(P[k]?' checked':'')+'> '+l;
   a.appendChild(t);
   t.querySelector('input').onchange=e=>{P[k]=e.target.checked;draw();};
 }
 const b=document.createElement('button');b.className='reset';b.textContent='Restaurar padrao';
 b.onclick=()=>{P={...DEF};build(presets);draw();};a.appendChild(b);
 const pc=document.getElementById('presets');pc.innerHTML='';
 for(const name of presets){const c=document.createElement('div');c.className='chip';c.textContent=name;
   c.onclick=()=>applyPreset(name);pc.appendChild(c);}
}
function qs(extra){const o={target,...P,...(extra||{})};
 return Object.entries(o).map(([k,v])=>k+'='+encodeURIComponent(v)).join('&');}
function draw(){
 if(timer)clearTimeout(timer);
 timer=setTimeout(()=>{
   document.getElementById('busy').classList.add('on');
   const im=new Image();
   im.onload=()=>{document.getElementById('img').src=im.src;document.getElementById('busy').classList.remove('on');};
   im.src='/render?'+qs({t:Date.now()});
 },120);
}
async function applyPreset(name){
 const im=new Image();document.getElementById('busy').classList.add('on');
 im.onload=()=>{document.getElementById('img').src=im.src;document.getElementById('busy').classList.remove('on');};
 im.src='/render?target='+target+'&preset='+name+'&t='+Date.now();
 // nao mexe nos sliders (preset e server-side); so mostra
}
function dl(){window.open('/download?'+qs(),'_blank');}
async function init(){
 const d=await(await fetch('/targets')).json();
 const sel=document.getElementById('target');
 for(const [k,m] of Object.entries(d.available)){
   const o=document.createElement('option');o.value=k;o.textContent=m.name;sel.appendChild(o);meta[k]=m;}
 for(const l of d.locked){const o=document.createElement('option');o.value='';o.disabled=true;
   o.textContent=l.name+'  (com a camera)';sel.appendChild(o);}
 sel.onchange=()=>{target=sel.value;setBadge();draw();};
 target=Object.keys(d.available)[0];
 build(d.presets); setBadge(); draw();
}
function setBadge(){const m=meta[target]||{};
 document.getElementById('badge').innerHTML='<b>'+(m.name||'')+'</b> &middot; '+(m.subs||'?')+
   ' subs &middot; '+(m.exp||'')+' &middot; '+(m.cam||'');}
init();
</script></body></html>"""
