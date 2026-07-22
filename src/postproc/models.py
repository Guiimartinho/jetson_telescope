"""Registro de modelos de IA embarcados — UM modelo por TAREFA (não vários do mesmo).

O jeito certo de "embarcar IA": uma biblioteca pequena com UM modelo por tarefa de realce
(denoise, remover estrelas, remover gradiente, deconvolução). Não são vários StarNet — é um StarNet
(remover estrelas) + um denoise + um gradiente, etc.

Formato no Jetson: **ONNX** (roda via onnxruntime com EP TensorRT/CUDA — ver `ai_denoise`). Os apps
x86 (StarNet++ binário, GraXpert-pip que exige Py≥3.11) NÃO rodam no Orin aarch64/Py3.10 — então
embarcamos os MODELOS (.onnx), não as ferramentas. Basta dropar `models/<tarefa>.onnx` (ou apontar a
env `TELE_MODEL_<TAREFA>`). Ver docs/29.
"""
from __future__ import annotations
import os

TASKS = ("denoise", "starless", "gradient", "deconv")

_DIR = os.environ.get(
    "TELE_MODELS_DIR",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "models")))


def model_for(task: str) -> str | None:
    """Caminho do modelo ONNX para a tarefa, ou None. Prioridade: env `TELE_MODEL_<TASK>` → models/<task>.onnx."""
    env = os.environ.get(f"TELE_MODEL_{task.upper()}")
    if env and os.path.exists(env):
        return env
    p = os.path.join(_DIR, f"{task}.onnx")
    return p if os.path.exists(p) else None


def available() -> dict:
    """Modelos presentes (tarefa → caminho)."""
    return {t: model_for(t) for t in TASKS if model_for(t)}
