"""Rotas da fase 3 do app: montagem e foco à mão, câmera, prévia, autofoco, plano da noite,
mosaico, Lua e planetas, convite de celular, nome do aparelho e exportar.

Sem rede nem aparelho: o Controller é uma lista de comandos recebidos, e o estado é o que o
teste põe no hub.
"""
from datetime import datetime, timezone

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient                                    # noqa: E402

from src.api import plan as planning                                         # noqa: E402
from src.api.app import ApiContext, create_app                               # noqa: E402
from src.api.identity import DeviceIdentity, b64u, b64u_decode               # noqa: E402
from src.api.pairing import PairingService, pairing_proof                    # noqa: E402
from src.core import catalog as cat                                          # noqa: E402
from src.server.webview import FrameHub                                      # noqa: E402

needs_ongc = pytest.mark.skipif(not cat.HAS_ONGC, reason="pyongc não instalado (OpenNGC)")
WHEN = datetime(2026, 10, 10, 1, 30, tzinfo=timezone.utc)      # 22h30 em São Paulo
IDLE = {"state": "IDLE", "job": None, "outcome": "", "focus_pos": 4200, "focus_range": [0, 10000],
        "mount_ctl": {"parked": False, "tracking": True, "jog": None}}


class FakeLink:
    def status(self):
        return {"connected": True, "ra_deg": 83.82, "dec_deg": -5.39, "error": None}


@pytest.fixture
def ctx(tmp_path):
    ident = DeviceIdentity.load_or_create(tmp_path / "identity")
    c = ApiContext(identity=ident, pairing=PairingService(ident), hub=FrameHub(), submit=None)
    c.commands = []
    c.submit = lambda cmd, tag=None: c.commands.append(cmd)
    c.hub.update(b"", dict(IDLE))
    c.site.now = lambda: WHEN
    c.sessions = lambda: [{"id": "lagoon", "target": "M8", "source": "reference"},
                          {"id": "s-1", "target": "M42", "source": "telescope"}]
    return c


@pytest.fixture
def http(ctx):
    with TestClient(create_app(ctx)) as c:
        yield c


def prove(http, ctx, secret, name):
    """Os dois passos do pareamento, como o app faz, com o segredo que se tem em mãos."""
    nonce = http.post("/api/v1/pair/start", json={"client_name": name}).json()["nonce"]
    proof = b64u(pairing_proof(secret, b64u_decode(nonce), ctx.identity.fingerprint_bytes, name))
    return http.post("/api/v1/pair/finish", json={"client_name": name, "proof": proof})


def pair(http, ctx, name="Pixel de teste", role="owner"):
    """Dono: pela janela, com o segredo do aparelho. Os demais papéis: por convite."""
    if role == "owner":
        ctx.pairing.open_window()
        secret = ctx.identity.pairing_secret
    else:
        secret = ctx.pairing.invite(role=role)
    r = prove(http, ctx, secret, name)
    assert r.status_code == 200, r.text
    assert r.json()["role"] == role
    return {"Authorization": f"Bearer {r.json()['token']}"}


def code(r):
    return r.status_code, r.json()["error"]["code"]


# ---- quem entra -------------------------------------------------------------
@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/focuser"), ("get", "/api/v1/camera"), ("get", "/api/v1/plan"),
    ("get", "/api/v1/solar"), ("get", "/api/v1/network"), ("get", "/api/v1/sessions/s-1/export"),
    ("post", "/api/v1/mount/slew"), ("post", "/api/v1/mount/stop"), ("post", "/api/v1/mount/park"),
    ("post", "/api/v1/mount/tracking"), ("post", "/api/v1/focuser"), ("post", "/api/v1/camera"),
    ("post", "/api/v1/observe/preview"), ("post", "/api/v1/observe/focus"),
    ("post", "/api/v1/observe/body"), ("put", "/api/v1/plan"), ("post", "/api/v1/plan/start"),
    ("post", "/api/v1/plan/skip"), ("post", "/api/v1/mosaic"), ("post", "/api/v1/clients/invite"),
    ("patch", "/api/v1/clients/c-1"), ("put", "/api/v1/device"), ("delete", "/api/v1/sessions/s-1"),
    ("get", "/api/v1/network/scan"), ("post", "/api/v1/network/join"), ("post", "/api/v1/network/mode"),
    ("post", "/api/v1/network/hotspot"), ("delete", "/api/v1/network/known/Casa"),
    ("get", "/api/v1/system/update"), ("post", "/api/v1/system/update/check"),
    ("post", "/api/v1/system/update/install"), ("post", "/api/v1/observe/polar"),
    ("post", "/api/v1/mount/polar/adjust"), ("post", "/api/v1/observe/planetary")])
