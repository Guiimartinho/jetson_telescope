"""T1 — testes do mosaico multi-painel."""
import os

from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.mosaic import Mosaic, panel_centers, stitch_siril
from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.control.focuser import SimFocuser
from src.control.solver import SimSolver


def test_panel_centers_grid():
    p = panel_centers(1000, 500, 2, 2, 100)
    assert [n for n, _ in p] == ["R0C0", "R0C1", "R1C0", "R1C1"]
    xy = {c for _, c in p}
    assert (950.0, 450.0) in xy and (1050.0, 550.0) in xy   # centrado (1000,500), passo 100


def _mosaic_session(tmp_path, w=400, h=300):
    sky = SkyModel(n_stars=4000)                            # denso: cada painel tem estrelas
    mount = SimMount(cx=sky.targets["M31"][0], cy=sky.targets["M31"][1])
    foc = SimFocuser(position=6300, best=6300)
    src = SkyCameraSource(sky, mount, foc, view_w=w, view_h=h, bad_frac=0.0)
    cfg = SessionConfig(width=w, height=h, web=False, out_dir=str(tmp_path))
    return Session(cfg, source=src, mount=mount, focuser=foc, solver=SimSolver(mount)), sky


def test_mosaic_visits_all_panels_and_writes_fits(tmp_path):
    s, sky = _mosaic_session(tmp_path)
    out = Mosaic(s, do_autofocus=False).run(sky.targets["M31"], rows=2, cols=2,
                                            step_px=150, frames_per_panel=4, stitch=False)
    assert len(out["panels"]) == 4
    assert all(r["status"] == "ok" for r in out["panels"])
    assert len(out["fits"]) == 4
    for p in out["fits"]:
        assert os.path.exists(p)


def test_stitch_skips_gracefully_without_siril(tmp_path):
    assert stitch_siril([str(tmp_path / "a.fits")], str(tmp_path / "m.fits")) is None
