"""O que faltava para o app ficar completo: rede do telescópio (casa e campo), atualização,
alinhamento polar e captura planetária — as rotas e os adapters de mentira com que as telas
são desenvolvidas. Sem rede nem aparelho.
"""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from src.api.network import NetworkError, SimNetwork                         # noqa: E402
from src.api.updates import SimUpdater, UpdateError                          # noqa: E402
from tests.test_api_phase3 import IDLE, FakeLink, code, ctx, http, pair      # noqa: E402,F401


class Clock:
    """Um relógio que só anda quando o teste manda."""
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


# ---- rede: o adapter de mentira ----------------------------------------------
def test_joining_home_wifi_happens_after_the_answer_and_keeps_the_network():
    """A troca só acontece DEPOIS da resposta: o celular precisa ouvir "aceito" antes de a
    rede cair. Depois, a rede fica guardada."""
    clock = Clock()
    net = SimNetwork(switch_s=3.0, clock=clock)
    assert net.status()["mode"] == "field" and net.status()["hotspot"]["active"] is True
    assert net.join("Casa", "senha-de-casa") == {"accepted": True, "reconnect_s": 8}
    during = net.status()
    assert (during["mode"], during["switching"]) == ("field", True), "ainda não trocou"
    clock.t += 3.1
    after = net.status()
    assert (after["mode"], after["wifi"], after["switching"]) == ("home", {"ssid": "Casa", "signal": 78}, False)
    assert after["known"] == ["Casa"] and after["hotspot"]["active"] is False and after["last_error"] is None


def test_a_wrong_password_leaves_the_telescope_where_it_was_and_says_why():
    """O aparelho nunca fica mudo: se a rede nova não deu certo, ele continua no WiFi próprio
    e conta o motivo quando o app o reencontra."""
    clock = Clock()
    net = SimNetwork(clock=clock)
    net.join("Casa", "senha-errada")
    clock.t += 10
    st = net.status()
    assert (st["mode"], st["wifi"], st["last_error"], st["known"]) == ("field", None, "wrong_password", [])
    net.nearby.pop("Vizinho 5G")
    with pytest.raises(NetworkError) as e:
        net.join("Vizinho 5G", "outra-senha")
    assert e.value.code == "not_found"
    with pytest.raises(NetworkError) as e:
        net.join("Casa", None)
    assert e.value.code == "invalid_argument", "rede com senha pede a senha"
    net.join("Visitantes", None)                       # rede aberta entra sem senha
    clock.t += 10
    assert net.status()["wifi"]["ssid"] == "Visitantes"


def test_a_network_that_vanishes_during_the_switch_does_not_strand_the_telescope():
    clock = Clock()
    net = SimNetwork(clock=clock)
    net.join("Casa", "senha-de-casa")
    net.nearby.pop("Casa")                             # o roteador desligou no meio
    clock.t += 10
    assert (net.status()["mode"], net.status()["last_error"]) == ("field", "not_found")


def test_switching_between_home_and_field_uses_what_is_known():
    clock = Clock()
    net = SimNetwork(clock=clock)
    with pytest.raises(NetworkError) as e:
        net.set_mode("home")
    assert e.value.code == "no_known_network", "sem rede guardada não há casa para onde ir"
    net.join("Casa", "senha-de-casa")
    clock.t += 10
    assert net.set_mode("home") == {"accepted": True, "reconnect_s": 0}, "já está em casa"
    net.set_mode("field")
    clock.t += 10
    assert net.status()["mode"] == "field" and net.status()["wifi"] is None
    net.set_mode("home")                               # volta sozinho para a rede guardada
    clock.t += 10
    assert net.status()["wifi"]["ssid"] == "Casa"
    net.set_mode("field")
    clock.t += 10
    net.join("Casa", None)                             # rede guardada: entra sem pedir a senha de novo
    clock.t += 10
    assert net.status()["wifi"]["ssid"] == "Casa" and net.status()["last_error"] is None
    with pytest.raises(NetworkError) as e:
        net.forget("Casa")
    assert e.value.code == "in_use", "não esquece a rede em que está"
    net.set_mode("field")
    clock.t += 10
    assert net.forget("Casa") == {"forgotten": "Casa"} and net.status()["known"] == []
    with pytest.raises(NetworkError):
        net.set_mode("praia")


