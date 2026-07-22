import numpy as np
import scipy.ndimage as ndi

from src.planetary.align import estimate_shift, align_to, shift_image


def _planet(n=128, seed=0):
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n]
    r = np.hypot(yy - n / 2, xx - n / 2)
    disk = (r <= 40).astype(np.float32)
    img = disk * 150.0 + disk * rng.normal(0, 8, (n, n)).astype(np.float32)
    return ndi.gaussian_filter(img, 1.0).astype(np.float32)


def test_estimate_shift_recovers_translation():
    ref = _planet()
    dy, dx = 3.0, -5.0
    frame = ndi.shift(ref, (dy, dx), order=1, mode="constant")
    ey, ex = estimate_shift(ref, frame)
    assert abs(ey - dy) < 0.6 and abs(ex - dx) < 0.6


def test_estimate_shift_subpixel():
    ref = _planet(seed=2)
    dy, dx = 2.4, 1.7
    frame = ndi.shift(ref, (dy, dx), order=1, mode="constant")
    ey, ex = estimate_shift(ref, frame)
    assert abs(ey - dy) < 0.6 and abs(ex - dx) < 0.6


def test_align_to_reduces_error():
    ref = _planet(seed=1)
    frame = ndi.shift(ref, (4.0, -3.0), order=1, mode="constant")
    before = np.mean((frame - ref) ** 2)
    aligned, mask, sh = align_to(frame, ref)
    m = mask > 0.5
    after = np.mean((aligned[m] - ref[m]) ** 2)
    assert after < before * 0.3


def test_shift_image_mask_marks_borders():
    img = np.ones((40, 50), np.float32)
    out, mask = shift_image(img, 5.0, 0.0)
    assert out.shape == (40, 50) and mask.shape == (40, 50)
    assert mask[:5, :].max() == 0.0        # borda que entrou vazia
    assert mask[10, 10] == 1.0             # miolo é válido
