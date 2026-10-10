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
    # ---- pedidos pelo app do celular (app/): o desenho nasce aqui e é exportado para lá ----
    # telescópio no tripé (aparelho / montagem)
    "mount": '<path d="M4.4 10 14.8 5l1.9 3.9L6.3 13.9z"/><path d="M16.7 8.9l3.3-1.6"/>'
             '<path d="M10.6 12.3v2.6M10.6 14.9 6.6 21M10.6 14.9l4 6.1M10.6 14.9V21"/>',
    # WiFi
    "wifi": '<path d="M2.6 9.3a14 14 0 0 1 18.8 0M5.8 12.9a9.2 9.2 0 0 1 12.4 0M9 16.4a4.4 4.4 0 0 1 6 0"/>'
            '<circle class="f" cx="12" cy="19.5" r="1.2"/>',
    # QR code (pareamento)
    "qr": '<rect x="3.5" y="3.5" width="6.5" height="6.5" rx="1"/><rect x="14" y="3.5" width="6.5" height="6.5" rx="1"/>'
          '<rect x="3.5" y="14" width="6.5" height="6.5" rx="1"/><path d="M14 14h2.6v2.6H14zM17.9 17.9h2.6v2.6h-2.6z"/>'
          '<path d="M18.6 14h1.9M14 18.6v1.9"/>',
    # teclado (digitar o código)
    "keyboard": '<rect x="2.5" y="6" width="19" height="12" rx="2"/><path d="M7.5 14.5h9"/>'
                '<circle class="f" cx="6.5" cy="10" r=".8"/><circle class="f" cx="10.2" cy="10" r=".8"/>'
                '<circle class="f" cx="13.8" cy="10" r=".8"/><circle class="f" cx="17.5" cy="10" r=".8"/>',
    # confirmado
    "check": '<path d="M4 12.5 9.5 18 20 6"/>',
    # fechar / cancelar
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    # atenção
    "warning": '<path d="M12 3.6 21.4 20H2.6z"/><path d="M12 10v4.6"/><circle class="f" cx="12" cy="17.3" r=".9"/>',
    # informação
    "info": '<circle cx="12" cy="12" r="8.6"/><path d="M12 11v5.6"/><circle class="f" cx="12" cy="7.8" r=".9"/>',
    # favorito
    "star": '<path d="M12 3.2l2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-3-5.4 3 1.1-6L3.2 9.6l6.1-.8z"/>',
    # avançar / abrir
    "chevron": '<path d="M9.5 5 16 12l-6.5 7"/>',
    # hora
    "clock": '<circle cx="12" cy="12" r="8.6"/><path d="M12 7v5.2l3.4 2"/>',
    # local
    "pin": '<path d="M12 21s-6.5-6.2-6.5-11a6.5 6.5 0 0 1 13 0c0 4.8-6.5 11-6.5 11z"/><circle cx="12" cy="10" r="2.4"/>',
    # adicionar
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "minus": '<path d="M5 12h14"/>',
    # seta para cima; o app a gira para as quatro direções do movimento manual
    "arrow": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    # apagar
    "trash": '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 13h9l1-13M10 11v5.5M14 11v5.5"/>',
    # compartilhar / exportar
    "share": '<path d="M12 15V3.5M7.8 7.5 12 3.5l4.2 4"/>'
             '<path d="M5 12.5V19a1.5 1.5 0 0 0 1.5 1.5h11A1.5 1.5 0 0 0 19 19v-6.5"/>',
    # celular
    "phone": '<rect x="7" y="2.5" width="10" height="19" rx="2.2"/><path d="M10.5 18.5h3"/>',
    # iniciar
    "play": '<path class="f" d="M8 5.5v13l10.5-6.5z"/>',
    # processador (GPU)
    "chip": '<rect x="6" y="6" width="12" height="12" rx="1.8"/>'
            '<path d="M9.5 2.5V6M14.5 2.5V6M9.5 18v3.5M14.5 18v3.5M2.5 9.5H6M2.5 14.5H6M18 9.5h3.5M18 14.5h3.5"/>',
    # temperatura
    "thermo": '<path d="M10 14.2V5a2 2 0 0 1 4 0v9.2a4 4 0 1 1-4 0z"/><path d="M12 9v7"/>',
    # disco
    "disk": '<ellipse cx="12" cy="6.5" rx="7.5" ry="3"/>'
            '<path d="M4.5 6.5v11c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3v-11M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3"/>',
    # cadeado (canal protegido / pareado)
    "lock": '<rect x="5" y="10.5" width="14" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
}