def test_scan_lists_what_the_telescope_sees_strongest_first():
    net = SimNetwork()
    rows = net.scan()
    assert [r["ssid"] for r in rows] == ["Casa", "Visitantes", "Vizinho 5G"]
    assert rows[0] == {"ssid": "Casa", "signal": 78, "secure": True, "known": False}
    assert rows[1]["secure"] is False


def test_the_hotspot_password_is_for_the_owner_only_and_has_wifi_rules():
    net = SimNetwork(hotspot_psk="ceu-estrelado")
    assert "psk" not in net.status()["hotspot"] and net.status(owner=True)["hotspot"]["psk"] == "ceu-estrelado"
    assert net.status()["hotspot"]["address"] == "10.42.0.1", "onde achar o aparelho no WiFi próprio"
    for bad in ("curta", "x" * 64, "com\nquebra-de-linha"):
        with pytest.raises(NetworkError):
            net.set_hotspot_psk(bad)
    assert net.set_hotspot_psk("outra-senha-boa")["changed"] is True
    assert net.status(owner=True)["hotspot"]["psk"] == "outra-senha-boa"


# ---- rede: as rotas -------------------------------------------------------------
def test_network_routes_drive_the_adapter_and_never_log_the_password(http, ctx):
    clock = Clock()
    ctx.network = SimNetwork(clock=clock)
    owner = pair(http, ctx)
    net = http.get("/api/v1/network", headers=owner).json()
    assert (net["enabled"], net["mode"], net["hotspot"]["psk"]) == (True, "field", "ceu-estrelado")
    assert net["hostname"]
    scan = http.get("/api/v1/network/scan", headers=owner).json()["items"]
    assert scan[0]["ssid"] == "Casa"
    r = http.post("/api/v1/network/join", json={"ssid": "Casa", "psk": "senha-de-casa"}, headers=owner)
    assert r.json() == {"accepted": True, "reconnect_s": 8}
    clock.t += 10
    assert http.get("/api/v1/network", headers=owner).json()["wifi"]["ssid"] == "Casa"
    assert http.post("/api/v1/network/mode", json={"mode": "field"}, headers=owner).json()["accepted"] is True
    clock.t += 10
    assert http.post("/api/v1/network/hotspot", json={"psk": "senha-nova-do-campo"}, headers=owner).json()["changed"]
    assert http.delete("/api/v1/network/known/Casa", headers=owner).json() == {"forgotten": "Casa"}
    log = str(ctx.audit.recent(50))
    assert "network_join" in log and "senha" not in log, "o registro guarda a rede, nunca a senha"
    # erros com o código certo
    assert code(http.post("/api/v1/network/join", json={"ssid": "Nao existe", "psk": "x" * 8}, headers=owner)) == \
        (404, "not_found")
    assert code(http.post("/api/v1/network/mode", json={"mode": "home"}, headers=owner)) == (409, "no_known_network")
    assert code(http.post("/api/v1/network/mode", json={"mode": "praia"}, headers=owner))[0] == 400
    assert code(http.post("/api/v1/network/hotspot", json={"psk": "curta"}, headers=owner))[0] == 400
    assert code(http.delete("/api/v1/network/known/Casa", headers=owner)) == (404, "not_found")


def test_only_the_owner_changes_the_network_or_sees_the_hotspot_password(http, ctx):
    ctx.network = SimNetwork()
    operator = pair(http, ctx, "Operador", "operator")
    net = http.get("/api/v1/network", headers=operator).json()
    assert net["enabled"] is True and "psk" not in net["hotspot"]
    for method, path, body in (("get", "/api/v1/network/scan", None),
                               ("post", "/api/v1/network/join", {"ssid": "Casa", "psk": "senha-de-casa"}),
                               ("post", "/api/v1/network/mode", {"mode": "field"}),
                               ("post", "/api/v1/network/hotspot", {"psk": "12345678"}),
                               ("delete", "/api/v1/network/known/Casa", None)):
        assert code(http.request(method.upper(), path, json=body, headers=operator)) == (403, "forbidden"), path
    assert ctx.network.status()["switching"] is False


