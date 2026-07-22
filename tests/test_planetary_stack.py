import numpy as np
import pytest

from src.planetary.simulator import PlanetSimulator
from src.planetary.stack import lucky_stack


def _bg_std(x):
    return float(x[:12, :12].std())        # canto = fundo (fora do disco)


def test_lucky_stack_counts():
    sim = PlanetSimulator(size=128, seed=3, noise=4.0)
    frames = sim.frames(30)
    res = lucky_stack(frames, keep=0.3, sharpen=None)
    assert res.total == 30 and res.used == 9    # 30% de 30
    assert res.image.shape == frames[0].shape
    assert 0 <= res.ref < 30


def test_lucky_stack_reduces_background_noise():
    sim = PlanetSimulator(size=128, seed=5, noise=5.0)
    frames = sim.frames(30)
    res = lucky_stack(frames, keep=0.3, sharpen=None)   # sem wavelet p/ medir só o stack
    single = np.mean([_bg_std(f) for f in frames])
    assert _bg_std(res.image) < single * 0.7            # média de vários baixa o ruído


def test_lucky_stack_color():
    sim = PlanetSimulator(size=96, seed=2, color=True)
    frames = sim.frames(12)
    res = lucky_stack(frames, keep=0.5)
    assert res.image.ndim == 3 and res.image.shape[2] == 3


def test_lucky_stack_empty_raises():
    with pytest.raises(ValueError):
        lucky_stack([], keep=0.3)
