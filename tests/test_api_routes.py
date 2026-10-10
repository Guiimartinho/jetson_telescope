"""Rotas da API v1 (app/docs/04-api.md), sem rede nem aparelho.

O servidor é montado com objetos simples no lugar do Controller e da GPU. O que estes testes
travam: nada além de `/info` e do pareamento responde sem token; erro tem sempre o mesmo
formato; comando repetido não executa duas vezes; e o canal em tempo real empurra o estado.
"""
import time
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient                                    # noqa: E402
from starlette.websockets import WebSocketDisconnect                          # noqa: E402

from src.api.app import ApiContext, create_app                               # noqa: E402
from src.api.identity import DeviceIdentity, b64u, b64u_decode               # noqa: E402
from src.api.pairing import PairingService, pairing_proof                    # noqa: E402
from src.core import catalog as cat                                          # noqa: E402
from src.server.webview import FrameHub                                      # noqa: E402

SESSIONS = [{"id": "lagoon_trifid", "target": "M8 Lagoa + M20 Trifida", "frames": 15,
             "integration_s": 2700, "has_fits": True}]
MOUNT = {"source": "indi", "connected": True, "ra_deg": 83.82, "dec_deg": -5.39,
         "tracking": None, "parked": None, "moving": None, "features": [], "error": None}

needs_ongc = pytest.mark.skipif(not cat.HAS_ONGC, reason="pyongc não instalado (OpenNGC)")


class FakeLink:
    """O bastante do MountLink para a API: estado e o envio de hora/local."""
    def __init__(self):
        self.sent = None

    def status(self):
        return {"connected": True, "ra_deg": 83.82, "dec_deg": -5.39, "error": None}

    def update_site(self, site, now=None):
        self.sent = (site, now())
        return True


def _fake_render(session_id, params):
    if "preset" in params and params["preset"] not in ("natural", "vivido"):
        raise ValueError("preset: desconhecido")
    return b"\xff\xd8render:" + str(sorted(params.items())).encode()


@pytest.fixture
def ctx(tmp_path):
    ident = DeviceIdentity.load_or_create(tmp_path / "identity")
    c = ApiContext(identity=ident, pairing=PairingService(ident), hub=FrameHub(), submit=None)
    c.commands, c.tags, c.image_keys = [], [], []
    c.submit = lambda cmd, tag=None: (c.commands.append(cmd), c.tags.append(tag))
    c.hub.update(b"", {"state": "IDLE", "job": None, "outcome": ""})
    c.mount_link = FakeLink()
    c.sessions = lambda: SESSIONS

    def image(key, thumb):
        c.image_keys.append(key)
        return b"\xff\xd8thumb" if thumb else b"\xff\xd8full"
    c.image_jpeg = image
    c.render_session = _fake_render
    c.presets = lambda: {"presets": {"natural": {}}, "controls": {}}
    return c


@pytest.fixture
def http(ctx):
    with TestClient(create_app(ctx)) as c:
        yield c


def pair(http, ctx, name="Pixel de teste", role="owner"):
    """Pareia como o app fará: pede o número, prova que tem o segredo, recebe o token."""
    ctx.pairing.open_window()
    nonce = http.post("/api/v1/pair/start", json={"client_name": name}).json()["nonce"]
    proof = b64u(pairing_proof(ctx.identity.pairing_secret, b64u_decode(nonce),
                               ctx.identity.fingerprint_bytes, name))
    if role != "owner":                      # papéis menores ainda não têm rota: direto no serviço
        token, _ = ctx.pairing.finish(name, proof, role=role)
        return {"Authorization": f"Bearer {token}"}
    r = http.post("/api/v1/pair/finish", json={"client_name": name, "proof": proof})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ---- quem entra -----------------------------------------------------------
def test_info_is_public_and_describes_the_device(http, ctx):
    r = http.get("/api/v1/info")
    assert r.status_code == 200
    d = r.json()
    assert d["id"] == ctx.identity.device_id and d["api"] == 1
    assert d["pairing_open"] is False and d["clock"]["synced"] is False
    assert "token" not in r.text and "secret" not in r.text


def test_info_says_what_is_real_and_what_is_simulated(http):
    """A montagem pode estar ligada de verdade enquanto o apontamento ainda é do simulador.
    O app precisa dos dois fatos para não prometer o que não acontece."""
    cap = http.get("/api/v1/info").json()["capabilities"]
    assert cap["mount"] == "indi" and cap["goto"] == "sim" and cap["camera"] == "sim"