def test_none_of_the_new_routes_answers_without_a_token(http, ctx, method, path):
    r = getattr(http, method)(path)
    assert r.status_code == 401, (path, r.text)
    assert ctx.commands == []


def test_a_viewer_can_look_but_not_move_anything(http, ctx):
    headers = pair(http, ctx, role="viewer")
    assert http.get("/api/v1/focuser", headers=headers).status_code == 200
    assert http.get("/api/v1/plan", headers=headers).status_code == 200
    for path, body in (("/api/v1/mount/slew", {"dir": "N"}), ("/api/v1/mount/stop", None),
                       ("/api/v1/focuser", {"delta": 10}), ("/api/v1/camera", {"gain": 100}),
                       ("/api/v1/observe/preview", {"id": "c-1"}), ("/api/v1/plan/start", {"id": "c-2"})):
        assert code(http.post(path, json=body, headers=headers)) == (403, "forbidden"), path
    assert code(http.put("/api/v1/plan", json={"items": []}, headers=headers)) == (403, "forbidden")
    assert ctx.commands == []


# ---- montagem à mão ---------------------------------------------------------
def test_state_tells_what_the_simulated_mount_can_do(http, ctx):
    mount = http.get("/api/v1/state", headers=pair(http, ctx)).json()["mount"]
    assert mount["source"] == "sim" and mount["features"] == ["jog", "park", "tracking", "home", "polar"]
    assert (mount["parked"], mount["tracking"], mount["moving"]) == (False, True, None)


def test_jog_carries_a_deadline_and_stop_is_always_accepted(http, ctx):
    headers = pair(http, ctx)
    r = http.post("/api/v1/mount/slew", json={"dir": "E", "rate": 3}, headers=headers)
    assert r.json() == {"moving": "E", "rate": 3, "hold_ms": 800}
    http.post("/api/v1/mount/slew", json={"dir": "N", "hold_ms": 300}, headers=headers)
    assert http.post("/api/v1/mount/stop", headers=headers).json() == {"moving": None}
    assert ctx.commands == ["mount:jog:E:3:800", "mount:jog:N:2:300", "mount:halt"]
    slews = [e for e in ctx.audit.recent(20) if e["action"] == "mount_slew"]
    assert len(slews) == 1, "a rajada de renovações vira um registro só"


@pytest.mark.parametrize("body", [{"dir": "X"}, {"dir": "N", "rate": 9}, {"dir": "N", "hold_ms": 60000}, {}])
def test_jog_refuses_bad_arguments(http, ctx, body):
    assert code(http.post("/api/v1/mount/slew", json=body, headers=pair(http, ctx)))[0] == 400
    assert ctx.commands == []


def test_jog_waits_for_the_running_job_and_for_unpark(http, ctx):
    headers = pair(http, ctx)
    ctx.hub.update(b"", dict(IDLE, state="STACKING"))
    assert code(http.post("/api/v1/mount/slew", json={"dir": "N"}, headers=headers)) == (409, "busy")
    assert code(http.post("/api/v1/mount/park", headers=headers)) == (409, "busy")
    ctx.hub.update(b"", dict(IDLE, state="PREVIEW"))
    assert http.post("/api/v1/mount/slew", json={"dir": "N"}, headers=headers).status_code == 200, \
        "com a câmera ao vivo é justamente quando se enquadra à mão"
    ctx.hub.update(b"", dict(IDLE, mount_ctl={"parked": True, "tracking": False, "jog": None}))
    assert code(http.post("/api/v1/mount/slew", json={"dir": "N"}, headers=headers)) == (409, "parked")
    assert code(http.post("/api/v1/mount/tracking", json={"on": True}, headers=headers)) == (409, "parked")
    assert http.post("/api/v1/mount/unpark", headers=headers).json() == {"accepted": "unpark"}
    assert ctx.commands == ["mount:jog:N:2:800", "mount:unpark"]


