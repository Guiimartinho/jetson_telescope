"""Denoise IA (runner ONNX + fallback clássico)."""
import numpy as np
import pytest

from src.postproc import ai_denoise as aid


def test_fallback_reduces_noise_without_model():
    rng = np.random.default_rng(0)
    clean = np.full((80, 100, 3), 120.0, np.float32)
    clean[30:50, 40:60] = 200.0
    noisy = np.clip(clean + rng.normal(0, 25, clean.shape), 0, 255).astype(np.uint8)
    out = aid.ai_denoise(noisy, model_path=None, strength=1.0)
    assert out.shape == noisy.shape and out.dtype == np.uint8
    # o denoise reduz o ruído -> resíduo vs "clean" menor que o do ruidoso
    r_noisy = np.std(noisy.astype(float) - clean)
    r_out = np.std(out.astype(float) - clean)
    assert r_out < r_noisy


def test_mono_input_preserved():
    img = (np.random.default_rng(1).uniform(0, 255, (40, 40))).astype(np.uint8)
    out = aid.ai_denoise(img, model_path=None, strength=0.5)
    assert out.shape == img.shape


def test_no_model_path_is_noop_when_strength_zero():
    img = (np.random.default_rng(2).uniform(0, 255, (30, 30, 3))).astype(np.uint8)
    out = aid.ai_denoise(img, model_path=None, strength=0.0)
    assert np.array_equal(out, img)


@pytest.mark.skipif(not aid.HAS_ORT, reason="onnxruntime não instalado")
def test_providers_include_cpu():
    provs = aid.onnx_providers()
    assert "CPUExecutionProvider" in provs                        # sempre há CPU
