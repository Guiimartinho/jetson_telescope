"""T3 — roda de filtros (port + sim + seleção por alvo)."""
import pytest

from src.control.filterwheel import (SimFilterWheel, IndiFilterWheel,
                                     filter_for_target, FilterWheel)
from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.scheduler import Scheduler, Target
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.solver import SimSolver


def test_sim_filterwheel_set_and_current():
    fw = SimFilterWheel()
    assert isinstance(fw, FilterWheel) and fw.current() == "VIS"
    fw.set("L-eXtreme")
    assert fw.current() == "L-eXtreme" and "L-Pro" in fw.names()


def test_sim_filterwheel_rejects_unknown():
    with pytest.raises(ValueError):
        SimFilterWheel().set("inexistente")


def test_filter_for_target_mapping():
    assert filter_for_target("galaxy") == "L-Pro"
    assert filter_for_target("nebula") == "L-eXtreme"
    assert filter_for_target("desconhecido") == "VIS"


def test_indi_filterwheel_fails_clearly_without_server():
    # implementado sobre o IndiClient (ver test_indi_adapters); sem servidor -> erro de conexão.
    with pytest.raises(OSError):
        IndiFilterWheel(host="127.0.0.1", port=1)


def test_scheduler_sets_filter_per_target(tmp_path):
    sky = SkyModel(n_stars=4000)
    mount = SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1])
    src = SkyCameraSource(sky, mount, None, view_w=300, view_h=220, bad_frac=0.0)
    fw = SimFilterWheel()
    s = Session(SessionConfig(width=300, height=220, web=False, out_dir=str(tmp_path)),
                source=src, mount=mount, solver=SimSolver(mount), filterwheel=fw)
    Scheduler(s, do_autofocus=False).run(
        [Target("M31", sky.targets["M31"], frames=3, filter="L-Pro")])
    assert fw.current() == "L-Pro"