# ---- atualização ------------------------------------------------------------------
def test_update_is_found_installed_and_the_version_changes():
    clock = Clock()
    up = SimUpdater(current="0.1.0", newer="0.2.0", install_s=6.0, clock=clock)
    assert up.status() == {"enabled": True, "current": "0.1.0", "available": None, "state": "idle",
                           "progress": None, "error": None}
    with pytest.raises(UpdateError) as e:
        up.install()
    assert e.value.code == "nothing_to_install"
    up.check()
    assert up.status()["state"] == "checking"
    clock.t += 1.1
    found = up.status()
    assert found["state"] == "idle" and found["available"]["version"] == "0.2.0" and found["available"]["notes"]
    up.install()
    seen = []
    for _ in range(40):
        st = up.status()
        if not seen or seen[-1] != st["state"]:
            seen.append(st["state"])
        clock.t += 0.25
    assert seen == ["downloading", "installing", "restarting", "idle"]
    done = up.status()
    assert (done["current"], done["available"], done["error"]) == ("0.2.0", None, None)
    up.check()
    clock.t += 1.1
    assert up.status()["available"] is None, "já está na última"


def test_a_failed_install_keeps_the_previous_version_and_says_so():
    clock = Clock()
    up = SimUpdater(current="0.1.0", newer="0.2.0", clock=clock)
    up.check()
    clock.t += 1.1
    up.fail_next = True
    up.install()
    with pytest.raises(UpdateError) as e:
        up.check()
    assert e.value.code == "busy", "uma de cada vez"
    clock.t += 5
    st = up.status()
    assert (st["state"], st["error"], st["current"]) == ("failed", "install_failed", "0.1.0")
    assert st["available"]["version"] == "0.2.0", "dá para tentar de novo"
    up.install()
    clock.t += 9
    assert up.status()["current"] == "0.2.0"


def test_update_routes_are_for_the_owner_and_wait_for_the_running_job(http, ctx):
    clock = Clock()
    ctx.updater = SimUpdater(current="0.1.0", newer="0.2.0", clock=clock)
    owner = pair(http, ctx)
    assert http.get("/api/v1/system", headers=owner).json()["update"] == {"enabled": True}
    assert http.post("/api/v1/system/update/check", headers=owner).json()["state"] == "checking"
    clock.t += 1.1
    assert http.get("/api/v1/system/update", headers=owner).json()["available"]["version"] == "0.2.0"
    ctx.hub.update(b"", dict(IDLE, state="STACKING"))
    assert code(http.post("/api/v1/system/update/install", headers=owner)) == (409, "busy")
    ctx.hub.update(b"", dict(IDLE))
    assert http.post("/api/v1/system/update/install", headers=owner).json()["state"] == "downloading"
    assert code(http.post("/api/v1/system/update/install", headers=owner)) == (409, "busy")
    assert code(http.post("/api/v1/system/update/voar", headers=owner)) == (404, "not_found")
    operator = pair(http, ctx, "Operador", "operator")
    assert http.get("/api/v1/system/update", headers=operator).status_code == 200
    assert code(http.post("/api/v1/system/update/check", headers=operator)) == (403, "forbidden")
    assert sorted(e["action"] for e in ctx.audit.recent(20) if e["action"].startswith("update")) == \
        ["update_check", "update_install"]


