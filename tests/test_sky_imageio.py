import numpy as np

from src.capture.sky import SkyModel, SkyCameraSource
from src.control.mount import SimMount
from src.gpu.quality import QualityConfig, detect_stars
from src.util.imageio import autostretch, robust_std, encode_jpeg


# ---- céu / câmera apontável ----------------------------------------------
def test_named_targets_exist():
    sky = SkyModel()
    for name in ("M31", "M42", "M45"):
        assert name in sky.targets


def test_camera_renders_detectable_stars():
    sky = SkyModel()
    mount = SimMount(cx=1560, cy=1350)             # M31
    src = SkyCameraSource(sky, mount, None, view_w=400, view_h=300, bad_frac=0.0)
    frame, meta = src.read()
    assert frame.shape == (300, 400)
    assert "pointing" in meta and len(meta["pointing"]) == 3
    assert len(detect_stars(frame, QualityConfig())[0]) >= 5


# ---- imageio --------------------------------------------------------------
def test_autostretch_is_uint8_in_range():
    img = np.random.default_rng(0).uniform(0, 1000, (40, 50)).astype(np.float32)
    out = autostretch(img)
    assert out.dtype == np.uint8 and out.shape == (40, 50)
    assert out.min() >= 0 and out.max() <= 255


def test_robust_std_of_constant_is_zero():
    assert robust_std(np.full((10, 10), 5.0, np.float32)) == 0.0


def test_encode_jpeg_mono_and_color():
    rng = np.random.default_rng(1)
    mono = rng.uniform(0, 1000, (30, 40)).astype(np.float32)
    color = rng.uniform(0, 1000, (20, 30, 3)).astype(np.float32)
    assert encode_jpeg(mono)[:2] == b"\xff\xd8"      # marcador SOI de JPEG
    assert encode_jpeg(color)[:2] == b"\xff\xd8"