def test_park_home_and_tracking_reach_the_controller(http, ctx):
    headers = pair(http, ctx)
    for action in ("park", "home"):
        assert http.post(f"/api/v1/mount/{action}", headers=headers).json() == {"accepted": action}
    assert http.post("/api/v1/mount/tracking", json={"on": False}, headers=headers).json() == {"tracking": False}
    assert code(http.post("/api/v1/mount/dance", headers=headers)) == (404, "not_found")
    assert ctx.commands == ["mount:park", "mount:home", "mount:tracking:off"]


def test_the_real_mount_is_read_only_for_now(http, ctx):
    """A montagem real aparece (posição, conexão), mas mexer nela pelo app ainda não existe:
    a API diz isso em vez de mover o simulador por baixo."""
    ctx.mount_link = FakeLink()
    headers = pair(http, ctx)
    mount = http.get("/api/v1/mount", headers=headers).json()
    assert mount["source"] == "indi" and mount["features"] == [] and mount["connected"] is True
    for path, body in (("/api/v1/mount/slew", {"dir": "N"}), ("/api/v1/mount/park", None),
                       ("/api/v1/mount/tracking", {"on": True})):
        assert code(http.post(path, json=body, headers=headers)) == (501, "not_supported"), path
    assert ctx.commands == []


# ---- foco e câmera ------------------------------------------------------------
def test_focuser_reports_position_range_and_curve(http, ctx):
    ctx.hub.update(b"", dict(IDLE, focus_curve=[[4200, 8.1], [6300, 2.4], [8400, None]], focus_best=6300))
    f = http.get("/api/v1/focuser", headers=pair(http, ctx)).json()
    assert (f["position"], f["min"], f["max"], f["best"], f["source"]) == (4200, 0, 10000, 6300, "sim")
    assert f["curve"] == [{"pos": 4200, "fwhm_px": 8.1}, {"pos": 6300, "fwhm_px": 2.4},
                          {"pos": 8400, "fwhm_px": None}]


def test_manual_focus_steps_and_end_of_travel(http, ctx):
    headers = pair(http, ctx)
    assert http.post("/api/v1/focuser", json={"delta": -100}, headers=headers).json() == \
        {"position": 4100, "at_limit": False}
    assert http.post("/api/v1/focuser", json={"position": 50000}, headers=headers).json() == \
        {"position": 10000, "at_limit": True}
    assert http.post("/api/v1/focuser", json={"delta": -5000}, headers=headers).json() == \
        {"position": 0, "at_limit": True}
    assert ctx.commands == ["focus:move:-100", "focus:goto:50000", "focus:move:-5000"]
    for bad in ({}, {"delta": 10, "position": 20}, {"delta": 999999}):
        assert code(http.post("/api/v1/focuser", json=bad, headers=headers))[0] == 400
    ctx.hub.update(b"", dict(IDLE, state="FOCUSING"))
    assert code(http.post("/api/v1/focuser", json={"delta": 10}, headers=headers)) == (409, "busy")


def test_camera_settings_are_kept_and_honestly_marked_as_not_applied(http, ctx):
    headers = pair(http, ctx)
    cam = http.get("/api/v1/camera", headers=headers).json()
    assert (cam["source"], cam["applied"], cam["exposure_s"], cam["gain"]) == ("sim", False, 30.0, 120)
    assert cam["limits"]["gain"] == [0, 600]
    cam = http.post("/api/v1/camera", json={"exposure_s": 60, "gain": 200}, headers=headers).json()
    assert (cam["exposure_s"], cam["gain"], cam["offset"], cam["applied"]) == (60.0, 200, 10, False)
    assert http.get("/api/v1/state", headers=headers).json()["camera"]["gain"] == 200
    assert code(http.post("/api/v1/camera", json={"gain": 9999}, headers=headers))[0] == 400


