"""T12 — modo autônomo noturno (integração final)."""
import os

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.autonomous import AutonomousNight, Observation
from src.core.session_store import Telemetry
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.solver import SimSolver
from src.control.filterwheel import SimFilterWheel


def _night_session(tmp_path, w=320, h=240):
    sky = SkyModel(n_stars=8000)                         # denso: cada painel do mosaico tem estrelas
    mount = SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1])
    src = SkyCameraSource(sky, mount, None, view_w=w, view_h=h, bad_frac=0.0)
    cfg = SessionConfig(width=w, height=h, web=False, out_dir=str(tmp_path))
    s = Session(cfg, source=src, mount=mount, solver=SimSolver(mount),
                filterwheel=SimFilterWheel())
    return s, sky


def test_autonomous_night_runs_observations_with_auto_filters(tmp_path):
    s, sky = _night_session(tmp_path)
    tel = Telemetry(str(tmp_path / "night.jsonl"))
    obs = [
        Observation("M31", sky.targets["M31"], frames=4, kind="galaxy", priority=2),
        Observation("M42", sky.targets["M42"], frames=4, kind="nebula", priority=1),
    ]
    summary = AutonomousNight(s, telemetry=tel, do_autofocus=False).run(obs)

    assert summary["count"] == 2
    assert [r["name"] for r in summary["observations"]] == ["M31", "M42"]   # prioridade desc
    fmap = {r["name"]: r["filter"] for r in summary["observations"]}
    assert fmap["M31"] == "L-Pro" and fmap["M42"] == "L-eXtreme"            # filtro automático
    assert os.path.exists(str(tmp_path / "night_summary.json"))
    events = [e["event"] for e in tel.read()]
    assert "night_start" in events and "night_end" in events


def test_autonomous_night_mosaic_observation(tmp_path):
    s, sky = _night_session(tmp_path)
    summary = AutonomousNight(s, do_autofocus=False).run(
        [Observation("M45", sky.targets["M45"], frames=3, kind="galaxy", mosaic=(2, 2))])
    assert summary["observations"][0]["kind"] == "mosaic"
    assert summary["observations"][0]["panels"] == 4