# Logo do produto: retículo + órbita + planeta + satélite (mira + órbitas = a essência).
# A geometria (grade de 32) é única: o SVG do cabeçalho e o ícone do app saem dela.
_MARK_INNER = ('<circle cx="16" cy="16" r="4.2"/>'
               '<ellipse cx="16" cy="16" rx="13" ry="6.4" transform="rotate(-24 16 16)" opacity=".85"/>'
               '<path d="M16 3v3.4M16 25.6V29M3 16h3.4M25.6 16H29" opacity=".9"/>'
               '<circle cx="26.4" cy="10" r="1.5" fill="currentColor" stroke="none"/>')
MARK = ('<svg class="mk" viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-width="1.7" '
        'stroke-linecap="round">' + _MARK_INNER + '</svg>')

# ---- o console como app (tela inicial do celular) ------------------------------------------
APP_NAME, APP_SHORT = "Telescópio Jetson", "Telescópio"
APP_BG, APP_ACCENT = "#04060c", "#33ddc4"            # --bg e --ac do tema
# O símbolo ocupa 62% do lado do ícone: cabe no círculo central de 80% que o Android preserva
# ao recortar ícones "maskable". Os traços vão de 3 a 29 na grade (26 unidades).
_ICON_SPAN = 0.62
_ICON_SCALE = _ICON_SPAN * 32 / 26
_ICON_CACHE: dict[int, bytes] = {}


def app_icon_svg() -> str:
    """Ícone do app em SVG: o logo na cor de destaque, sobre o fundo do app."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            f'<rect width="32" height="32" fill="{APP_BG}"/>'
            f'<g transform="translate(16 16) scale({_ICON_SCALE:.4f}) translate(-16 -16)" fill="none" '
            f'stroke="{APP_ACCENT}" stroke-width="1.7" stroke-linecap="round" color="{APP_ACCENT}">'
            f'{_MARK_INNER}</g></svg>')


def app_icon_png(size: int) -> bytes:
    """O mesmo ícone em PNG (iOS e Android exigem PNG na tela inicial). Desenhado com a
    geometria do logo, em 4x e reduzido — traço limpo sem depender de um renderizador de SVG."""
    if size in _ICON_CACHE:
        return _ICON_CACHE[size]
    import cv2
    import numpy as np
    big = size * 4
    u = _ICON_SPAN * big / 26.0                        # 1 unidade da grade de 32, em pixels
    bg = tuple(int(APP_BG[i:i + 2], 16) for i in (5, 3, 1))          # BGR
    ac = tuple(int(APP_ACCENT[i:i + 2], 16) for i in (5, 3, 1))

    def pt(x, y):
        return int(round(big / 2 + (x - 16) * u)), int(round(big / 2 + (y - 16) * u))

    def tom(opacidade):
        return tuple(int(round(a * opacidade + b * (1 - opacidade))) for a, b in zip(ac, bg))

    traco = max(1, int(round(1.7 * u)))
    img = np.empty((big, big, 3), np.uint8)
    img[:] = bg
    cv2.ellipse(img, pt(16, 16), (int(round(13 * u)), int(round(6.4 * u))), -24, 0, 360,
                tom(.85), traco, cv2.LINE_AA)                                  # órbita
    for x1, y1, x2, y2 in ((16, 3, 16, 6.4), (16, 25.6, 16, 29), (3, 16, 6.4, 16), (25.6, 16, 29, 16)):
        cv2.line(img, pt(x1, y1), pt(x2, y2), tom(.9), traco, cv2.LINE_AA)     # marcas do retículo
    cv2.circle(img, pt(16, 16), int(round(4.2 * u)), ac, traco, cv2.LINE_AA)   # planeta
    cv2.circle(img, pt(26.4, 10), int(round(1.5 * u)), ac, -1, cv2.LINE_AA)    # satélite
    ok, buf = cv2.imencode(".png", cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA))
    if not ok:
        raise RuntimeError("falha ao codificar o ícone do app")
    _ICON_CACHE[size] = buf.tobytes()
    return _ICON_CACHE[size]


def manifest() -> dict:
    """Manifesto de app web: é o que deixa o console ir para a tela inicial do celular."""
    icones = []
    for lado in (192, 512):
        for uso in ("any", "maskable"):
            icones.append({"src": f"/icon-{lado}.png", "sizes": f"{lado}x{lado}",
                           "type": "image/png", "purpose": uso})
    icones.append({"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"})
    return {"name": APP_NAME, "short_name": APP_SHORT, "lang": "pt-BR",
            "description": "Console de campo do telescópio (Live / Atlas / Pro)",
            "start_url": "/", "scope": "/", "display": "standalone",
            "background_color": APP_BG, "theme_color": APP_BG, "icons": icones}


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