def test_preview_and_autofocus_are_jobs(http, ctx):
    headers = pair(http, ctx)
    p = http.post("/api/v1/observe/preview", json={"id": "c-1"}, headers=headers).json()
    f = http.post("/api/v1/observe/focus", json={"id": "c-2"}, headers=headers).json()
    assert (p["kind"], f["kind"]) == ("preview", "focus") and p["job"] != f["job"]
    assert ctx.commands == ["start:preview", "start:focus"]
    ctx.hub.update(b"", dict(IDLE, state="FOCUSING", job=f["job"]))
    assert http.get("/api/v1/state", headers=headers).json()["job"]["steps"] == [{"name": "focus", "state": "running"}]
    ctx.hub.update(b"", dict(IDLE, job=f["job"], outcome="focus_failed"))
    job = http.get("/api/v1/state", headers=headers).json()["job"]
    assert (job["state"], job["error"]) == ("failed", "focus_failed")


# ---- Lua, planetas e Sol ------------------------------------------------------
def test_solar_lists_the_bodies_for_the_site_and_time(http, ctx):
    items = http.get("/api/v1/solar", headers=pair(http, ctx)).json()["items"]
    by_id = {b["id"]: b for b in items}
    assert by_id["saturn"]["up"] is True and by_id["sun"]["up"] is False
    assert by_id["moon"]["phase"] is not None


def test_pointing_at_a_body_is_a_goto_by_coordinates(http, ctx):
    headers = pair(http, ctx)
    job = http.post("/api/v1/observe/body", json={"id": "c-1", "body": "saturn"}, headers=headers).json()
    assert (job["kind"], job["target"]) == ("goto", "Saturno")
    assert ctx.commands[0].startswith("start:goto:@10.7")
    assert code(http.post("/api/v1/observe/body", json={"id": "c-2", "body": "plutao"}, headers=headers)) == \
        (404, "not_found")


def test_the_sun_needs_the_filter_confirmation(http, ctx):
    headers = pair(http, ctx)
    r = http.post("/api/v1/observe/body", json={"id": "c-1", "body": "sun"}, headers=headers)
    assert code(r) == (400, "solar_filter_required") and ctx.commands == []
    r = http.post("/api/v1/observe/body", json={"id": "c-2", "body": "sun", "filter_confirmed": True},
                  headers=headers)
    assert r.status_code == 200 and len(ctx.commands) == 1
    assert any(e["action"] == "sun_filter_confirmed" for e in ctx.audit.recent(10))


# ---- plano da noite e mosaico ---------------------------------------------------
@needs_ongc
def test_plan_is_stored_scheduled_and_survives_restart(http, ctx, tmp_path):
    ctx.plan = planning.PlanStore(tmp_path / "plan.json")
    headers = pair(http, ctx)
    assert http.get("/api/v1/plan", headers=headers).json()["items"] == []
    body = {"items": [{"target": "m42", "frames": 40}, {"target": "NGC 253", "frames": 20, "exposure_s": 60,
                                                         "mosaic": [1, 2]}]}
    plan = http.put("/api/v1/plan", json=body, headers=headers).json()
    first, second = plan["items"]
    assert (first["id"], first["target"], first["type"], first["frames"]) == ("p-1", "M42", "nebula", 40)
    assert (second["target"], second["mosaic"], second["exposure_s"]) == ("NGC253", [1, 2], 60.0)
    assert first["duration_s"] == 120 + 40 * 30 and second["duration_s"] == 2 * (120 + 20 * 60)
    assert plan["night"]["start"] == "2026-10-10T01:30:00Z" and plan["running"] is False
    assert planning.PlanStore(tmp_path / "plan.json").items()[0]["target"] == "M42"


