"""T5 — Value Objects (DDD tático): tipos pequenos, imutáveis, com unidades e regras.

Dão clareza e segurança a conceitos do domínio (apontamento, FWHM, escala, equipamento)
sem o peso do DDD completo. Ver docs/11 e docs/17.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Pointing:
    ra_deg: float
    dec_deg: float
    rot_deg: float = 0.0


@dataclass(frozen=True)
class PixelScale:
    arcsec_per_px: float

    @staticmethod
    def from_optics(pixel_um: float, focal_mm: float) -> "PixelScale":
        return PixelScale(206.265 * pixel_um / focal_mm)


@dataclass(frozen=True)
class Fwhm:
    px: float

    def arcsec(self, scale: PixelScale) -> float:
        return self.px * scale.arcsec_per_px


@dataclass(frozen=True)
class EquipmentProfile:
    name: str
    camera: str
    sensor_px_um: float
    mount: str
    focal_mm: float
    aperture_mm: float

    @property
    def pixscale(self) -> PixelScale:
        return PixelScale.from_optics(self.sensor_px_um, self.focal_mm)

    @property
    def fratio(self) -> float:
        return self.focal_mm / self.aperture_mm
