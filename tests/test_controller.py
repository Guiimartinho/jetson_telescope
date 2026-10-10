"""Painel de controle — despacho de modos e parada."""
import time

from src.core.config import SessionConfig
from src.core.controller import Controller
from src.core.state import State


def test_controller_builds_world():
    c = Controller(SessionConfig(width=200, height=150, web=False))
    assert "M31" in c.sky.targets
    assert c.session.mount is c.mount and c.session.filterwheel is not None


def test_hub_has_state_and_real_backend_before_any_mode_runs():
    """Regressão: parado, o hub ficava vazio e as UIs mostravam "CPU" por falta do campo,
    mesmo com o pipeline em GPU. O estado inicial (IDLE + backend real) sai na criação."""
    from src.backend import backend_name
    from src.server.webview import FrameHub
    hub = FrameHub()
    Controller(SessionConfig(width=200, height=150, web=False), hub=hub)
    _, stats = hub.get()
    assert stats["state"] == "IDLE"
    assert stats["backend"] == backend_name()


def test_controller_stop_command():
    c = Controller(SessionConfig(width=200, height=150, web=False))
    c.session.stop = False
    c.dispatch("stop")
    assert c.session.stop is True


def test_controller_starts_and_stops_a_mode(tmp_path):
    c = Controller(SessionConfig(width=300, height=220, web=False, out_dir=str(tmp_path)))
    c.dispatch("start:autofind:M31")                 # inicia modo numa thread
    time.sleep(0.6)
    assert c._worker is not None and c._worker.is_alive()
    c.dispatch("stop")                               # pede parada pela "UI"
    c._worker.join(timeout=15)
    assert not c._worker.is_alive()                  # encerrou de fato


def test_reset_state_recovers_from_terminal_stopped():
    """Regressão: STOPPED é terminal; reset_state permite iniciar um novo modo."""
    from src.core.orchestrator import Session
    from src.core.state import State
    s = Session(SessionConfig(width=100, height=100, web=False))
    s._set_state(State.STACKING)
    s._set_state(State.STOPPED)                      # terminal
    s.reset_state()
    assert s.sm.state is State.IDLE
    s._set_state(State.TRACKING)                     # não levanta após reset
    assert s.sm.state is State.TRACKING


def test_hub_stats_reflect_stopped_after_stop(tmp_path):
    """Regressao: o painel (via hub) mostrava STACKING pra sempre porque _set_state(STOPPED)
    nao empurrava o estado pro hub. /stats le do hub, entao ficava preso no ultimo frame."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=300, height=220, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:stack:M31")
    time.sleep(0.8)
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=15)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"          # o hub reflete a parada, nao STACKING


def test_controller_goto_mode_centers(tmp_path):
    """Modo GOTO celeste (T16): roda o laço RA/DEC e centraliza (erro pequeno em arcmin)."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=200, height=150, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:goto:M42")
    if c._worker:
        c._worker.join(timeout=30)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"
    assert stats.get("err_unit") == "arcmin"
    assert stats.get("error_px", 99) <= 1.0            # centralizou (<1 arcmin)


def test_controller_realdata_mode_stacks_real_photo(tmp_path):
    """Modo 'Dados reais': empilha a foto REAL de M67 (o dado real, visível no painel)."""
    import os
    from src.server.webview import FrameHub
    fixture = os.path.join(os.path.dirname(__file__), "data", "real_starfield_m67.fits")
    if not os.path.exists(fixture):
        import pytest
        pytest.skip("fixture de foto real ausente")
    hub = FrameHub()
    c = Controller(SessionConfig(width=400, height=300, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:realdata")
    time.sleep(1.5)
    _, stats = hub.get()
    assert stats.get("target") == "M67 (foto real)"
    assert stats.get("state") in ("STACKING", "STOPPED")
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=15)
    _, stats = hub.get()
    assert stats.get("state") == "STOPPED"
    assert stats.get("accepted", 0) >= 1                 # aceitou frames reais (não rejeitou tudo)


def test_mode_completing_naturally_leaves_panel_ready(tmp_path):
    """Regressao: um modo que TERMINA SOZINHO (nao pelo Parar) nao pode deixar o painel preso
    num estado 'rodando' (ex.: STACKING) — senao os botoes parecem mortos. Deve ir p/ IDLE/STOPPED."""
    from src.server.webview import FrameHub
    hub = FrameHub()
    c = Controller(SessionConfig(width=300, height=220, web=True, out_dir=str(tmp_path)), hub=hub)
    c.dispatch("start:goto:M31")                      # goto termina sozinho (converge)
    if c._worker:
        c._worker.join(timeout=30)
    _, stats = hub.get()
    assert stats.get("state") in ("IDLE", "STOPPED")  # painel pronto, nao congelado
    # e um novo modo inicia normalmente depois
    c.dispatch("start:tracking")
    ok = False
    for _ in range(40):
        time.sleep(0.2)
        if c.session.sm.state.name == "TRACKING":
            ok = True
            break
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=10)
    assert ok