@needs_ongc
def test_schedule_orders_by_the_queue_and_says_why_something_does_not_fit():
    """22h30 em São Paulo: NGC 253 (Escultor) está alto; M42 (Órion) só sobe de madrugada; e
    NGC 188, colado no polo norte, não nasce nunca daqui."""
    items = planning.normalize([{"target": "NGC253", "frames": 20}, {"target": "M42", "frames": 20},
                                {"target": "NGC188", "frames": 20}])
    plan = planning.schedule(items, -23.55, -46.63, WHEN)
    scultor, orion, polar = plan["items"]
    assert scultor["status"] == "ok" and scultor["start"] == "2026-10-10T01:30:00Z"
    assert scultor["alt_start_deg"] > 60
    assert orion["status"] == "ok" and orion["start"] > scultor["end"], "espera Órion subir"
    assert orion["alt_start_deg"] >= 25
    assert (polar["status"], polar["start"]) == ("never_up", None)
    assert plan["free_s"] > 0 and plan["total_s"] == 3 * (120 + 20 * 30)
    queue = planning.runnable(items, -23.55, -46.63, WHEN)
    assert [q["skip"] for q in queue] == [None, None, "below_horizon"]


@needs_ongc
def test_an_item_that_runs_past_dawn_is_flagged():
    items = planning.normalize([{"target": "NGC253", "frames": 5000, "exposure_s": 60}])
    assert planning.schedule(items, -23.55, -46.63, WHEN)["items"][0]["status"] == "after_dawn"


@needs_ongc
@pytest.mark.parametrize("items,field", [
    ([{"target": "alvo inventado"}], "items[0].target"),
    ([{"target": "M42", "frames": 0}], "items[0].frames"),
    ([{"target": "M42", "mosaic": [9, 1]}], "items[0].mosaic"),
    ([{"target": "M42", "min_alt_deg": 95}], "items[0].min_alt_deg"),
    ([{"target": "M42", "overlap": 0.9}], "items[0].overlap"),
    ("M42", "items"), ([{"target": "M42"}] * 41, "items")])
def test_plan_refuses_bad_items_naming_the_field(http, ctx, items, field):
    r = http.put("/api/v1/plan", json={"items": items}, headers=pair(http, ctx))
    assert code(r) == (400, "invalid_argument") and r.json()["error"]["message"].startswith(field)
    assert ctx.plan.items() == []


@needs_ongc
def test_night_starts_once_runs_in_order_and_can_skip(http, ctx):
    headers = pair(http, ctx)
    assert code(http.post("/api/v1/plan/start", json={"id": "c-0"}, headers=headers)) == (400, "invalid_argument")
    assert code(http.post("/api/v1/plan/skip", headers=headers)) == (409, "not_running")
    http.put("/api/v1/plan", json={"items": [{"target": "NGC253"}, {"target": "NGC188"}]}, headers=headers)
    job = http.post("/api/v1/plan/start", json={"id": "c-1"}, headers=headers).json()
    assert job["kind"] == "plan"
    assert http.post("/api/v1/plan/start", json={"id": "c-1"}, headers=headers).json()["job"] == job["job"]
    assert ctx.commands == ["start:plan"], "o mesmo comando reenviado não começa a noite de novo"
    assert [q["skip"] for q in ctx.plan_queue()] == [None, "below_horizon"]
    ctx.hub.update(b"", dict(IDLE, state="STACKING", job=job["job"], plan=[
        {"id": "p-1", "target": "NGC253", "status": "running", "accepted": 3, "snr": 2.0, "reason": ""}]))
    assert http.get("/api/v1/plan", headers=headers).json()["running"] is True
    assert http.get("/api/v1/state", headers=headers).json()["night"][0]["status"] == "running"
    assert code(http.put("/api/v1/plan", json={"items": []}, headers=headers)) == (409, "busy")
    assert http.post("/api/v1/plan/skip", headers=headers).json() == {"skipped": True}
    http.post("/api/v1/plan/stop", json={"id": "c-2"}, headers=headers)
    assert ctx.commands == ["start:plan", "skip", "stop"]


