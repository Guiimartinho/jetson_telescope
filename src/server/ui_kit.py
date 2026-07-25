"""Design system compartilhado das 3 UIs (console, estúdio, painel).

Identidade coerente do produto: tema escuro "espaço profundo", tipografia de instrumento (mono p/
dados), e um conjunto de **ícones SVG desenhados à mão** (NUNCA emoji) que remetem ao projeto —
retículo, diafragma de foco, obturador, mapa estelar, satélite, planeta, nebulosa, galáxia. Tudo
`currentColor` (herda a cor do contexto). `css()` devolve o CSS base; `icon(nome)` o SVG; `MARK` a logo.
"""
from __future__ import annotations

# ---------------------------------------------------------------- tokens + base
_CSS = """
:root{
  color-scheme:dark;
  --bg:#04060c; --surf:#0a0f1b; --surf2:#0d1526; --elev:rgba(255,255,255,.04);
  --line:rgba(150,172,214,.13); --line2:rgba(150,172,214,.08);
  --tx:#e9eefb; --mut:#8492b0; --dim:#59677f;
  --ac:#33ddc4; --ac2:#1a9d8c; --gold:#f5b95c; --vi:#9aa2ff; --ok:#49d17e; --warn:#f5b95c; --bad:#ff5d6c;
  --r:14px; --r2:11px; --sh:0 18px 50px rgba(0,0,0,.55);
  --mono:ui-monospace,"Cascadia Mono","SF Mono",Consolas,monospace;
  --sans:system-ui,"Segoe UI",-apple-system,sans-serif;
}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);font:15px/1.5 var(--sans)}
.mono{font-family:var(--mono)}
svg.ic{width:22px;height:22px;display:block;fill:none;stroke:currentColor;stroke-width:1.6;
  stroke-linecap:round;stroke-linejoin:round;flex:none}
svg.ic .f{fill:currentColor;stroke:none}
.lbl{font:600 10px/1 var(--mono);letter-spacing:.16em;text-transform:uppercase;color:var(--mut)}
.brand{display:flex;align-items:center;gap:9px;font:800 14px/1 var(--sans);letter-spacing:.01em;color:var(--tx)}
.brand .mk{width:26px;height:26px;color:var(--ac)}
.brand small{font:600 9px/1 var(--mono);letter-spacing:.22em;color:var(--mut);text-transform:uppercase}
.btn{display:inline-flex;align-items:center;gap:8px;font:600 13px var(--sans);color:var(--tx);
  background:var(--elev);border:1px solid var(--line);border-radius:var(--r2);padding:10px 15px;cursor:pointer;
  transition:border-color .15s,background .15s}
.btn:hover{border-color:var(--ac)} .btn svg.ic{width:18px;height:18px}
.btn.primary{background:linear-gradient(180deg,#2ad0b8,#1aa896);color:#032018;border:0;font-weight:700}
.btn.ghost{background:0}
.chip{display:inline-flex;align-items:center;gap:6px;font:600 12px var(--mono);color:var(--mut);
  background:var(--elev);border:1px solid var(--line);border-radius:99px;padding:7px 13px;cursor:pointer;white-space:nowrap}
.chip.on{background:var(--ac);color:#032018;border-color:var(--ac)}
.card{background:var(--surf);border:1px solid var(--line);border-radius:var(--r);box-shadow:var(--sh)}
.field{display:flex;align-items:center;gap:9px;background:var(--elev);border:1px solid var(--line);
  border-radius:var(--r2);padding:10px 13px;color:var(--mut)}
.field input{flex:1;background:0;border:0;color:var(--tx);font:14px var(--sans);outline:0}
.field svg.ic{width:18px;height:18px}
.scrollx{overflow-x:auto;scrollbar-width:none} .scrollx::-webkit-scrollbar{display:none}
"""


def css() -> str:
    return _CSS


