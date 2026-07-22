"""Registro de modelos de IA (um por tarefa)."""
import os

from src.postproc import models


def test_absent_task_returns_none(monkeypatch):
    monkeypatch.delenv("TELE_MODEL_DENOISE", raising=False)
    monkeypatch.setenv("TELE_MODELS_DIR", "/caminho/inexistente")
    # recarrega o _DIR olhando a env
    import importlib
    importlib.reload(models)
    assert models.model_for("denoise") is None
    assert models.available() == {}


def test_env_var_points_to_model(tmp_path, monkeypatch):
    m = tmp_path / "denoise.onnx"
    m.write_bytes(b"fake-onnx")
    monkeypatch.setenv("TELE_MODEL_DENOISE", str(m))
    assert models.model_for("denoise") == str(m)
    assert "denoise" in models.available()


def test_models_dir_convention(tmp_path, monkeypatch):
    (tmp_path / "starless.onnx").write_bytes(b"x")
    monkeypatch.setenv("TELE_MODELS_DIR", str(tmp_path))
    monkeypatch.delenv("TELE_MODEL_STARLESS", raising=False)
    import importlib
    importlib.reload(models)
    assert models.model_for("starless") == os.path.join(str(tmp_path), "starless.onnx")
    importlib.reload(models)     # restaura estado padrão p/ outros testes
