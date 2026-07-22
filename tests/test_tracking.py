"""Fase 4 (T8–T11) — detector, fluxo óptico e laço de rastreamento."""
from src.capture.satellite import SatelliteScene
from src.capture.sky import SkyModel
from src.control.mount import SimMount
from src.control.detector import BrightObjectDetector, YoloTensorRTDetector, Detector
from src.control.tracking import OpticalFlowTracker
from src.core.config import SessionConfig
from src.core.orchestrator import Session
from src.core.state import State


def _scene(w=400, h=300, vel=(3.0, 2.0), nudge_res=1.0):
    sky = SkyModel(n_stars=3000)
    mount = SimMount(cx=3000.0, cy=2200.0, nudge_residual_px=nudge_res, drift_px=0.0)
    scene = SatelliteScene(sky, mount, obj0=(3000.0, 2200.0), vel=vel, view_w=w, view_h=h)
    return scene, mount


# ---- T9 detector ----------------------------------------------------------
def test_bright_object_detector_finds_object():
    scene, _ = _scene()
    frame, meta = scene.read()
    det = BrightObjectDetector().detect(frame)
    assert det is not None and isinstance(BrightObjectDetector(), Detector)
    tx, ty = meta["obj_screen"]
    assert abs(det[0] - tx) < 3 and abs(det[1] - ty) < 3


def test_yolo_detector_falls_back_without_tensorrt():
    d = YoloTensorRTDetector()
    assert d.backend is None                          # sem TensorRT no PC de dev
    scene, _ = _scene()
    frame, _ = scene.read()
    assert d.detect(frame) is not None                # funciona via fallback CV


# ---- T8 fluxo óptico ------------------------------------------------------
def test_optical_flow_tracker_follows_object():
    scene, _ = _scene(vel=(2.0, 1.5))
    tr = OpticalFlowTracker()
    frame, meta = scene.read()
    tr.init(frame, meta["obj_screen"])
    ok = 0
    for _ in range(8):
        frame, meta = scene.read()
        p = tr.update(frame)
        if p is not None:
            tx, ty = meta["obj_screen"]
            if abs(p[0] - tx) < 6 and abs(p[1] - ty) < 6:
                ok += 1
    assert ok >= 6                                     # segue o objeto na maioria dos frames


# ---- T10/T11 laço de rastreamento ----------------------------------------
def test_track_loop_keeps_object_centered(tmp_path):
    scene, mount = _scene(vel=(4.0, 2.0), nudge_res=0.5)
    s = Session(SessionConfig(width=400, height=300, web=False, out_dir=str(tmp_path)),
                mount=mount)
    errs = s.track(scene, BrightObjectDetector(), frames=25)
    assert s.sm.state is State.TRACKING
    assert max(errs[5:]) < 10                          # após o lock, fica centralizado (< 10 px)