# ---------------------------------------------------------------- ícones (24x24)
# Conteúdo interno do <svg>. Traço herda currentColor; `.f` = preenchido.
_IC = {
    # retículo de mira / GOTO
    "reticle": '<circle cx="12" cy="12" r="7.2"/><path d="M12 1.5V4.6M12 19.4V22.5M1.5 12H4.6M19.4 12H22.5"/>'
               '<circle class="f" cx="12" cy="12" r="1.4"/>',
    # diafragma de foco (lente)
    "focus": '<circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="3.8"/>'
             '<path d="M12 3.4v3M12 17.6v3M3.4 12h3M17.6 12h3"/>',
    # ponto de gravação (capturar)
    "dot": '<circle class="f" cx="12" cy="12" r="6.5"/>',
    # quadrado (parar/stop)
    "square": '<rect class="f" x="6.5" y="6.5" width="11" height="11" rx="2.4"/>',
    # mapa estelar (atlas) — constelação
    "atlas": '<circle class="f" cx="5" cy="6.5" r="1.1"/><circle class="f" cx="11" cy="4" r="1.1"/>'
             '<circle class="f" cx="17" cy="8.5" r="1.1"/><circle class="f" cx="9.5" cy="13" r="1.1"/>'
             '<circle class="f" cx="19" cy="16.5" r="1.1"/><circle class="f" cx="13" cy="19.5" r="1.1"/>'
             '<path d="M5 6.5 11 4 17 8.5 9.5 13 13 19.5M17 8.5 19 16.5" stroke-width="1.2"/>',
    # sinal ao vivo (telemetria)
    "live": '<circle cx="12" cy="12" r="8.6"/><path d="M4.2 12h3l1.6-4 3 8 1.6-4h3.4"/>',
    # gráfico (pro)
    "chart": '<path d="M4 3.5v17h16"/><path d="M6.5 15 10 10.5 13.5 13 20 5.5" stroke-width="1.7"/>',
    # ajustes (sliders) — nada de engrenagem-emoji
    "sliders": '<path d="M3 7h18M3 12h18M3 17h18"/><circle class="f" cx="8" cy="7" r="2.3"/>'
               '<circle class="f" cx="15" cy="12" r="2.3"/><circle class="f" cx="10" cy="17" r="2.3"/>',
    # galeria/álbum (quadros empilhados + estrela)
    "album": '<rect x="3" y="6" width="13" height="13" rx="2.2"/><path d="M7.5 6V4.6A1.6 1.6 0 0 1 9.1 3H19.4A1.6 1.6 0 0 1 21 4.6V15"/>'
             '<path d="M6 16l3-3 3 2.4" /><circle class="f" cx="12.5" cy="10" r="1.2"/>',
    # satélite (corpo + painéis + órbita)
    "satellite": '<rect x="10.2" y="10.2" width="3.6" height="3.6" rx=".6"/><path d="M10.2 12H5.4M2.4 10.4h3v3.2h-3z"/>'
                 '<path d="M13.8 12h4.8M18.6 10.4h3v3.2h-3z"/><path d="M8 4.4a10 10 0 0 1 8 16" opacity=".55"/>',
    # planeta anelado
    "planet": '<circle cx="12" cy="12" r="6"/><ellipse cx="12" cy="12" rx="11" ry="3.4" transform="rotate(-22 12 12)" opacity=".8"/>',
    # nebulosa (nuvem + estrelas)
    "nebula": '<path d="M7.5 16a4 4 0 0 1-.4-7.6A4.2 4.2 0 0 1 14 6.4 3.6 3.6 0 0 1 18.7 10 3.3 3.3 0 0 1 17 16z"/>'
              '<circle class="f" cx="10" cy="11.5" r=".8"/><circle class="f" cx="14.5" cy="13" r=".8"/><circle class="f" cx="13" cy="9.5" r=".7"/>',
    # galáxia (espiral)
    "galaxy": '<path d="M12 6.2a5.8 5.8 0 1 1-5.4 3.6"/><path d="M12 9.4a2.6 2.6 0 1 0 2.4 1.5"/><circle class="f" cx="12" cy="12" r="1"/>',
    # aglomerado (dots)
    "cluster": '<circle class="f" cx="8" cy="8" r="1"/><circle class="f" cx="13.5" cy="6.8" r="1"/><circle class="f" cx="16.5" cy="11" r="1"/>'
               '<circle class="f" cx="10.5" cy="12" r="1"/><circle class="f" cx="14.5" cy="15" r="1"/><circle class="f" cx="8.5" cy="16" r="1"/>',
    # lua (crescente)
    "moon": '<path d="M15.5 3.2a9 9 0 1 0 5.3 14.7A7.2 7.2 0 0 1 15.5 3.2z"/>',
    # sol (disco + raios)
    "sun": '<circle cx="12" cy="12" r="4.6"/><path d="M12 2.5v2.4M12 19.1v2.4M2.5 12h2.4M19.1 12h2.4M5.2 5.2l1.7 1.7M17.1 17.1l1.7 1.7M18.8 5.2l-1.7 1.7M6.9 17.1l-1.7 1.7"/>',
    # busca
    "search": '<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5 20.5 20.5"/>',
    # voltar
    "back": '<path d="M14.5 5 8 12l6.5 7"/>',
    # foco/telescópio ajuste (haste)
    "target": '<circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="3.4"/>',
    # alerta/parar redondo
    "power": '<path d="M12 3v8"/><path d="M6.5 6.5a8 8 0 1 0 11 0"/>',
    # empilhar (camadas)
    "layers": '<path d="M12 3 3 7.7l9 4.7 9-4.7z"/><path d="M3 12.2l9 4.7 9-4.7"/><path d="M3 16.5l9 4.7 9-4.7"/>',
    # agenda (lista)
    "list": '<path d="M8.5 6h12.5M8.5 12h12.5M8.5 18h12.5"/><circle class="f" cx="4" cy="6" r="1.4"/>'
            '<circle class="f" cx="4" cy="12" r="1.4"/><circle class="f" cx="4" cy="18" r="1.4"/>',
    # mosaico (grade)
    "grid": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.2"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.2"/>'
            '<rect x="3.5" y="13.5" width="7" height="7" rx="1.2"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.2"/>',
    # download / alta resolução
    "download": '<path d="M12 3v11M7.5 10 12 14.5 16.5 10"/><path d="M4 20h16"/>',
    # olho / live
    "eye": '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    # câmera / captura real
    "camera": '<path d="M4 8.5a2 2 0 0 1 2-2h1.6l1-1.6h4.8l1 1.6H18a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>'
              '<circle cx="12" cy="12.3" r="3.3"/>',
}

