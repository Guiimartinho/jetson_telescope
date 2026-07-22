"""T6 — Persistência de sessão (resumo JSON) + telemetria estruturada (JSONL).

Grava o resumo de cada alvo/sessão (JSON) e um log append-only de eventos (JSONL) para
análise/resume. Ver docs/17.
"""
from __future__ import annotations
import json
import os


def save_session(path: str, summary: dict) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    return path


def load_session(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Telemetry:
    """Log append-only de eventos (uma linha JSON por evento)."""
    def __init__(self, path: str):
        self.path = path

    def log(self, **fields):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(fields, ensure_ascii=False) + "\n")

    def read(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [json.loads(ln) for ln in f if ln.strip()]