@needs_ongc
def test_mosaic_grid_covers_the_target_with_overlap(http, ctx):
    headers = pair(http, ctx)
    grid = http.post("/api/v1/mosaic", json={"target": "M31", "rows": 2, "cols": 3, "overlap": 0.2},
                     headers=headers).json()
    assert (grid["target"], grid["rows"], grid["cols"]) == ("M31", 2, 3) and len(grid["panels"]) == 6
    fov_w, fov_h = grid["field_deg"]
    wide, tall = grid["covers_deg"]                    # campo + (n-1) passos de 80% do campo
    assert abs(wide - (fov_w + 2 * fov_w * 0.8)) < 0.02 and abs(tall - (fov_h + fov_h * 0.8)) < 0.02
    assert grid["covers_object"] is True, "Andrômeda (178') cabe num 2x3"
    north, south = grid["panels"][0], grid["panels"][3]
    assert north["name"] == "R0C0" and north["dec_deg"] > south["dec_deg"]
    assert grid["panels"][0]["ra_deg"] > grid["panels"][2]["ra_deg"], "a coluna 0 é a do leste"
    small = http.post("/api/v1/mosaic", json={"target": "M31", "rows": 1, "cols": 1}, headers=headers).json()
    assert small["covers_object"] is False
    assert code(http.post("/api/v1/mosaic", json={"target": "nada", "rows": 1, "cols": 1},
                          headers=headers)) == (404, "not_found")
    assert code(http.post("/api/v1/mosaic", json={"target": "M31", "rows": 7}, headers=headers))[0] == 400


def test_panel_grid_stretches_right_ascension_near_the_pole():
    from src.core.mosaic import panel_grid_radec
    low, _ = panel_grid_radec(100.0, 0.0, 1, 2, (2.0, 1.0), 0.0)
    high, covers = panel_grid_radec(100.0, 60.0, 1, 2, (2.0, 1.0), 0.0)
    assert round(low[0]["ra_deg"] - low[1]["ra_deg"], 3) == 2.0
    assert round(high[0]["ra_deg"] - high[1]["ra_deg"], 3) == 4.0, "a 60 graus, 1 grau de céu = 2 de RA"
    assert covers == (4.0, 1.0)


# ---- celulares, nome e rede -----------------------------------------------------
def _invite_secret(uri):
    from urllib.parse import parse_qs, urlsplit
    return b64u_decode(parse_qs(urlsplit(uri).query)["s"][0])


def test_an_owner_invites_another_phone_with_a_one_time_code(http, ctx):
    """O convite: um segredo NOVO, de uso único, com o papel que o dono escolheu. O segredo do
    aparelho (o da etiqueta) não viaja pela API nem aparece no convite."""
    ctx.qr_svg = lambda uri: f"<svg>{len(uri)}</svg>"
    owner = pair(http, ctx)
    assert http.get("/api/v1/info").json()["pairing_open"] is False
    r = http.post("/api/v1/clients/invite", json={"role": "viewer", "minutes": 2}, headers=owner)
    inv = r.json()
    assert inv["role"] == "viewer" and inv["expires_s"] == 120 and inv["qr_svg"].startswith("<svg>")
    assert inv["uri"].startswith("tele://pair?v=1&id=" + ctx.identity.device_id)
    assert "host=testserver" in inv["uri"]
    secret = _invite_secret(inv["uri"])
    assert secret != ctx.identity.pairing_secret
    assert b64u(ctx.identity.pairing_secret) not in r.text
    assert http.get("/api/v1/info").json()["pairing_open"] is True

    # com só o convite valendo, o segredo do aparelho NÃO entra (e não vira dono)
    assert code(prove(http, ctx, ctx.identity.pairing_secret, "Curioso")) == (403, "pairing_rejected")
    guest = prove(http, ctx, secret, "Celular da visita").json()
    assert guest["role"] == "viewer"
    assert http.get("/api/v1/info").json()["pairing_open"] is False, "um convite, um celular"
    assert code(http.post("/api/v1/pair/start", json={"client_name": "De novo"})) == (403, "pairing_closed")
    visitor = {"Authorization": f"Bearer {guest['token']}"}
    assert code(http.post("/api/v1/clients/invite", json={}, headers=visitor)) == (403, "forbidden")
    assert not any("uri" in e or "secret" in e for e in ctx.audit.recent(20)), "o registro não guarda o código"