@pytest.mark.parametrize("path", ["/api/v1/state", "/api/v1/targets", "/api/v1/sessions",
                                  "/api/v1/system", "/api/v1/clients", "/api/v1/frame.jpg",
                                  "/api/v1/logs", "/api/v1/openapi.json", "/api/v1/preview.mjpg",
                                  "/api/v1/targets/M8/thumb", "/api/v1/render/presets"])
def test_everything_else_needs_a_token(http, path):
    for headers in ({}, {"Authorization": "Bearer token-inventado"}):
        r = http.get(path, headers=headers)
        assert r.status_code == 401
        assert r.json() == {"error": {"code": "unauthorized",
                                      "message": "pareie o celular com o telescópio"}}


def test_pairing_over_http_end_to_end(http, ctx):
    headers = pair(http, ctx)
    r = http.get("/api/v1/state", headers=headers)
    assert r.status_code == 200
    s = r.json()
    assert s["state"] == "IDLE" and s["mount"] == MOUNT and s["job"] is None
    assert s["camera"]["source"] == "sim", "a câmera ainda é simulada, e a API diz isso"
    assert s["stack"]["integration_s"] is None, "sem exposição de verdade, não se inventa tempo"
    assert http.get("/api/v1/mount", headers=headers).json() == MOUNT


def test_pairing_errors_have_codes_the_app_can_translate(http, ctx):
    r = http.post("/api/v1/pair/start", json={"client_name": "Pixel"})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "pairing_closed")
    ctx.pairing.open_window()
    http.post("/api/v1/pair/start", json={"client_name": "Pixel"})
    r = http.post("/api/v1/pair/finish", json={"client_name": "Pixel", "proof": b64u(b"x" * 32)})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "pairing_rejected")


def test_invalid_input_is_a_400_with_the_field_name(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/site", headers=h, json={"utc": "2026-10-09T20:00:00Z", "lat": 200, "lon": 0})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_argument" and "lat" in r.json()["error"]["message"]


def test_unknown_route_uses_the_same_error_format(http):
    r = http.get("/api/v1/nao-existe")
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_huge_body_is_refused_before_anything_else(http):
    """As rotas de pareamento não pedem token: sem limite, qualquer um na rede encheria a
    memória da Jetson."""
    r = http.post("/api/v1/pair/start", json={"client_name": "x" * 100_000})
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")

    def em_pedacos():                                 # sem tamanho declarado
        for _ in range(40):
            yield b"x" * 4096
    r = http.post("/api/v1/pair/start", content=em_pedacos(),
                  headers={"Content-Type": "application/json"})
    assert (r.status_code, r.json()["error"]["code"]) == (413, "payload_too_large")


# ---- hora e local vêm do celular -----------------------------------------
def test_phone_sets_site_and_clock_and_the_mount_receives_them(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/site", headers=h, json={"utc": "2031-03-04T05:06:07Z", "lat": -22.9,
                                                    "lon": -43.2, "elev_m": 10})
    assert r.status_code == 200
    assert r.json()["clock_set"] is True and r.json()["mount_updated"] is True
    site, when = ctx.mount_link.sent
    assert site == (-22.9, -43.2, 10.0)
    assert abs((when - datetime(2031, 3, 4, 5, 6, 7, tzinfo=timezone.utc)).total_seconds()) < 5, (
        "a montagem recebe a hora do CELULAR, mesmo com o relógio da Jetson errado")
    d = http.get("/api/v1/info").json()
    assert d["site"] == {"lat": -22.9, "lon": -43.2, "elev_m": 10.0, "source": "phone"}
    assert d["clock"]["synced"] is True and d["clock"]["utc"].startswith("2031-03-04T05:06")


