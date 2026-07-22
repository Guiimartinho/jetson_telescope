import numpy as np

from src.backend import asnumpy
from src.gpu.calibration import Calibrator, remove_hot_pixels


def test_remove_hot_pixels_kills_spikes_keeps_background():
    """Sem darks, hot pixels viram 'walking noise' ao registrar — este passo os remove."""
    img = np.full((60, 60), 100.0, np.float32)
    img[25, 25] = 60000.0                              # pixel quente isolado
    img[40, 12] = 55000.0
    out = remove_hot_pixels(img)
    assert out[25, 25] < 300 and out[40, 12] < 300     # spikes substituídos pela mediana local
    assert out[0, 0] == 100.0 and out[50, 50] == 100.0  # fundo intacto


# ---- unidades -------------------------------------------------------------
def test_no_masters_is_identity_for_positive_input():
    c = Calibrator()
    f = np.array([[1.0, 2.0], [3.0, 4.0]], np.float32)
    np.testing.assert_allclose(asnumpy(c.apply(f)), f)


def test_dark_subtracted_and_clipped_to_zero():
    dark = np.array([[1.0, 1.0], [10.0, 1.0]], np.float32)
    f = np.full((2, 2), 5.0, np.float32)
    r = asnumpy(Calibrator(master_dark=dark).apply(f))
    np.testing.assert_allclose(r, [[4.0, 4.0], [0.0, 4.0]])   # 5-10 -> clip 0


def test_flat_division_corrects_response():
    flat = np.array([[0.5, 1.0], [2.0, 1.0]], np.float32)     # já normalizado
    f = np.full((2, 2), 10.0, np.float32)
    r = asnumpy(Calibrator(master_flat=flat).apply(f))
    np.testing.assert_allclose(r, [[20.0, 10.0], [5.0, 10.0]])


def test_build_master_dark_is_average():
    d = Calibrator.build_master_dark(
        [np.full((2, 2), 2.0, np.float32), np.full((2, 2), 4.0, np.float32)])
    np.testing.assert_allclose(asnumpy(d), 3.0)


def test_master_flat_is_normalized_to_mean_one():
    flats = [np.full((4, 4), v, np.float32) for v in (100, 120, 110)]
    mf = Calibrator.build_master_flat(flats)
    assert abs(float(asnumpy(mf.mean())) - 1.0) < 1e-4


def test_from_frames_builds_all_masters():
    cal = Calibrator.from_frames(
        dark=[np.full((3, 3), 10.0, np.float32)] * 3,
        flat=[np.full((3, 3), 100.0, np.float32)] * 3,
        bias=[np.full((3, 3), 5.0, np.float32)] * 3)
    np.testing.assert_allclose(asnumpy(cal.dark), 10.0)
    np.testing.assert_allclose(asnumpy(cal.flat), 1.0, atol=1e-4)   # (100-5)/95 = 1


def test_mismatched_master_shape_is_ignored():
    c = Calibrator(master_dark=np.zeros((3, 3), np.float32))
    f = np.full((2, 2), 5.0, np.float32)                      # shape difere -> ignora
    np.testing.assert_allclose(asnumpy(c.apply(f)), 5.0)


# ---- end-to-end: remove vinheta + pixels quentes --------------------------
def _corner_center_ratio(img):
    h, w = img.shape
    s = 20
    center = np.median(img[h // 2 - s:h // 2 + s, w // 2 - s:w // 2 + s])
    corner = np.median(img[:s, :s])
    return corner / max(center, 1e-6)


def test_calibration_flattens_vignette_and_removes_hot_pixels():
    from src.capture.simulator import StarFieldSimulator, SimConfig
    cfg = SimConfig(width=200, height=160, n_stars=12, bad_frac=0.0,
                    bias=200.0, dark_current=6.0, hot_pixel_frac=0.004,
                    hot_pixel_level=9000.0, vignette=0.45, seed=1)
    sim = StarFieldSimulator(cfg)
    cal = Calibrator.from_frames(
        dark=[sim.dark_frame() for _ in range(8)],
        flat=[sim.flat_frame() for _ in range(8)],
        bias=[sim.bias_frame() for _ in range(8)])

    raw = asnumpy(sim.frame(0)[0])
    cald = asnumpy(cal.apply(raw))

    # Vinheta: bruto tem canto mais escuro; calibrado fica bem mais plano (~1).
    assert abs(_corner_center_ratio(cald) - 1.0) < abs(_corner_center_ratio(raw) - 1.0)
    assert abs(_corner_center_ratio(cald) - 1.0) < 0.12

    # Pixel quente: spike no bruto, removido após calibrar.
    hy, hx = map(int, np.argwhere(sim._hot > 0)[0])
    assert raw[hy, hx] > np.median(raw) + 1000
    local = np.median(cald[max(0, hy - 3):hy + 4, max(0, hx - 3):hx + 4])
    assert abs(cald[hy, hx] - local) < 200


def test_calibrated_pipeline_runs_at_custom_size(tmp_path):
    """Regressão do bug de dimensão: pipeline calibrado empilha em tamanho != default."""
    from src.capture.simulator import StarFieldSimulator, SimConfig
    from src.capture.source import SimulatorSource
    from src.core.config import SessionConfig
    from src.core.orchestrator import Session
    sc = SimConfig(width=320, height=240, n_stars=25, bad_frac=0.0,
                   bias=200.0, dark_current=6.0, hot_pixel_frac=0.002, vignette=0.4, seed=2)
    twin = StarFieldSimulator(sc)
    cal = Calibrator.from_frames(dark=[twin.dark_frame() for _ in range(6)],
                                 flat=[twin.flat_frame() for _ in range(6)],
                                 bias=[twin.bias_frame() for _ in range(6)])
    s = Session(SessionConfig(width=320, height=240, frames=6, web=False, out_dir=str(tmp_path)),
                source=SimulatorSource(sc), calibrator=cal)
    assert s.run_stack()["accepted"] >= 3