def test_an_invite_code_does_not_make_an_owner_and_expires(ctx, tmp_path):
    now = [1000.0]
    service = PairingService(ctx.identity, store=tmp_path / "c.json", clock=lambda: now[0])
    secret = service.invite(seconds=60, role="operator")

    def finish(with_secret, name):
        nonce, _ = service.start(name)
        return service.finish(name, b64u(pairing_proof(with_secret, b64u_decode(nonce),
                                                       ctx.identity.fingerprint_bytes, name)))
    # janela do dono aberta junto com o convite: cada segredo dá o SEU papel
    service.open_window()
    assert finish(ctx.identity.pairing_secret, "Dono")[1].role == "owner"
    assert finish(secret, "Operador")[1].role == "operator"
    with pytest.raises(Exception) as e:
        service.start("Terceiro")
    assert e.value.code == "pairing_closed"
    # um convite novo cancela o anterior, e vence sozinho
    old = service.invite(seconds=60, role="viewer")
    new = service.invite(seconds=60, role="viewer")
    with pytest.raises(Exception) as e:
        finish(old, "Com o código velho")
    assert e.value.code == "pairing_rejected"
    now[0] += 61
    assert service.window_open is False
    with pytest.raises(Exception) as e:
        finish(new, "Atrasado")
    assert e.value.code == "pairing_closed"
    with pytest.raises(Exception) as e:
        service.invite(role="rei")
    assert e.value.code == "invalid_argument"


def test_roles_can_change_but_the_last_owner_stays(http, ctx):
    owner = pair(http, ctx)
    guest = pair(http, ctx, name="Outro celular", role="operator")
    ids = {c["name"]: c["id"] for c in http.get("/api/v1/clients", headers=owner).json()["items"]}
    assert http.patch(f"/api/v1/clients/{ids['Outro celular']}", json={"role": "viewer"}, headers=owner).json() == \
        {"id": ids["Outro celular"], "role": "viewer"}
    assert code(http.post("/api/v1/observe/preview", json={"id": "c-1"}, headers=guest)) == (403, "forbidden")
    r = http.patch(f"/api/v1/clients/{ids['Pixel de teste']}", json={"role": "viewer"}, headers=owner)
    assert code(r) == (409, "last_owner")
    assert code(http.patch("/api/v1/clients/c-nao-existe", json={"role": "viewer"}, headers=owner)) == (404, "not_found")
    assert code(http.patch(f"/api/v1/clients/{ids['Outro celular']}", json={"role": "rei"}, headers=owner))[0] == 400


def test_the_owner_names_the_telescope(http, ctx):
    saved = []
    ctx.save_name = saved.append
    owner = pair(http, ctx)
    assert http.put("/api/v1/device", json={"name": "  Tucana   do quintal "}, headers=owner).json() == \
        {"name": "Tucana do quintal"}
    assert http.get("/api/v1/info").json()["name"] == "Tucana do quintal" and saved == ["Tucana do quintal"]
    for bad in ({"name": ""}, {"name": "x" * 41}, {"name": "a\nb\x00"}, {}):
        assert code(http.put("/api/v1/device", json=bad, headers=owner))[0] == 400
    assert code(http.put("/api/v1/device", json={"name": "Outro"}, headers=pair(http, ctx, "Op", "operator"))) == \
        (403, "forbidden")


def test_network_is_visible_but_changing_it_is_not_enabled(http, ctx):
    """No aparelho de verdade a troca de rede fica desligada até ser testada na bancada: a API
    mostra a rede e recusa mexer nela."""
    owner = pair(http, ctx)
    net = http.get("/api/v1/network", headers=owner).json()
    assert net["enabled"] is False and net["mode"] == "unknown" and net["hostname"]
    assert net["hotspot"] is None and net["known"] == []
    for method, path, body in (("post", "/api/v1/network/mode", {"mode": "field"}),
                               ("post", "/api/v1/network/join", {"ssid": "Casa", "psk": "12345678"}),
                               ("post", "/api/v1/network/hotspot", {"psk": "12345678"}),
                               ("get", "/api/v1/network/scan", None),
                               ("delete", "/api/v1/network/known/Casa", None)):
        r = http.request(method.upper(), path, json=body, headers=owner)
        assert code(r) == (501, "not_enabled"), path


