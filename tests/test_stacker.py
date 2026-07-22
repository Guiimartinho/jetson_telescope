import numpy as np

from src.backend import asnumpy
from src.gpu.stacker import LiveStacker


def test_single_frame_is_itself():
    s = LiveStacker()
    s.add(np.full((4, 4), 7.0, np.float32), 1.0)
    np.testing.assert_allclose(asnumpy(s.result()), 7.0, rtol=1e-5)


def test_equal_weight_is_mean():
    s = LiveStacker()
    s.add(np.full((3, 3), 2.0, np.float32), 1.0)
    s.add(np.full((3, 3), 4.0, np.float32), 1.0)
    np.testing.assert_allclose(asnumpy(s.result()), 3.0)


def test_weighted_average():
    s = LiveStacker()
    s.add(np.full((2, 2), 10.0, np.float32), 3.0)
    s.add(np.full((2, 2), 0.0, np.float32), 1.0)
    np.testing.assert_allclose(asnumpy(s.result()), 7.5)   # (3*10+1*0)/4


def test_mask_zeroes_uncovered_pixels():
    s = LiveStacker()
    mask = np.array([[1, 0], [1, 0]], np.float32)
    s.add(np.full((2, 2), 5.0, np.float32), 1.0, mask)
    r = asnumpy(s.result())
    assert r[0, 0] == 5.0 and r[1, 0] == 5.0
    assert r[0, 1] == 0.0 and r[1, 1] == 0.0   # peso 0 -> 0


def test_color_frames_supported():
    s = LiveStacker()
    f = np.zeros((2, 2, 3), np.float32)
    f[..., 0], f[..., 1], f[..., 2] = 1, 2, 3
    s.add(f, 1.0)
    r = asnumpy(s.result())
    assert r.shape == (2, 2, 3)
    np.testing.assert_allclose(r[0, 0], [1, 2, 3])


def test_reset_clears_state():
    s = LiveStacker()
    s.add(np.ones((2, 2), np.float32), 1.0)
    s.reset()
    assert s.n == 0 and s.result() is None