# ---- alinhamento polar ---------------------------------------------------------------
def test_polar_alignment_is_a_job_and_its_result_travels_in_the_state(http, ctx):
    headers = pair(http, ctx)
    assert http.get("/api/v1/state", headers=headers).json()["polar"] is None
    job = http.post("/api/v1/observe/polar", json={"id": "c-1"}, headers=headers).json()
    assert job["kind"] == "polar" and ctx.commands == ["start:polar"]
    ctx.hub.update(b"", dict(IDLE, state="SOLVING", job=job["job"],
                             polar={"step": 2, "points": 3, "measured": False}))
    st = http.get("/api/v1/state", headers=headers).json()
    assert st["polar"] == {"step": 2, "points": 3, "measured": False}
    assert [s["name"] for s in st["job"]["steps"]] == ["solve"]
    ctx.hub.update(b"", dict(IDLE, job=job["job"], outcome="polar_failed"))
    failed = http.get("/api/v1/state", headers=headers).json()["job"]
    assert (failed["state"], failed["error"]) == ("failed", "polar_failed")


def test_the_simulated_screws_are_reachable_and_the_real_mount_is_not_touched(http, ctx):
    headers = pair(http, ctx)
    r = http.post("/api/v1/mount/polar/adjust", json={"alt_arcmin": -38.0, "az_arcmin": 52.5}, headers=headers)
    assert r.json() == {"adjusted": True} and ctx.commands == ["polar:adjust:-38.000:52.500"]
    for bad in ({"alt_arcmin": 9999, "az_arcmin": 0}, {"alt_arcmin": 1}, {}):
        assert code(http.post("/api/v1/mount/polar/adjust", json=bad, headers=headers))[0] == 400
    ctx.hub.update(b"", dict(IDLE, state="STACKING"))
    assert code(http.post("/api/v1/observe/polar", json={"id": "c-2"}, headers=headers)) == (409, "busy")
    ctx.hub.update(b"", dict(IDLE))
    ctx.mount_link = FakeLink()                        # com a montagem real: ainda não
    assert code(http.post("/api/v1/observe/polar", json={"id": "c-3"}, headers=headers)) == (501, "not_supported")
    assert code(http.post("/api/v1/mount/polar/adjust", json={"alt_arcmin": 1, "az_arcmin": 1},
                          headers=headers)) == (501, "not_supported")
    assert len(ctx.commands) == 1


def test_channel_sends_polar_and_capture_on_their_own(ctx):
    from src.api.app import build_state, state_messages
    first = build_state(ctx)
    ctx.hub.update(b"", dict(IDLE, polar={"alt_arcmin": 3.0, "measured": True}))
    second = build_state(ctx)
    assert state_messages(first, second) == [("polar", {"alt_arcmin": 3.0, "measured": True})]
    ctx.hub.update(b"", dict(IDLE, polar=second["polar"], planet={"body": "moon", "frames": 5, "total": 60}))
    third = build_state(ctx)
    assert state_messages(second, third) == [("capture", {"body": "moon", "frames": 5, "total": 60})]
    ctx.hub.update(b"", dict(IDLE, polar=second["polar"], planet=None))
    assert state_messages(third, build_state(ctx)) == [("capture", None)], "o fim da captura também é notícia"


# ---- captura planetária ----------------------------------------------------------------
def test_planetary_capture_points_at_the_body_and_carries_the_settings(http, ctx):
    headers = pair(http, ctx)
    job = http.post("/api/v1/observe/planetary", json={"id": "c-1", "body": "saturn"}, headers=headers).json()
    assert (job["kind"], job["target"]) == ("planetary", "Saturno")
    body, frames, keep, ra, dec = ctx.commands[0].removeprefix("start:planetary:").split("|")
    assert (body, frames, keep) == ("saturn", "300", "15")
    assert abs(float(ra) - 10.71) < 0.2 and abs(float(dec) - 1.66) < 0.2, "as coordenadas de agora"
    http.post("/api/v1/observe/planetary", headers=headers,
              json={"id": "c-2", "body": "moon", "frames": 500, "keep_percent": 10, "point": False})
    assert ctx.commands[1] == "start:planetary:moon|500|10", "sem apontar: grava de onde está"


@pytest.mark.parametrize("body,status", [
    ({"id": "c-1", "body": "sun"}, 404),               # o Sol não entra neste modo
    ({"id": "c-1", "body": "plutao"}, 404),
    ({"id": "c-1", "body": "moon", "frames": 5}, 400),
    ({"id": "c-1", "body": "moon", "keep_percent": 90}, 400),
    ({"body": "moon"}, 400)])
