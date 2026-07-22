import numpy as np
import scipy.ndimage as ndi

from src.planetary.lucky import sharpness, grade, select_best


def _tex(n=96, seed=0):
    return np.random.default_rng(seed).uniform(0, 255, (n, n)).astype(np.float32)


def test_sharper_frame_scores_higher():
    base = _tex()
    blur = ndi.gaussian_filter(base, 3.0)
    assert sharpness(base) > sharpness(blur)


def test_grade_length_and_order():
    frames = [_tex(seed=0), ndi.gaussian_filter(_tex(seed=0), 4.0)]
    g = grade(frames)
    assert len(g) == 2 and g[0] > g[1]


def test_select_best_picks_sharpest():
    scores = [1.0, 5.0, 2.0, 9.0, 3.0]
    idx = select_best(scores, keep=0.4)          # 40% de 5 = 2
    assert set(idx.tolist()) == {1, 3}           # índices dos scores 5 e 9
    assert list(idx) == sorted(idx)              # devolvidos em ordem crescente


def test_select_best_min_keep():
    idx = select_best([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], keep=0.0, min_keep=1)
    assert len(idx) == 1 and idx[0] == 9         # o mais nítido (score 10)


def test_select_best_empty():
    assert len(select_best([], keep=0.5)) == 0
