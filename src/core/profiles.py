"""T5 — Perfis de equipamento em YAML (trocar rig sem editar código). Reuso: PyYAML."""
from __future__ import annotations

from .vo import EquipmentProfile

try:
    import yaml
    HAS_YAML = True
except Exception:
    HAS_YAML = False


def profile_from_dict(d: dict) -> EquipmentProfile:
    campos = {"name", "camera", "sensor_px_um", "mount", "focal_mm", "aperture_mm"}
    faltando = campos - set(d)
    if faltando:
        raise ValueError(f"perfil incompleto — faltam campos: {sorted(faltando)}")
    return EquipmentProfile(**{k: d[k] for k in campos})


def load_profile(path: str) -> EquipmentProfile:
    if not HAS_YAML:
        raise RuntimeError("PyYAML não instalado (pip install pyyaml)")
    with open(path, encoding="utf-8") as f:
        return profile_from_dict(yaml.safe_load(f))