def test_planetary_capture_refuses_what_it_cannot_do(http, ctx, body, status):
    assert http.post("/api/v1/observe/planetary", json=body, headers=pair(http, ctx)).status_code == status
    assert ctx.commands == []


def test_capture_progress_travels_in_the_state(http, ctx):
    headers = pair(http, ctx)
    job = http.post("/api/v1/observe/planetary", json={"id": "c-1", "body": "jupiter"}, headers=headers).json()
    planet = {"body": "jupiter", "frames": 120, "total": 300, "kept": 45, "keep": 0.15, "done": False}
    ctx.hub.update(b"", dict(IDLE, state="CAPTURING", job=job["job"], planet=planet))
    st = http.get("/api/v1/state", headers=headers).json()
    assert st["capture"] == planet and st["state"] == "CAPTURING"
    assert st["job"]["steps"] == [{"name": "capture", "state": "running"}]


# ---- anúncio na rede -----------------------------------------------------------------------
def test_advertiser_without_the_library_says_no_instead_of_crashing(monkeypatch):
    import builtins

    from src.api.server import Advertiser
    real = builtins.__import__

    def without_zeroconf(name, *args, **kwargs):
        if name == "zeroconf":
            raise ImportError("sem zeroconf")
        return real(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_zeroconf)
    advert = Advertiser("tele-0b04", "Telescópio", 8443, address="192.168.3.221")
    assert advert.start() is False
    advert.stop()                                      # parar sem ter começado não quebra


def test_advertiser_announces_the_device_id_when_the_library_is_there(monkeypatch):
    """Confere O QUE seria anunciado, sem abrir rede: o anunciador de verdade (multicast) fica
    trocado por um de mentira. Nenhum teste do CI depende de rede."""
    zeroconf = pytest.importorskip("zeroconf")
    from src.api.server import SERVICE_TYPE, Advertiser
    announced = []

    class NoNetwork:
        def register_service(self, info):
            announced.append(info)

        def unregister_service(self, info):
            announced.remove(info)

        def close(self):
            announced.append("fechado")

    monkeypatch.setattr(zeroconf, "Zeroconf", NoNetwork)
    advert = Advertiser("tele-0b04", "Telescópio do quintal", 8443, address="192.168.3.221")
    assert advert.start() is True
    (info,) = announced
    assert info.type == SERVICE_TYPE and info.port == 8443
    assert info.properties[b"id"] == b"tele-0b04" and info.properties[b"api"] == b"1"
    assert info.name == "Telescópio do quintal tele-0b04." + SERVICE_TYPE
    assert info.parsed_addresses() == ["192.168.3.221"]
    advert.stop()
    assert announced == ["fechado"], "parou: o anúncio sai da rede"


# ---- achados da revisão: guardas, papéis e o contrato dos adapters --------------------------
def test_the_mount_is_not_moved_by_hand_during_a_planetary_capture(http, ctx):
    """Gravando, a montagem é do modo: movimento manual, estacionar e casa respondem "ocupado"."""
    headers = pair(http, ctx)
    ctx.hub.update(b"", dict(IDLE, state="CAPTURING"))
    assert code(http.post("/api/v1/mount/slew", json={"dir": "E", "rate": 2, "hold_ms": 800},
                          headers=headers)) == (409, "busy")
    for action in ("park", "home"):
        assert code(http.post(f"/api/v1/mount/{action}", headers=headers)) == (409, "busy"), action
    assert code(http.post("/api/v1/observe/polar", json={"id": "c-9"}, headers=headers)) == (409, "busy")
    assert http.post("/api/v1/mount/stop", headers=headers).status_code == 200, "parar nunca é recusado"
    assert ctx.commands == ["mount:halt"]


