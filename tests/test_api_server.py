"""A API ligada às peças reais (`src/api/server.py`): estúdio, galeria, quadro ao vivo e o
Controller de verdade. Roda no backend que houver (NumPy no CI), sem rede e sem aparelho.
"""
import time

import cv2
import numpy as np
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi.testclient import TestClient                                    # noqa: E402

from src.api import server                                                   # noqa: E402
from src.api.app import create_app                                           # noqa: E402
from src.api.identity import b64u, b64u_decode                               # noqa: E402
from src.api.pairing import pairing_proof                                    # noqa: E402
from src.core import catalog as cat                                          # noqa: E402
from src.core.config import SessionConfig                                    # noqa: E402
from src.core.controller import Controller                                   # noqa: E402
from src.postproc.render import PRESETS, RenderParams                        # noqa: E402
from src.server.webview import FrameHub                                      # noqa: E402


# ---- estúdio ----------------------------------------------------------------
def test_render_controls_start_from_the_preset():
    p, full = server.render_params({"preset": "vivido", "stretch": 20, "remove_grad": True})
    assert (p.stretch, p.remove_grad, full) == (20.0, True, False)
    assert p.saturation == PRESETS["vivido"].saturation, "o que não veio fica como no preset"
    assert PRESETS["vivido"].stretch == 13.0, "o preset não é alterado por um pedido"
    assert server.render_params({})[0] == RenderParams()
    assert server.render_params({"full": True})[1] is True


@pytest.mark.parametrize("body", [
    {"preset": "inexistente"}, {"stretch": 31}, {"stretch": 0.5}, {"gamma": "1.2"},
    {"stretch": True}, {"remove_grad": 1}, {"full": "sim"}, {"bg_percentile": 30},
    {"__class__": 1}, {"stretch": float("nan")}])
def test_render_controls_are_checked_by_name_type_and_range(body):
    with pytest.raises(ValueError):
        server.render_params(body)


def test_presets_describe_every_control_the_app_can_show():
    d = server.render_presets()
    assert set(d["presets"]) == set(PRESETS)
    assert d["controls"]["stretch"] == {"min": 1.0, "max": 30.0, "step": 0.5, "default": 10.0}
    assert d["toggles"] == {"remove_grad": {"default": False}}
    for name, preset in d["presets"].items():
        for control, value in preset.items():
            if control in d["controls"]:
                lim = d["controls"][control]
                assert lim["min"] <= value <= lim["max"], f"preset {name}: {control} fora da faixa"
        server.render_params(dict(preset, preset=name))       # o próprio preset tem de ser aceito


# ---- galeria ----------------------------------------------------------------
def test_sessions_list_only_the_stacks_that_exist(tmp_path, monkeypatch):
    from src.server import studio
    real = tmp_path / "lagoa.fits"
    real.write_bytes(b"x")
    monkeypatch.setattr(studio, "CATALOG", {
        "lagoa": {"name": "M8 Lagoa", "kind": "nebulosa", "stack": str(real), "subs": 15,
                  "exp": "45 min", "cam": "ASI2600MC (dado real)"},
        "m51": {"name": "M51", "kind": "galaxia", "stack": str(tmp_path / "sumiu.fits"), "subs": 50,
                "exp": "~8 min", "cam": "Stellina"}})
    assert server.list_sessions() == [{
        "id": "lagoa", "target": "M8 Lagoa", "type": "nebula", "frames": 15, "integration_s": 2700,
        "integration_approx": False, "camera": "ASI2600MC (dado real)", "source": "reference",
        "has_fits": True}]


# ---- quadro ao vivo ---------------------------------------------------------
def _jpeg(w, h):
    rng = np.random.default_rng(1)
    ok, buf = cv2.imencode(".jpg", rng.integers(0, 255, (h, w, 3), dtype=np.uint8))
    return buf.tobytes()