# Logo do produto: retículo + órbita + planeta + satélite (mira + órbitas = a essência).
MARK = ('<svg class="mk" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round"><circle cx="16" cy="16" r="4.2"/>'
        '<ellipse cx="16" cy="16" rx="13" ry="6.4" transform="rotate(-24 16 16)" opacity=".85"/>'
        '<path d="M16 3v3.4M16 25.6V29M3 16h3.4M25.6 16H29" opacity=".9"/>'
        '<circle cx="26.4" cy="10" r="1.5" fill="currentColor" stroke="none"/></svg>')


def icon(name: str, size: int = 22, cls: str = "") -> str:
    """SVG do ícone `name` (currentColor). size em px; `cls` adiciona classes."""
    inner = _IC.get(name, _IC["reticle"])
    return (f'<svg class="ic {cls}" viewBox="0 0 24 24" width="{size}" height="{size}" '
            f'aria-hidden="true">{inner}</svg>')


def brand(sub: str = "TELESCÓPIO") -> str:
    return f'<div class="brand">{MARK}<span>JETSON<small>&nbsp;{sub}</small></span></div>'


# categoria de alvo -> ícone (usado no Atlas)
CAT_ICON = {"Nebulosa": "nebula", "Galáxia": "galaxy", "Aglomerado": "cluster",
            "Planeta": "planet", "Lua": "moon", "Sol": "sun", "Satélite": "satellite"}