def test_resending_the_polar_command_returns_the_same_job_instead_of_busy(http, ctx):
    """O sinal caiu e o app reenviou o mesmo comando com a medida já rodando: tem de receber o
    MESMO trabalho, e não "ocupado" por causa da própria medida."""
    headers = pair(http, ctx)
    first = http.post("/api/v1/observe/polar", json={"id": "c-1"}, headers=headers).json()
    ctx.hub.update(b"", dict(IDLE, state="SOLVING", job=first["job"]))
    again = http.post("/api/v1/observe/polar", json={"id": "c-1"}, headers=headers)
    assert again.status_code == 200 and again.json()["job"] == first["job"]
    assert ctx.commands == ["start:polar"], "não mede duas vezes"
    assert code(http.post("/api/v1/observe/polar", json={"id": "c-2"}, headers=headers)) == (409, "busy")


def test_polar_and_planetary_only_enter_by_their_own_routes(http, ctx):
    """`/observe/run` aceita modos pelo nome; estes dois ficam de fora: são as rotas próprias
    que conferem a montagem e o corpo pedido."""
    headers = pair(http, ctx)
    for mode in ("polar", "planetary"):
        r = http.post("/api/v1/observe/run", json={"id": f"c-{mode}", "mode": mode, "target": "sun"},
                      headers=headers)
        assert code(r)[0] == 400, mode
    assert ctx.commands == []
    assert http.post("/api/v1/observe/run", json={"id": "c-ok", "mode": "stack"}, headers=headers).status_code == 200
    info = http.get("/api/v1/info").json()["capabilities"]["modes"]
    assert "planetary" in info and "polar" in info, "o que o aparelho sabe fazer continua dito"


def test_a_viewer_cannot_measure_adjust_or_capture(http, ctx):
    viewer = pair(http, ctx, "Visita", "viewer")
    for path, body in (("/api/v1/observe/polar", {"id": "c-1"}),
                       ("/api/v1/mount/polar/adjust", {"alt_arcmin": 1, "az_arcmin": 1}),
                       ("/api/v1/observe/planetary", {"id": "c-2", "body": "moon"})):
        assert code(http.post(path, json=body, headers=viewer)) == (403, "forbidden"), path
    assert ctx.commands == []


def test_turning_the_simulated_screws_is_audited(http, ctx):
    headers = pair(http, ctx)
    http.post("/api/v1/mount/polar/adjust", json={"alt_arcmin": -38.0, "az_arcmin": 52.5}, headers=headers)
    entry = [e for e in ctx.audit.recent(10) if e["action"] == "polar_adjust"]
    assert len(entry) == 1 and entry[0]["detail"] == {"alt_arcmin": -38.0, "az_arcmin": 52.5}


@pytest.mark.parametrize("body", [
    {"ssid": "Casa", "psk": "curta"},                  # senha de WiFi tem de 8 a 63 caracteres
    {"ssid": "   ", "psk": "senha-de-casa"},           # nome em branco
    {"ssid": "ã" * 17, "psk": "senha-de-casa"},        # 34 bytes: passa do limite do WiFi (32)
    {"ssid": "Casa", "psk": "x" * 64},
    {"psk": "senha-de-casa"}])
def test_join_refuses_names_and_passwords_no_wifi_would_take(http, ctx, body):
    ctx.network = SimNetwork()
    assert code(http.post("/api/v1/network/join", json=body, headers=pair(http, ctx)))[0] == 400
    assert ctx.network.status()["switching"] is False


def test_an_accepted_request_with_nothing_to_switch_does_not_carry_an_old_error():
    """Entrou com a senha errada (erro registrado) e depois pediu o modo em que já está: o pedido
    é aceito sem nada a trocar, e o erro antigo não pode ser lido como resultado dele."""
    clock = Clock()
    net = SimNetwork(clock=clock)
    net.join("Casa", "senha-errada")
    clock.t += 10
    assert net.status()["last_error"] == "wrong_password"
    assert net.set_mode("field") == {"accepted": True, "reconnect_s": 0}
    assert net.status()["last_error"] is None