def test_site_time_without_timezone_is_refused(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/site", headers=h, json={"utc": "2026-10-09T20:00:00", "lat": 0, "lon": 0})
    assert r.status_code == 400


# ---- observar -------------------------------------------------------------
def test_goto_becomes_a_job_and_reaches_the_controller(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-1", "target": "m 8"})
    job = r.json()
    assert r.status_code == 200 and (job["kind"], job["state"], job["target"]) == ("goto", "accepted", "M8")
    assert ctx.commands == ["start:goto:M8"]
    assert ctx.tags == [job["job"]], "o Controller recebe o id do trabalho como etiqueta"
    assert http.get("/api/v1/state", headers=h).json()["job"]["job"] == job["job"]


def test_job_follows_the_controller_until_it_ends(http, ctx):
    """O app pergunta "terminou?" e a resposta vem do estado que o Controller publica."""
    h = pair(http, ctx)
    tag = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-1", "target": "M8"}).json()["job"]

    def job_after(**stats):
        ctx.hub.update(b"", dict({"job": tag, "outcome": ""}, **stats))
        return http.get("/api/v1/state", headers=h).json()["job"]

    assert job_after(state="STACKING", job="outro-comando")["state"] == "accepted"
    assert job_after(state="IDLE")["state"] == "accepted"
    assert job_after(state="SLEWING")["steps"] == [{"name": "slew", "state": "running"}]
    j = job_after(state="SOLVING")
    assert j["state"] == "running" and j["steps"] == [{"name": "slew", "state": "done"},
                                                     {"name": "solve", "state": "running"}]
    j = job_after(state="STOPPED", outcome="ok")
    assert j["state"] == "done" and all(s["state"] == "done" for s in j["steps"])


def test_goto_that_did_not_converge_is_a_failed_job(http, ctx):
    h = pair(http, ctx)
    tag = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-1", "target": "M8"}).json()["job"]
    ctx.hub.update(b"", {"state": "SOLVING", "job": tag, "outcome": ""})
    http.get("/api/v1/state", headers=h)
    ctx.hub.update(b"", {"state": "STOPPED", "job": tag, "outcome": "not_converged"})
    j = http.get("/api/v1/state", headers=h).json()["job"]
    assert (j["state"], j["error"]) == ("failed", "not_converged")
    assert j["steps"] == [{"name": "solve", "state": "failed"}]


def test_resending_the_same_command_does_not_run_it_twice(http, ctx):
    """O app reenvia depois de uma queda de sinal; a montagem não pode se mexer duas vezes."""
    h = pair(http, ctx)
    a = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-7", "target": "M8"}).json()
    b = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-7", "target": "M8"}).json()
    assert a["job"] == b["job"] and ctx.commands == ["start:goto:M8"]


def test_stop_and_modes(http, ctx):
    h = pair(http, ctx)
    assert http.post("/api/v1/observe/stack", headers=h, json={"id": "a"}).json()["ignored"] == []
    noite = http.post("/api/v1/observe/run", headers=h, json={"id": "b", "mode": "night"}).json()
    parar = http.post("/api/v1/observe/stop", headers=h, json={"id": "c"}).json()
    assert (parar["kind"], parar["state"]) == ("stop", "done")
    assert ctx.commands == ["start:stack", "start:night", "stop"]
    ctx.hub.update(b"", {"state": "STOPPED", "job": noite["job"], "outcome": "stopped"})
    j = http.get("/api/v1/state", headers=h).json()["job"]
    assert (j["job"], j["state"]) == (noite["job"], "stopped"), "o trabalho parado é o da noite"


def test_a_new_command_interrupts_the_previous_job(http, ctx):
    h = pair(http, ctx)
    http.post("/api/v1/observe/stack", headers=h, json={"id": "a"})
    b = http.post("/api/v1/observe/goto", headers=h, json={"id": "b", "target": "M8"}).json()
    assert http.get("/api/v1/state", headers=h).json()["job"]["job"] == b["job"]
    repetido = http.post("/api/v1/observe/stack", headers=h, json={"id": "a"}).json()
    assert repetido["state"] == "stopped" and ctx.commands == ["start:stack", "start:goto:M8"]


def test_api_says_when_a_parameter_is_not_applied_yet(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/observe/stack", headers=h,
                  json={"id": "s", "exposure_s": 30, "gain": 120, "frames": 50})
    assert r.json()["ignored"] == ["exposure_s", "gain", "frames"], (
        "com a câmera simulada estes parâmetros não valem, e a resposta diz quais")


def test_observe_target_is_one_command_for_the_whole_quick_night(http, ctx):
    """Apontar, centralizar e empilhar num comando só: a sequência é da Jetson, não do celular."""
    h = pair(http, ctx)
    job = http.post("/api/v1/observe/target", headers=h, json={"id": "o-1", "target": "M8"}).json()
    assert (job["kind"], job["target"]) == ("observe", "M8") and ctx.commands == ["start:observe:M8"]
    assert http.post("/api/v1/observe/target", headers=h, json={"id": "o-2"}).status_code == 400
    assert http.post("/api/v1/observe/target", headers=h, json={"id": "o-3", "target": "../x"}).status_code == 404
    assert ctx.commands == ["start:observe:M8"]


def test_goto_by_coordinates(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/observe/goto", headers=h, json={"id": "x", "ra_deg": 83.82, "dec_deg": -5.39})
    assert r.status_code == 200 and ctx.commands == ["start:goto:@83.82000,-5.39000"]


def test_invalid_commands_never_reach_the_controller(http, ctx):
    h = pair(http, ctx)
    casos = [("/api/v1/observe/goto", {"id": "y"}, 400),
             ("/api/v1/observe/goto", {"id": "y", "ra_deg": 400, "dec_deg": 0}, 400),
             ("/api/v1/observe/goto", {"id": "y", "target": "M8:../x"}, 404),
             ("/api/v1/observe/run", {"id": "z", "mode": "formatar-o-disco"}, 400),
             ("/api/v1/observe/run", {"id": "z", "mode": "stack", "target": "M31:stop"}, 400),
             ("/api/v1/observe/stop", {}, 400)]
    for path, body, status in casos:
        assert http.post(path, headers=h, json=body).status_code == status, (path, body)
    assert ctx.commands == []


def test_viewer_can_watch_but_not_command(http, ctx):
    h = pair(http, ctx, name="Tablet da visita", role="viewer")
    assert http.get("/api/v1/state", headers=h).status_code == 200
    r = http.post("/api/v1/observe/stop", headers=h, json={"id": "c"})
    assert (r.status_code, r.json()["error"]["code"]) == (403, "forbidden")
    assert http.get("/api/v1/clients", headers=h).status_code == 403
    assert http.get("/api/v1/logs", headers=h).status_code == 403
    assert ctx.commands == []


def test_audit_log_says_who_did_what_and_holds_no_secret(http, ctx):
    h = pair(http, ctx, "Pixel")
    http.post("/api/v1/observe/goto", headers=h, json={"id": "c-1", "target": "M8"})
    http.post("/api/v1/observe/stop", headers=h, json={"id": "c-2"})
    r = http.get("/api/v1/logs", headers=h)
    itens = r.json()["items"]
    assert [(i["who"], i["action"]) for i in itens] == [("Pixel", "stop"), ("Pixel", "goto"), ("Pixel", "pair")]
    assert itens[1]["detail"]["target"] == "M8"
    token = h["Authorization"].split()[1]
    assert token not in r.text and b64u(ctx.identity.pairing_secret) not in r.text


# ---- galeria --------------------------------------------------------------
def test_sessions_images_and_render(http, ctx):
    h = pair(http, ctx)
    assert http.get("/api/v1/sessions", headers=h).json() == {"items": SESSIONS}
    assert http.get("/api/v1/sessions/lagoon_trifid", headers=h).json()["frames"] == 15
    r = http.get("/api/v1/sessions/lagoon_trifid/image?thumb=true", headers=h)
    assert r.headers["content-type"] == "image/jpeg" and r.content == b"\xff\xd8thumb"
    r = http.post("/api/v1/sessions/lagoon_trifid/render", headers=h,
                  json={"preset": "vivido", "stretch": 13.0})
    assert r.content.startswith(b"\xff\xd8render:") and b"vivido" in r.content
    r = http.get("/api/v1/sessions/nao-existe", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (404, "not_found")


def test_render_refuses_bad_controls(http, ctx):
    h = pair(http, ctx)
    for body in ({"preset": "inexistente"}, {"stretch": [1, 2]}, {"stretch": {"a": 1}}):
        r = http.post("/api/v1/sessions/lagoon_trifid/render", headers=h, json=body)
        assert (r.status_code, r.json()["error"]["code"]) == (400, "invalid_argument"), body
    assert http.post("/api/v1/sessions/outra/render", headers=h, json={}).status_code == 404


# ---- céu ------------------------------------------------------------------
@needs_ongc
def test_targets_come_highest_first_with_paging(http, ctx):
    h = pair(http, ctx)
    d = http.get("/api/v1/targets?visible=true&limit=5", headers=h).json()
    alts = [t["alt_deg"] for t in d["items"]]
    assert len(alts) == 5 and alts == sorted(alts, reverse=True) and min(alts) >= 25
    assert d["total"] > 5
    seguinte = http.get("/api/v1/targets?visible=true&limit=5&offset=5", headers=h).json()
    assert seguinte["items"][0]["id"] != d["items"][0]["id"]
    assert http.get("/api/v1/targets?limit=5000", headers=h).status_code == 400


@needs_ongc
def test_targets_search_and_filters(http, ctx):
    h = pair(http, ctx)
    d = http.get("/api/v1/targets?q=m31", headers=h).json()
    assert d["items"][0]["id"] == "M31" and d["items"][0]["type"] == "galaxy"
    assert d["items"][0]["catalog"] == "NGC224" and d["items"][0]["name"] == "Andromeda Galaxy"
    assert http.get("/api/v1/targets?q=m3", headers=h).json()["items"][0]["id"] == "M3", (
        "o que casa exatamente vem antes do que só começa igual (M30, M31...)")
    assert http.get("/api/v1/targets?q=orion", headers=h).json()["items"][0]["id"] == "M42"
    so_galaxias = http.get("/api/v1/targets?type=galaxy&limit=20", headers=h).json()["items"]
    assert so_galaxias and all(t["type"] == "galaxy" for t in so_galaxias)
    cabem = http.get("/api/v1/targets?fits=true&limit=20", headers=h).json()["items"]
    assert cabem and all(t["fits"] is True for t in cabem)
    assert http.get("/api/v1/targets?type=planeta", headers=h).status_code == 400


@needs_ongc
def test_target_detail_has_the_night_curve(http, ctx):
    # relógio fixo (22h30 em São Paulo): com o relógio de verdade o teste falhava quando rodava
    # no fim da madrugada, porque sobravam poucos pontos de noite
    ctx.site.now = lambda: datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc)
    h = pair(http, ctx)
    d = http.get("/api/v1/targets/M8", headers=h).json()
    assert d["id"] == "M8" and d["framing"]["fov_deg"] == [2.57, 1.44]
    curva = d["night"]["altitude"]
    assert 10 < len(curva) < 60, "uma noite em passos de 20 minutos"
    assert curva[0]["utc"] == "2026-10-10T01:30:00Z"
    assert all(-90 <= p["alt_deg"] <= 90 for p in curva)
    assert http.get("/api/v1/targets/XYZ999", headers=h).status_code == 404


@needs_ongc
def test_thumb_key_comes_from_the_catalog_never_from_the_request(http, ctx):
    h = pair(http, ctx)
    assert http.get("/api/v1/targets/M8/thumb", headers=h).content == b"\xff\xd8thumb"
    assert http.get("/api/v1/targets/ngc 6523/thumb", headers=h).status_code == 200
    assert ctx.image_keys == ["lagoon_trifid", "lagoon_trifid"]
    for ruim in ("..%5C..%5Csegredo", "M8%00", "@sky:M31", "..", "M8.jpg"):
        assert http.get(f"/api/v1/targets/{ruim}/thumb", headers=h).status_code == 404, ruim
    assert ctx.image_keys == ["lagoon_trifid", "lagoon_trifid"], "nada de fora vira nome de arquivo"


# ---- celulares e sistema --------------------------------------------------
def test_owner_revokes_a_phone_and_it_is_out(http, ctx):
    dono = pair(http, ctx, "Pixel")
    outro = pair(http, ctx, "Tablet")
    itens = http.get("/api/v1/clients", headers=dono).json()["items"]
    assert [(c["name"], c["current"]) for c in itens] == [("Pixel", True), ("Tablet", False)]
    assert all("token" not in k for c in itens for k in c)
    tablet = next(c["id"] for c in itens if c["name"] == "Tablet")
    assert http.delete(f"/api/v1/clients/{tablet}", headers=dono).status_code == 200
    assert http.get("/api/v1/state", headers=outro).status_code == 401


def test_power_is_off_unless_the_device_enables_it(http, ctx):
    h = pair(http, ctx)
    r = http.post("/api/v1/system/shutdown", headers=h)
    assert (r.status_code, r.json()["error"]["code"]) == (501, "not_enabled")
    assert http.get("/api/v1/system", headers=h).json()["power"] is False
    pedidos = []
    ctx.power = pedidos.append
    assert http.post("/api/v1/system/restart", headers=h).status_code == 200
    assert pedidos == ["restart"]


def test_api_description_is_generated_but_only_for_paired_phones(http, ctx):
    h = pair(http, ctx)
    paths = http.get("/api/v1/openapi.json", headers=h).json()["paths"]
    assert "/api/v1/observe/goto" in paths and "/api/v1/pair/start" in paths
    assert http.get("/docs").status_code == 404 and http.get("/openapi.json").status_code == 404


# ---- canal em tempo real --------------------------------------------------
def _next(ws, kind):
    for _ in range(20):
        msg = ws.receive_json()
        if msg.get("type") == kind:
            return msg
    raise AssertionError(f"nenhuma mensagem {kind}")


def test_websocket_pushes_state_and_takes_commands(http, ctx):
    h = pair(http, ctx)
    with http.websocket_connect("/api/v1/ws", headers=h) as ws:
        primeiro = ws.receive_json()
        assert primeiro["type"] == "state" and primeiro["seq"] == 1
        assert primeiro["data"]["mount"]["connected"] is True
        t0 = time.monotonic()
        ctx.hub.update(b"", {"state": "STACKING", "accepted": 7, "backend": "CuPy/GPU"})
        msg = _next(ws, "state")
        assert msg["seq"] > 1 and msg["data"]["state"] == "STACKING"
        assert msg["data"]["stack"]["accepted"] == 7
        assert time.monotonic() - t0 < 1.0, "empurrado, não consultado"
        ws.send_json({"id": "c-9", "cmd": "observe.stop"})
        ack = _next(ws, "ack")
        assert ack["id"] == "c-9" and ack["kind"] == "stop"
        assert ctx.commands == ["stop"]
        ws.send_json({"id": "c-10", "cmd": "apagar.tudo"})
        assert _next(ws, "error")["code"] == "not_supported"


def test_websocket_sends_only_the_part_that_changed(http, ctx):
    """Durante o empilhamento só os números mudam: o app recebe só eles, não o retrato todo."""
    h = pair(http, ctx)
    ctx.hub.update(b"", {"state": "STACKING", "accepted": 1})
    with http.websocket_connect("/api/v1/ws", headers=h) as ws:
        assert ws.receive_json()["type"] == "state"
        ctx.hub.update(b"", {"state": "STACKING", "accepted": 2, "snr": 3.5})
        msg = _next(ws, "stack")
        assert msg["data"]["accepted"] == 2 and msg["data"]["snr"] == 3.5
        assert "mount" not in msg["data"] and "state" not in msg["data"]


def test_websocket_reports_job_progress(http, ctx):
    h = pair(http, ctx)
    tag = http.post("/api/v1/observe/goto", headers=h, json={"id": "c-1", "target": "M8"}).json()["job"]
    ctx.hub.update(b"", {"state": "IDLE", "job": tag, "outcome": ""})
    with http.websocket_connect("/api/v1/ws", headers=h) as ws:
        assert ws.receive_json()["data"]["job"]["state"] == "accepted"
        ctx.hub.update(b"", {"state": "IDLE", "job": tag, "outcome": "ok"})
        msg = _next(ws, "progress")
        assert (msg["data"]["job"], msg["data"]["state"]) == (tag, "done")


def test_websocket_without_a_valid_token_is_closed(http):
    with http.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"auth": "token-inventado"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 4401


def test_websocket_accepts_the_token_in_the_first_message(http, ctx):
    token = pair(http, ctx)["Authorization"].split()[1]
    with http.websocket_connect("/api/v1/ws") as ws:
        ws.send_json({"auth": token})
        assert ws.receive_json()["type"] == "state"


def test_revoking_a_phone_drops_its_live_channel(http, ctx):
    h = pair(http, ctx)
    cid = ctx.pairing.clients()[0].id
    with http.websocket_connect("/api/v1/ws", headers=h) as ws:
        ws.receive_json()
        ctx.pairing.revoke(cid)
        with pytest.raises(WebSocketDisconnect) as e:
            for _ in range(20):
                ws.receive_json()
        assert e.value.code == 4401