def test_system_reports_uptime_and_that_updates_are_not_available(http, ctx):
    owner = pair(http, ctx)
    s = http.get("/api/v1/system", headers=owner).json()
    assert s["uptime_s"] >= 0 and s["update"] == {"enabled": False} and s["firmware"] is None
    u = http.get("/api/v1/system/update", headers=owner).json()
    assert (u["enabled"], u["available"], u["state"]) == (False, None, "idle") and u["current"]
    assert code(http.post("/api/v1/system/update/check", headers=owner)) == (501, "not_enabled")


# ---- exportar e apagar ----------------------------------------------------------
def test_export_sends_the_file_with_its_name_and_type(http, ctx, tmp_path):
    big = tmp_path / "pilha.fits"
    big.write_bytes(b"SIMPLE  =" + b"0" * 5000)
    asked = []

    def export(session_id, fmt, max_side):
        asked.append((session_id, fmt, max_side))
        if fmt == "fits":
            return big, "application/fits", f"{session_id}.fits"
        return (b"II*\x00tiff" if fmt == "tif" else b"\xff\xd8jpeg"), f"image/{'tiff' if fmt == 'tif' else 'jpeg'}", \
            f"{session_id}.{fmt}"
    ctx.export_session = export
    headers = pair(http, ctx)
    r = http.get("/api/v1/sessions/s-1/export?format=tif&max_side=2000", headers=headers)
    assert r.status_code == 200 and r.headers["content-type"] == "image/tiff" and r.content.startswith(b"II*")
    assert r.headers["content-disposition"] == 'attachment; filename="s-1.tif"'
    r = http.get("/api/v1/sessions/s-1/export?format=fits", headers=headers)
    assert r.status_code == 200 and len(r.content) == 5009, "o arquivo grande vai inteiro"
    assert http.get("/api/v1/sessions/s-1/export", headers=headers).content == b"\xff\xd8jpeg"
    assert asked == [("s-1", "tif", 2000), ("s-1", "fits", 0), ("s-1", "jpg", 0)]
    assert code(http.get("/api/v1/sessions/s-1/export?format=exe", headers=headers))[0] == 400
    assert code(http.get("/api/v1/sessions/nada/export", headers=headers)) == (404, "not_found")
    ctx.export_session = lambda *a: None
    assert code(http.get("/api/v1/sessions/s-1/export", headers=headers)) == (404, "not_found")


def test_reference_images_are_never_deleted_from_the_app(http, ctx):
    gone = []
    ctx.delete_session = lambda sid: gone.append(sid) or True
    owner = pair(http, ctx)
    assert code(http.delete("/api/v1/sessions/lagoon", headers=owner)) == (409, "protected")
    assert http.delete("/api/v1/sessions/s-1", headers=owner).json() == {"deleted": "s-1"}
    assert gone == ["s-1"]
    op = pair(http, ctx, "Operador", "operator")
    assert code(http.delete("/api/v1/sessions/s-1", headers=op)) == (403, "forbidden")


def test_channel_sends_focus_and_night_only_when_they_change(ctx):
    from src.api.app import build_state, state_messages
    first = build_state(ctx)
    ctx.hub.update(b"", dict(IDLE, focus_pos=4300))
    second = build_state(ctx)
    assert [k for k, _ in state_messages(first, second)] == ["focus"], \
        "mexer no foco manda só o foco, não o retrato inteiro"
    ctx.hub.update(b"", dict(IDLE, focus_pos=4300, plan=[{"id": "p-1", "status": "running"}]))
    third = build_state(ctx)
    assert state_messages(second, third) == [("night", [{"id": "p-1", "status": "running"}])]