def _sim_network():
    """(adapter, deixar o tempo passar, rede boa, senha boa)."""
    clock = Clock()
    net = SimNetwork(switch_s=3.0, clock=clock)

    def wait(seconds):
        clock.t += seconds
    return net, wait, "Casa", "senha-de-casa"


def _sim_updater():
    """(adapter, deixar o tempo passar, fazer a próxima instalação falhar)."""
    clock = Clock()
    up = SimUpdater(current="0.1.0", newer="0.2.0", clock=clock)

    def wait(seconds):
        clock.t += seconds

    def fail_next():
        up.fail_next = True
    return up, wait, fail_next


# O adapter de verdade (NetworkManager na Jetson; o que baixa e instala) entra NESTAS listas no
# dia em que existir: o contrato abaixo é o que o app espera de qualquer um.
NETWORK_ADAPTERS = [_sim_network]
UPDATER_ADAPTERS = [_sim_updater]


@pytest.mark.parametrize("make", NETWORK_ADAPTERS)
def test_network_adapter_contract(make):
    from src.api.network import NetworkControl
    net, wait, ssid, psk = make()
    assert isinstance(net, NetworkControl)
    before = net.status(owner=True)
    assert {"enabled", "mode", "wifi", "hotspot", "known", "last_error", "switching"} <= set(before)
    assert before["enabled"] is True and before["mode"] in ("home", "field")
    assert {"ssid", "active", "address", "psk"} <= set(before["hotspot"])
    assert "psk" not in net.status()["hotspot"], "a senha do WiFi próprio só vai para o dono"
    assert all({"ssid", "signal", "secure", "known"} <= set(row) for row in net.scan())

    # 1) responde ANTES de trocar, e diz quanto esperar
    answer = net.join(ssid, psk)
    assert answer["accepted"] is True and answer["reconnect_s"] > 0
    during = net.status()
    assert during["switching"] is True and during["mode"] == before["mode"], "ainda não trocou"
    wait(answer["reconnect_s"])
    after = net.status()
    assert (after["mode"], after["wifi"]["ssid"], after["switching"], after["last_error"]) == \
        ("home", ssid, False, None)
    assert ssid in after["known"]

    # 2) se a rede nova não der certo, VOLTA para onde estava e conta o motivo
    back = net.set_mode("field")
    wait(back["reconnect_s"])
    assert net.status()["mode"] == "field"
    net.forget(ssid)
    wrong = net.join(ssid, psk + "-errada")
    wait(wrong["reconnect_s"])
    failed = net.status()
    assert (failed["mode"], failed["switching"], failed["last_error"]) == ("field", False, "wrong_password")

    # 3) um pedido aceito limpa o erro anterior, e `switching` volta a valer
    again = net.join(ssid, psk)
    assert net.status()["last_error"] is None and net.status()["switching"] is True
    wait(again["reconnect_s"])
    assert net.status()["mode"] == "home"
    with pytest.raises(NetworkError):
        net.set_mode("praia")


@pytest.mark.parametrize("make", UPDATER_ADAPTERS)
def test_updater_adapter_contract(make):
    from src.api.updates import STATES, Updater
    up, wait, fail_next = make()
    assert isinstance(up, Updater)
    start = up.status()
    assert {"enabled", "current", "available", "state", "progress", "error"} <= set(start)
    assert start["state"] in STATES and start["enabled"] is True
    with pytest.raises(UpdateError):
        up.install()                                   # sem versão achada não há o que instalar
    up.check()
    wait(5)
    found = up.status()
    assert found["available"]["version"] != found["current"] and found["state"] == "idle"

    # uma instalação que falha deixa a versão ANTERIOR valendo, e diz por quê
    fail_next()
    up.install()
    with pytest.raises(UpdateError):
        up.check()                                     # uma de cada vez
    wait(60)
    failed = up.status()
    assert (failed["state"], failed["current"]) == ("failed", start["current"]) and failed["error"]
    assert failed["available"] is not None, "dá para tentar de novo"

    up.install()
    wait(60)
    done = up.status()
    assert (done["state"], done["current"], done["error"]) == ("idle", found["available"]["version"], None)
