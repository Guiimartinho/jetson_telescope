"""O console como "app": instalável na tela inicial, com canal em tempo real e sem digitar porta.

O app é a própria página servida pela Jetson (sem loja). Três coisas a tornam app:
  * manifesto + ícones (o mesmo símbolo do ui_kit, desenhado, sem emoji);
  * WebSocket: a Jetson EMPURRA o estado, em vez de a página perguntar a cada segundo;
  * porta extra (a 80, na Jetson), para o endereço ser só `telescopio.local`.
Ver docs/33.
"""
import json
import time
import urllib.request

import cv2
import numpy as np
import pytest

from src.server import ui_kit as uik
from src.server.console import ConsoleServer
from src.server.webview import FrameHub


def _wait(cond, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


@pytest.fixture
def server():
    got = []
    hub = FrameHub()
    srv = ConsoleServer(hub, host="127.0.0.1", port=0, ws_port=0, extra_ports=(0,),
                        on_command=got.append)
    srv.start()
    srv.commands, srv.hub = got, hub
    yield srv
    srv.stop()


def _get(srv, path, port=None):
    with urllib.request.urlopen(f"http://127.0.0.1:{port or srv.port}{path}", timeout=5) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()


# ---- manifesto e ícones ----------------------------------------------------
def test_manifest_makes_the_console_installable():
    m = uik.manifest()
    assert m["name"] and m["short_name"]
    assert m["start_url"] == "/" and m["display"] == "standalone"
    assert m["background_color"] == uik.APP_BG == m["theme_color"]
    pngs = {i["sizes"] for i in m["icons"] if i["type"] == "image/png"}
    assert {"192x192", "512x512"} <= pngs, "Android exige PNG de 192 e de 512"
    assert any("maskable" in i.get("purpose", "") for i in m["icons"])


@pytest.mark.parametrize("size", [180, 192, 512])
def test_app_icon_is_the_brand_mark_inside_the_maskable_safe_zone(size):
    """O ícone é o símbolo do produto (retículo + órbita) na cor de destaque sobre o fundo do
    app. Fundo cheio até a borda e desenho dentro do círculo central de 80%: o Android
    recorta ícones "maskable" em círculo/squircle e não pode comer o símbolo."""
    img = cv2.imdecode(np.frombuffer(uik.app_icon_png(size), np.uint8), cv2.IMREAD_COLOR)
    assert img.shape == (size, size, 3)
    bg = np.array([int(uik.APP_BG[i:i + 2], 16) for i in (5, 3, 1)])          # BGR
    for y, x in ((0, 0), (0, size - 1), (size - 1, 0), (size - 1, size - 1)):
        assert np.abs(img[y, x].astype(int) - bg).max() <= 2, "os cantos têm de ser fundo"
    desenho = np.abs(img.astype(int) - bg).max(axis=2) > 40
    assert desenho.mean() > 0.02, "o símbolo sumiu"
    yy, xx = np.nonzero(desenho)
    raio = np.hypot(yy - (size - 1) / 2, xx - (size - 1) / 2).max()
    assert raio <= 0.40 * size, f"o símbolo sai da zona segura (raio {raio / size:.2f} do lado)"


def test_svg_icon_reuses_the_brand_geometry():
    svg = uik.app_icon_svg()
    assert svg.startswith("<svg") and uik.APP_BG in svg and uik.APP_ACCENT in svg
    assert 'rx="13" ry="6.4"' in svg, "a órbita é a mesma do logo"


def test_console_serves_manifest_and_icons(server):
    st, ctype, body = _get(server, "/manifest.webmanifest")
    assert st == 200 and "manifest+json" in ctype and json.loads(body)["display"] == "standalone"
    for path in ("/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"):
        st, ctype, body = _get(server, path)
        assert st == 200 and ctype == "image/png" and body[:4] == b"\x89PNG"
    st, ctype, body = _get(server, "/icon.svg")
    assert st == 200 and "svg" in ctype and body.startswith(b"<svg")


def test_page_declares_itself_as_an_app(server):
    _, _, page = _get(server, "/")
    html = page.decode("utf-8")
    assert '<link rel="manifest" href="/manifest.webmanifest">' in html
    assert 'rel="apple-touch-icon"' in html                    # iPhone: ícone da tela inicial
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html   # iPhone: tela cheia


# ---- porta extra -----------------------------------------------------------
def test_console_answers_on_the_extra_port_too(server):
    """Na Jetson a porta extra é a 80: o endereço vira só `telescopio.local`."""
    assert len(server.extra_ports) == 1 and server.extra_ports[0] != server.port
    st, _, body = _get(server, "/api/state", port=server.extra_ports[0])
    assert st == 200 and "mount" in json.loads(body)


def test_an_extra_port_that_cannot_be_bound_does_not_kill_the_console(monkeypatch):
    """Sem permissão para a 80 (PC de dev), o console sobe mesmo assim na porta principal."""
    from src.server import console as mod
    real = mod.ThreadingHTTPServer

    def sem_permissao_na_80(addr, handler):
        if addr[1] == 80:
            raise PermissionError(13, "Permission denied")
        return real(addr, handler)

    monkeypatch.setattr(mod, "ThreadingHTTPServer", sem_permissao_na_80)
    srv = ConsoleServer(FrameHub(), host="127.0.0.1", port=0, ws_port=None, extra_ports=(80,))
    try:
        assert srv.extra_ports == [] and srv.port
    finally:
        srv.stop()


# ---- canal em tempo real ---------------------------------------------------
ws_client = pytest.importorskip("websockets.sync.client", reason="websockets não instalado")


def test_state_tells_the_page_where_the_live_channel_is(server):
    _, _, body = _get(server, "/api/state")
    assert json.loads(body)["ws_port"] == server.ws_port and server.ws_port


def test_websocket_pushes_state_without_being_asked(server):
    """A página não precisa perguntar: mudou o estado, chega a mensagem."""
    with ws_client.connect(f"ws://127.0.0.1:{server.ws_port}") as ws:
        primeiro = json.loads(ws.recv(timeout=3))
        assert "mount" in primeiro                                   # estado completo ao conectar
        t0 = time.monotonic()
        server.hub.update(b"", {"state": "STACKING", "accepted": 7, "backend": "CuPy/GPU"})
        while True:
            s = json.loads(ws.recv(timeout=3))
            if s.get("state") == "STACKING":
                break
        assert s["accepted"] == 7
        assert time.monotonic() - t0 < 0.8, "tem de ser empurrado, não esperar o próximo ciclo"


def test_websocket_carries_commands_to_the_controller(server):
    with ws_client.connect(f"ws://127.0.0.1:{server.ws_port}") as ws:
        ws.recv(timeout=3)
        ws.send(json.dumps({"cmd": "start:stack"}))
        assert _wait(lambda: server.commands == ["start:stack"])


def test_garbage_on_the_websocket_does_not_break_the_channel(server):
    with ws_client.connect(f"ws://127.0.0.1:{server.ws_port}") as ws:
        ws.recv(timeout=3)
        ws.send("isto não é JSON")
        ws.send(json.dumps({"cmd": "stop"}))
        assert _wait(lambda: server.commands == ["stop"])


def test_console_without_live_channel_still_serves_state():
    """Sem a lib (ou com ws_port=None) a página segue no modo antigo, perguntando."""
    srv = ConsoleServer(FrameHub(), host="127.0.0.1", port=0, ws_port=None)
    srv.start()
    try:
        _, _, body = _get(srv, "/api/state")
        assert json.loads(body)["ws_port"] is None
    finally:
        srv.stop()


# ---- com a API protegida ligada, o console vira só leitura -----------------

@pytest.fixture
def readonly_server():
    got = []
    srv = ConsoleServer(FrameHub(), host="127.0.0.1", port=0, ws_port=0, on_command=got.append,
                        allow_commands=False)
    srv.start()
    srv.commands = got
    yield srv
    srv.stop()


def test_read_only_console_refuses_commands_over_open_http(readonly_server):
    """A API do app exige canal cifrado e token. Deixar o comando aberto por HTTP ao lado
    anularia isso: qualquer um na rede moveria a montagem (app/docs/07-seguranca.md, §9)."""
    with pytest.raises(urllib.error.HTTPError) as e:
        _get(readonly_server, "/api/cmd/start:goto:M31")
    assert e.value.code == 403
    assert json.loads(e.value.read())["error"] == "commands_disabled"
    assert readonly_server.commands == []


def test_read_only_console_ignores_commands_on_the_websocket(readonly_server):
    with ws_client.connect(f"ws://127.0.0.1:{readonly_server.ws_port}") as ws:
        ws.recv(timeout=3)
        ws.send(json.dumps({"cmd": "start:stack"}))
        time.sleep(0.4)
    assert readonly_server.commands == []


def test_read_only_console_still_shows_everything_and_says_why(readonly_server):
    status, _, body = _get(readonly_server, "/api/state")
    assert status == 200 and json.loads(body)["commands"] is False
    _, _, page = _get(readonly_server, "/")
    assert "só pelo app".encode() in page, "a página avisa em vez de falhar calada"


def test_console_commands_stay_on_by_default(server):
    _, _, body = _get(server, "/api/state")
    assert json.loads(body)["commands"] is True
    assert _get(server, "/api/cmd/stop")[0] == 200 and server.commands == ["stop"]