def test_live_frame_is_shrunk_for_the_phone():
    shrink, big = server.Shrinker(), _jpeg(1600, 1200)
    small = shrink(big, 800)
    img = cv2.imdecode(np.frombuffer(small, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[:2] == (600, 800) and len(small) < len(big) / 2
    assert shrink(big, 800) is small, "o mesmo quadro não é recodificado a cada pedido"
    assert shrink(big, 4000) is big, "nunca amplia"
    assert shrink(b"isto nao e jpeg", 800) == b"isto nao e jpeg"


# ---- tudo junto, com o Controller de verdade --------------------------------
@pytest.fixture
def rig(tmp_path):
    hub = FrameHub()
    ctrl = Controller(SessionConfig(width=200, height=150, web=True, out_dir=str(tmp_path / "out")), hub=hub)
    ctrl.start()
    ctx = server.build_context(hub, ctrl.submit, identity_dir=tmp_path / "identity")
    with TestClient(create_app(ctx)) as http:
        ctx.pairing.open_window()
        nonce = http.post("/api/v1/pair/start", json={"client_name": "Pixel"}).json()["nonce"]
        proof = b64u(pairing_proof(ctx.identity.pairing_secret, b64u_decode(nonce),
                                   ctx.identity.fingerprint_bytes, "Pixel"))
        token = http.post("/api/v1/pair/finish", json={"client_name": "Pixel", "proof": proof}).json()["token"]
        http.headers["Authorization"] = f"Bearer {token}"
        yield http, ctx
        http.post("/api/v1/observe/stop", json={"id": "fim"})


def _job_until(http, states, timeout=40.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        job = http.get("/api/v1/state").json()["job"]
        if job and job["state"] in states:
            return job
        time.sleep(0.1)
    raise AssertionError(f"o trabalho não chegou a {states}: {job}")


def test_goto_job_runs_to_the_end_on_the_real_controller(rig):
    """O contrato entre o Controller e a API: etiqueta do comando, etapas e como terminou."""
    http, _ = rig
    target = "M42" if cat.HAS_ONGC else "M31"
    sent = http.post("/api/v1/observe/goto", json={"id": "c-1", "target": target}).json()
    job = _job_until(http, ("done", "failed", "stopped"))
    assert (job["job"], job["state"], job["target"]) == (sent["job"], "done", target)
    names = [s["name"] for s in job["steps"]]
    assert names[:2] == ["slew", "solve"] and all(s["state"] == "done" for s in job["steps"])
    state = http.get("/api/v1/state").json()
    assert state["pointing"]["unit"] == "arcmin" and state["pointing"]["error"] <= 1.0
    assert http.get("/api/v1/frame.jpg?max_side=64").content[:2] == b"\xff\xd8"


def test_stacking_runs_until_the_app_stops_it(rig):
    http, _ = rig
    sent = http.post("/api/v1/observe/stack", json={"id": "s-1"}).json()
    job = _job_until(http, ("running",))
    assert job["job"] == sent["job"] and job["steps"][-1] == {"name": "stack", "state": "running"}
    http.post("/api/v1/observe/stop", json={"id": "s-2"})
    job = _job_until(http, ("stopped", "done", "failed"))
    assert job["state"] == "stopped", "parado pelo app, não concluído"


def test_quick_night_points_and_then_stacks_on_the_real_controller(rig):
    http, _ = rig
    target = "M42" if cat.HAS_ONGC else "M31"
    sent = http.post("/api/v1/observe/target", json={"id": "o-1", "target": target}).json()
    end = time.monotonic() + 40
    while time.monotonic() < end:
        state = http.get("/api/v1/state").json()
        if state["state"] == "STACKING" and state["stack"]["accepted"] >= 1:
            break
        time.sleep(0.1)
    job = state["job"]
    assert (job["job"], job["kind"], job["state"]) == (sent["job"], "observe", "running")
    names = [s["name"] for s in job["steps"]]
    assert names[:2] == ["slew", "solve"] and names[-1] == "stack"
    assert all(s["state"] == "done" for s in job["steps"][:-1])
    http.post("/api/v1/observe/stop", json={"id": "o-2"})
    assert _job_until(http, ("stopped", "done", "failed"))["state"] == "stopped"


def test_context_serves_the_real_studio_presets_and_history(rig):
    http, ctx = rig
    assert set(http.get("/api/v1/render/presets").json()["presets"]) == set(PRESETS)
    assert len(http.get("/api/v1/histogram").json()["bins"]) == 40
    assert ctx.audit.path.name == "audit.jsonl" and ctx.audit.path.exists(), "auditoria vai ao disco"
