"""Configuração da sessão da Fase 1."""
from __future__ import annotations
from dataclasses import dataclass, field

from ..capture.simulator import SimConfig
from ..gpu.quality import QualityConfig


@dataclass
class SessionConfig:
    # Fonte de frames
    source: str = "sim"                # 'sim' | 'indi'
    width: int = 1600
    height: int = 1200
    frames: int = 0                    # 0 = roda até Ctrl+C (live); >0 = para depois
    # Sub-configs
    sim: SimConfig = field(default_factory=SimConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    # INDI (usado só se source='indi')
    indi_device: str = "ASI585MC"
    indi_exposure_s: float = 2.0
    indi_gain: int = 250
    # Saída
    web: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    out_dir: str = "output"
    save_every: int = 25               # salva PNG a cada N frames empilhados
    enhance: bool = False              # pós-processo (remoção de gradiente/denoise) no frame final
