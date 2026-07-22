"""T2 — pós-processo (remoção de gradiente + wrapper GraXpert)."""
import numpy as np

from src.postproc.enhance import enhance, remove_gradient, graxpert_available
from tests._helpers import plant_star


def test_remove_gradient_reduces_gradient():
    h, w = 120, 160
    yy, xx = np.mgrid[0:h, 0:w]
    grad = (100 + 0.6 * xx + 0.4 * yy).astype(np.float32)     # gradiente linear forte

    def diag(img):
        return float(np.median(img[:15, :15])) - float(np.median(img[-15:, -15:]))
    assert abs(diag(remove_gradient(grad))) < abs(diag(grad)) * 0.3


def test_remove_gradient_preserves_stars():
    img = np.full((120, 160), 100.0, np.float32)
    plant_star(img, 80, 60, flux=15000, sigma=1.5)
    out = remove_gradient(img)
    y, x = np.unravel_index(int(np.argmax(out)), out.shape)
    assert abs(x - 80) <= 2 and abs(y - 60) <= 2


def test_enhance_shape_and_flag():
    img = np.random.default_rng(0).uniform(100, 500, (40, 50)).astype(np.float32)
    assert enhance(img).shape == (40, 50)
    assert isinstance(graxpert_available(), bool)