def test_controller_switches_between_modes(tmp_path):
    """Regressão: trocar de modo (após um parar) deve iniciar o próximo, não travar em STOPPED."""
    c = Controller(SessionConfig(width=300, height=220, web=False, out_dir=str(tmp_path)))
    c.dispatch("start:scheduler")
    time.sleep(0.8)
    c.dispatch("start:tracking")
    ok = False
    for _ in range(40):
        time.sleep(0.2)
        if c.session.sm.state.name == "TRACKING":
            ok = True
            break
    c.dispatch("stop")
    if c._worker:
        c._worker.join(timeout=10)
    assert ok


# ---- o que a API do app precisa do Controller ------------------------------

def _hub_controller(tmp_path, width=200, height=150):
    from src.server.webview import FrameHub
    hub = FrameHub()
    return hub, Controller(SessionConfig(width=width, height=height, web=True, out_dir=str(tmp_path)), hub=hub)


def _wait(hub, cond, seconds=40.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        st = hub.get()[1]
        if cond(st):
            return st
        time.sleep(0.01)
    raise AssertionError(f"não aconteceu a tempo; último estado: {hub.get()[1]}")


def test_command_tag_says_which_command_the_state_belongs_to(tmp_path):
    """A API devolve um trabalho por comando; para acompanhá-lo, o estado publicado tem de
    dizer de QUAL comando ele é. Comando sem etiqueta (as páginas antigas) limpa a etiqueta."""
    hub, c = _hub_controller(tmp_path)
    assert hub.get()[1].get("job") is None
    c.dispatch("start:goto:M42", tag="j-7")
    c._worker.join(timeout=30)
    stats = hub.get()[1]
    assert (stats["job"], stats["state"], stats["outcome"]) == ("j-7", "STOPPED", "ok")
    c.dispatch("start:goto:M31")
    c._worker.join(timeout=30)
    assert hub.get()[1]["job"] is None


def test_tag_travels_through_the_command_queue(tmp_path):
    _, c = _hub_controller(tmp_path)
    seen = []
    c.dispatch = lambda cmd, tag=None: seen.append((cmd, tag))
    c.submit("stop")
    c.submit("start:stack", tag="j-2")
    c._drain()
    assert seen == [("stop", None), ("start:stack", "j-2")]


def test_goto_that_does_not_converge_says_so(tmp_path, monkeypatch):
    """Sem isto, um goto que falhou e um que deu certo terminam iguais: STOPPED."""
    from src.core import controller as mod
    monkeypatch.setattr(mod, "close_loop_goto", lambda *a, **k: (False, 12.0, 8))
    hub, c = _hub_controller(tmp_path)
    c.dispatch("start:goto:M42", tag="j-1")
    c._worker.join(timeout=30)
    assert hub.get()[1]["outcome"] == "not_converged"


def test_mode_that_raises_reports_an_error_outcome(tmp_path, monkeypatch):
    hub, c = _hub_controller(tmp_path)
    monkeypatch.setattr(c, "_run_goto", lambda name: (_ for _ in ()).throw(RuntimeError("quebrou")))
    c.dispatch("start:goto:M42", tag="j-1")
    c._worker.join(timeout=30)
    stats = hub.get()[1]
    assert stats["outcome"] == "error" and stats["state"] in ("IDLE", "STOPPED")


def test_goto_accepts_coordinates(tmp_path):
    hub, c = _hub_controller(tmp_path)
    assert c._radec_for("@83.82,-5.39") == (83.82, -5.39)
    c.dispatch("start:goto:@83.82,-5.39")
    c._worker.join(timeout=30)
    stats = hub.get()[1]
    assert stats["state"] == "STOPPED" and stats["error_px"] <= 1.0


def test_every_mode_ends_by_saying_how_it_ended(tmp_path):
    """Parado pelo usuário -> "stopped"; e o aviso vem com a etiqueta do comando."""
    hub, c = _hub_controller(tmp_path)
    c.dispatch("start:stack", tag="j-3")
    time.sleep(0.6)
    assert hub.get()[1]["outcome"] == "", "enquanto roda, ainda não terminou"
    c.dispatch("stop")
    c._worker.join(timeout=15)
    stats = hub.get()[1]
    assert (stats["job"], stats["outcome"]) == ("j-3", "stopped")


def test_observe_mode_points_then_stacks_until_stopped(tmp_path):
    """A "noite rápida" do app: um comando só aponta, centraliza e empilha — na Jetson, sem
    o celular orquestrar. Só termina quando alguém para; e o apontamento que falha não empilha."""
    hub, c = _hub_controller(tmp_path)
    seen = []
    c.dispatch("start:observe:M42", tag="j-9")
    end = time.monotonic() + 40
    while time.monotonic() < end:
        st = hub.get()[1]
        if not seen or seen[-1] != st["state"]:
            seen.append(st["state"])
        if st["state"] == "STACKING" and st["accepted"] >= 2:
            break
        time.sleep(0.05)
    st = hub.get()[1]
    assert st["state"] == "STACKING" and st["outcome"] == "", f"devia estar empilhando: {seen}"
    assert seen.index("SOLVING") < seen.index("STACKING"), "empilha só depois de reconhecer o céu"
    c.dispatch("stop")
    c._worker.join(timeout=15)
    st = hub.get()[1]
    assert (st["job"], st["outcome"]) == ("j-9", "stopped")


def test_observe_mode_does_not_stack_when_pointing_fails(tmp_path, monkeypatch):
    from src.core import controller as mod
    monkeypatch.setattr(mod, "close_loop_goto", lambda *a, **k: (False, 12.0, 8))
    hub, c = _hub_controller(tmp_path)
    c.dispatch("start:observe:M42", tag="j-1")
    c._worker.join(timeout=30)
    st = hub.get()[1]
    assert (st["outcome"], st["state"], st["accepted"]) == ("not_converged", "STOPPED", 0)


# ---- fase 3 do app: prévia, foco, montagem à mão e plano ---------------------

def test_preview_mode_shows_the_live_camera_without_stacking(tmp_path):
    """Enquadrar e focar à mão pedem a câmera ao vivo SEM empilhar: quadros novos chegando,
    com a nitidez medida, até alguém parar."""
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.dispatch("start:preview", tag="j-1")
    st = _wait(hub, lambda s: s["state"] == "PREVIEW" and s.get("fwhm", 0) > 0)
    first = hub.get()[0]
    assert first, "tem de haver imagem"
    assert st["accepted"] == 0, "prévia não empilha"
    _wait(hub, lambda s: hub.get()[0] is not first)          # chegou um quadro novo
    c.dispatch("stop")
    c._worker.join(timeout=15)
    st = hub.get()[1]
    assert (st["state"], st["outcome"], st["accepted"]) == ("STOPPED", "stopped", 0)


def test_focus_mode_finds_the_critical_focus_and_publishes_the_curve(tmp_path):
    """O autofoco como trabalho do app: varre, acha o foco e conta a curva (posição, nitidez)
    para a tela desenhar. O simulador tem o foco ideal em 6300, escondido do algoritmo."""
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.session.pace = False
    c.dispatch("start:focus", tag="j-2")
    c._worker.join(timeout=90)
    st = hub.get()[1]
    assert (st["job"], st["outcome"]) == ("j-2", "ok")
    assert st["state"] in ("IDLE", "STOPPED")
    assert abs(st["focus_pos"] - 6300) < 400 and st["focus_best"] == st["focus_pos"]
    curve = st["focus_curve"]
    assert len(curve) >= 5 and all(len(p) == 2 for p in curve)
    assert min(f for _, f in curve if f) < 5.0, "perto do foco a estrela fica pequena"


def test_focus_that_finds_no_stars_fails_instead_of_pretending(tmp_path, monkeypatch):
    from src.control import autofocus as af
    monkeypatch.setattr(af, "detect_stars", lambda frame, q: ([], []))
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.session.pace = False
    c.dispatch("start:focus", tag="j-3")
    c._worker.join(timeout=90)
    st = hub.get()[1]
    assert st["outcome"] == "focus_failed" and st["focus_best"] is None
    assert all(f is None for _, f in st["focus_curve"]), "ponto sem estrela não vira número"


def test_manual_focus_commands_move_the_focuser_and_respect_the_limits(tmp_path):
    hub, c = _hub_controller(tmp_path)
    start = c.focuser.position()
    assert hub.get()[1]["focus_range"] == [c.focuser.lo, c.focuser.hi]
    c.dispatch("focus:move:-100")
    assert c.focuser.position() == start - 100
    assert hub.get()[1]["focus_pos"] == start - 100
    assert hub.get()[0], "mexer no foco parado mostra um quadro novo"
    c.dispatch("focus:goto:999999")
    assert c.focuser.position() == c.focuser.hi, "fim de curso"
    c.dispatch("focus:move:abc")                       # comando torto não derruba nada
    c.dispatch("focus:voa:10")
    assert c.focuser.position() == c.focuser.hi


def test_jog_moves_the_mount_only_while_the_command_is_renewed(tmp_path):
    """Homem-morto: o movimento manual tem prazo. Se o celular some (sinal caiu com o dedo no
    botão), a montagem para sozinha em vez de seguir andando."""
    hub, c = _hub_controller(tmp_path)
    x0 = c.mount.cx
    c.dispatch("mount:jog:E:3:300")
    t = time.monotonic()
    assert c._jog_step(t + 0.1) is True
    assert c.mount.cx > x0 + 20 and hub.get()[1]["mount_ctl"]["jog"] == "E"
    x1 = c.mount.cx
    assert c._jog_step(t + 0.5) is False, "passou do prazo: para"
    assert hub.get()[1]["mount_ctl"]["jog"] is None
    assert c._jog_step(t + 0.9) is False
    assert abs(c.mount.cx - x1) < 1.0, "parada, só a deriva do rastreio mexe"


def test_jog_stays_inside_the_simulated_sky(tmp_path):
    _, c = _hub_controller(tmp_path)
    for _ in range(200):
        c.dispatch("mount:jog:W:3:2000")
        c._jog_step(time.monotonic() + 0.25)
    assert c.mount.cx >= c.cfg.width / 2.0


def test_parked_mount_does_not_jog_and_stop_halts_manual_motion(tmp_path):
    hub, c = _hub_controller(tmp_path)
    c.dispatch("mount:park")
    assert hub.get()[1]["mount_ctl"] == {"parked": True, "tracking": False, "jog": None}
    c.dispatch("mount:jog:N:2:500")
    assert c._jog is None, "estacionada não anda"
    c.dispatch("mount:tracking:on")
    assert hub.get()[1]["mount_ctl"]["tracking"] is False, "estacionada não rastreia"
    c.dispatch("mount:unpark")
    c.dispatch("mount:tracking:off")
    assert hub.get()[1]["mount_ctl"] == {"parked": False, "tracking": False, "jog": None}
    c.dispatch("mount:tracking:on")
    c.dispatch("mount:jog:N:2:500")
    assert c._jog is not None
    c.dispatch("stop")
    assert c._jog is None, "PARAR vale para o movimento manual também"
    for torto in ("mount:jog:X:2", "mount:jog:N:9", "mount:jog:N:dois", "mount:dance", "mount:"):
        c.dispatch(torto)
    assert c._jog is None


def test_pointing_takes_the_mount_out_of_park(tmp_path):
    hub, c = _hub_controller(tmp_path)
    c.dispatch("mount:park")
    c.dispatch("start:goto:M42", tag="j-1")
    c._worker.join(timeout=30)
    assert hub.get()[1]["mount_ctl"] == {"parked": False, "tracking": True, "jog": None}


def test_each_target_gets_its_own_simulated_field(tmp_path):
    import pytest
    from src.core import catalog as cat
    _, c = _hub_controller(tmp_path)
    assert c._xy_for("M31") == c.sky.targets["M31"]
    assert c._xy_for("alvo que não existe") == c.sky.targets["M31"]
    if not cat.HAS_ONGC:
        pytest.skip("pyongc não instalado (OpenNGC)")
    m8, m51 = c._xy_for("M8"), c._xy_for("M51")
    assert m8 != m51 and m8 != c.sky.targets["M31"]
    for x, y in (m8, m51):
        assert 0 < x < c.sky.world_w and 0 < y < c.sky.world_h


def _plan_statuses(st):
    return [p["status"] for p in st.get("plan") or []]


def test_plan_mode_runs_the_queue_in_order_and_reports_each_item(tmp_path):
    """A noite autônoma do app: a fila na ordem do dono, com o que aconteceu em cada alvo."""
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.session.pace = False
    c.plan_provider = lambda: [{"id": "p1", "target": "M42", "frames": 3, "type": "nebula"},
                               {"id": "p2", "target": "M31", "frames": 3, "type": "galaxy"}]
    seen = []
    c.dispatch("start:plan", tag="j-5")
    end = time.monotonic() + 120
    while c._worker.is_alive() and time.monotonic() < end:
        snap = _plan_statuses(hub.get()[1])
        if snap and (not seen or seen[-1] != snap):
            seen.append(snap)
        time.sleep(0.005)
    c._worker.join(timeout=5)
    st = hub.get()[1]
    assert st["outcome"] == "ok" and (st["queue_done"], st["queue_total"]) == (2, 2)
    assert _plan_statuses(st) == ["done", "done"]
    assert [p["id"] for p in st["plan"]] == ["p1", "p2"]
    assert all(p["accepted"] >= 1 for p in st["plan"])
    assert ["running", "pending"] in seen and ["done", "running"] in seen, seen
    assert st["state"] in ("IDLE", "STOPPED")


def test_skip_moves_to_the_next_item_and_stop_ends_the_night(tmp_path):
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.session.pace = False
    c.plan_provider = lambda: [{"id": "p1", "target": "M42", "frames": 0},
                               {"id": "p2", "target": "M31", "frames": 0},
                               {"id": "p3", "target": "M45", "frames": 0}]
    c.dispatch("start:plan", tag="j-6")
    _wait(hub, lambda s: s["state"] == "STACKING" and s["accepted"] >= 1
          and _plan_statuses(s)[:1] == ["running"])
    c.dispatch("skip")
    _wait(hub, lambda s: _plan_statuses(s)[:2] == ["skipped", "running"]
          and s["state"] == "STACKING" and s["accepted"] >= 1)
    c.dispatch("stop")
    c._worker.join(timeout=15)
    st = hub.get()[1]
    assert _plan_statuses(st) == ["skipped", "stopped", "pending"]
    assert (st["outcome"], st["state"]) == ("stopped", "STOPPED")
    assert st["plan"][0]["reason"] == "user"


def test_a_target_that_cannot_be_found_does_not_end_the_night(tmp_path, monkeypatch):
    hub, c = _hub_controller(tmp_path, 640, 480)
    c.session.pace = False
    real = c.session.auto_find
    calls = []

    def flaky(xy, **kw):
        calls.append(xy)
        return False if len(calls) == 1 else real(xy, **kw)
    monkeypatch.setattr(c.session, "auto_find", flaky)
    c.plan_provider = lambda: [{"id": "p1", "target": "M42", "frames": 2},
                               {"id": "p2", "target": "M31", "frames": 2}]
    c.dispatch("start:plan", tag="j-7")
    c._worker.join(timeout=120)
    st = hub.get()[1]
    assert _plan_statuses(st) == ["failed", "done"] and st["plan"][0]["reason"] == "not_found"
    assert st["outcome"] == "ok" and st["queue_done"] == 2


def test_polar_mode_measures_the_axis_error_in_three_points(tmp_path):
    """O alinhamento polar como trabalho: três campos reconhecidos girando a ascensão reta, e
    o erro do eixo separado em altitude e azimute. A montagem de mentira nasce desalinhada."""
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    c.latitude_provider = lambda: -23.55
    seen = []
    c.dispatch("start:polar", tag="j-p1")
    while c._worker.is_alive():
        step = (hub.get()[1].get("polar") or {}).get("step")
        if step is not None and (not seen or seen[-1] != step):
            seen.append(step)
        time.sleep(0.002)
    c._worker.join(timeout=5)
    st = hub.get()[1]
    polar = st["polar"]
    assert (st["job"], st["outcome"]) == ("j-p1", "ok")
    assert st["state"] == "STOPPED", "mediu: a montagem fica parada, como depois de um goto"
    assert c.session.sm.history[-2:] == [State.SOLVING, State.STOPPED], "sem transição inválida no fim"
    assert polar["measured"] and polar["step"] == 3 and not polar["aligned"]
    assert abs(polar["alt_arcmin"] - 38.0) < 2 and abs(polar["az_arcmin"] + 52.0) < 2
    assert polar["total_arcmin"] > 60 and polar["lat"] == -23.55
    assert seen == sorted(seen), f"os pontos avançam em ordem: {seen}"


def test_turning_the_screws_makes_the_last_measure_stale_and_the_next_one_better(tmp_path):
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    c.dispatch("start:polar")
    c._worker.join(timeout=30)
    first = hub.get()[1]["polar"]
    c.dispatch(f"polar:adjust:{-first['alt_arcmin']}:{-first['az_arcmin']}")
    assert hub.get()[1]["polar"]["stale"] is True, "mexeu nos parafusos: a medida não vale mais"
    c.dispatch("start:polar")
    c._worker.join(timeout=30)
    second = hub.get()[1]["polar"]
    assert second["stale"] is False and second["total_arcmin"] < first["total_arcmin"] / 4
    for torto in ("polar:adjust:1", "polar:adjust:x:y", "polar:adjust:nan:1", "polar:adjust:99999:0",
                  "polar:voa:1:2"):
        c.dispatch(torto)                              # comando torto não mexe em nada
    assert hub.get()[1]["polar"]["stale"] is False


def test_planetary_mode_keeps_only_the_sharpest_frames(tmp_path):
    """A captura planetária: muitos quadros curtos, só os mais nítidos empilhados. O andamento
    conta quantos chegaram e quantos estão sendo aproveitados."""
    import os
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    seen = []
    c.dispatch("start:planetary:jupiter|60|25", tag="j-v1")
    while c._worker.is_alive():
        st = hub.get()[1]
        if not seen or seen[-1] != st["state"]:
            seen.append(st["state"])
        time.sleep(0.002)
    c._worker.join(timeout=5)
    st = hub.get()[1]
    planet = st["planet"]
    assert (st["job"], st["outcome"]) == ("j-v1", "ok")
    assert (planet["body"], planet["frames"], planet["total"], planet["kept"], planet["done"]) == \
        ("jupiter", 60, 60, 15, True)
    assert (st["accepted"], st["rejected"]) == (15, 45)
    assert "CAPTURING" in seen and seen.index("CAPTURING") < seen.index("STACKING")
    assert hub.get()[0][:2] == b"\xff\xd8", "o resultado vai para a tela"
    assert os.path.exists(os.path.join(str(tmp_path), "planet_jupiter.png"))
    c.dispatch("start:stack", tag="j-v2")
    time.sleep(0.3)
    assert hub.get()[1]["planet"] is None, "outro modo não herda a captura planetária"
    c.dispatch("stop")
    c._worker.join(timeout=15)


def test_the_mount_is_not_moved_by_hand_in_the_middle_of_a_planetary_capture(tmp_path):
    """Durante a gravação a montagem é do modo: mover, estacionar ou ir para casa à mão no meio
    da captura estragaria os quadros. Os comandos manuais são ignorados até ela acabar."""
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    c.dispatch("start:planetary:jupiter|5000|10")
    assert _wait(hub, lambda st: st["state"] == "CAPTURING" and (st.get("planet") or {}).get("frames", 0) >= 5)
    where = (c.mount.cx, c.mount.cy)
    for command in ("mount:jog:E:3:800", "mount:park", "mount:home"):
        c.dispatch(command)
    assert c._jog is None and c._jog_step(time.monotonic()) is False, "nenhum movimento manual começou"
    assert (c.mount.cx, c.mount.cy) == where and c._mount_ctl["parked"] is False
    c.dispatch("stop")
    c._worker.join(timeout=15)
    c.dispatch("mount:park")                           # parado, volta a obedecer
    assert c._mount_ctl["parked"] is True


def test_planetary_capture_keeps_no_more_frames_than_the_memory_budget(tmp_path, monkeypatch):
    """O pedido vem em número de quadros, mas o que acaba a memória da Jetson são bytes: o
    teto em memória vale mais que o percentual pedido."""
    from src.core import controller as ctl
    from src.planetary.simulator import PlanetSimulator
    one = int(PlanetSimulator(size=240, radius=84, kind="jupiter", seed=7, color=True).frame()[0].nbytes)
    monkeypatch.setattr(ctl, "PLANET_BUDGET_BYTES", 4 * one + one // 2)      # cabem quatro quadros
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    c.dispatch("start:planetary:jupiter|60|50", tag="j-m1")                  # pediu 30
    c._worker.join(timeout=60)
    st = hub.get()[1]
    assert (st["outcome"], st["planet"]["kept"], st["planet"]["done"]) == ("ok", 4, True)
    assert (st["accepted"], st["rejected"]) == (4, 56)


def test_an_orphan_mode_that_crashes_does_not_fail_the_next_command(tmp_path):
    """Um modo que estoura DEPOIS de outro comando ter assumido não pode marcar o trabalho novo
    como falho: o desfecho só é escrito por quem ainda é dono do estado."""
    hub, c = _hub_controller(tmp_path)
    c.session.stats["job"] = "j-novo"                  # outro comando já é o dono
    c._run_mode("planetary", "jupiter|abc|15", tag="j-velho")     # argumento torto: estoura
    assert not c.session.stats.get("outcome"), "o erro do órfão não vaza para o trabalho seguinte"
    c.session.stats["job"] = "j-velho"
    c._run_mode("planetary", "jupiter|abc|15", tag="j-velho")
    assert c.session.stats["outcome"] == "error", "quando é o dono, o erro aparece"


def test_planetary_mode_points_first_when_given_coordinates_and_can_be_stopped(tmp_path):
    hub, c = _hub_controller(tmp_path)
    c.session.pace = False
    seen = []
    c.dispatch("start:planetary:saturn|4000|10|10.71|1.65", tag="j-v3")
    end = time.monotonic() + 40
    while time.monotonic() < end:
        st = hub.get()[1]
        if not seen or seen[-1] != st["state"]:
            seen.append(st["state"])
        if st["state"] == "CAPTURING" and (st.get("planet") or {}).get("frames", 0) >= 10:
            break
        time.sleep(0.002)
    assert seen.index("SOLVING") < seen.index("CAPTURING"), f"aponta antes de gravar: {seen}"
    assert hub.get()[1]["target"] == "saturn"
    c.dispatch("stop")
    c._worker.join(timeout=15)
    st = hub.get()[1]
    assert (st["outcome"], st["state"]) == ("stopped", "STOPPED")
    assert st["planet"]["done"] is False and st["planet"]["frames"] < 4000


def test_empty_plan_ends_at_once(tmp_path):
    hub, c = _hub_controller(tmp_path)
    c.dispatch("start:plan", tag="j-8")
    c._worker.join(timeout=15)
    st = hub.get()[1]
    assert (st["outcome"], st["plan"], st["queue_total"]) == ("ok", [], 0)
