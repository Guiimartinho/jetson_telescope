"""Alinhamento polar por três pontos — o método do Ekos, do NINA e do ASIAIR (docs/08: reusar
o algoritmo, não reinventar).

A montagem equatorial gira em torno do eixo polar DELA. Se esse eixo não aponta para o polo
celeste, o céu escorrega na foto longa. Para medir o erro:

  1. reconhece-se o céu (plate solve) em três posições, girando SÓ o eixo de ascensão reta;
  2. os três centros de campo caem num círculo em volta do eixo da montagem: o eixo é a normal
     desse círculo;
  3. compara-se o eixo com o polo celeste e separa-se o erro nas duas direções que a pessoa
     ajusta à mão: ALTITUDE (o parafuso que sobe e desce) e AZIMUTE (o que gira para os lados).

Tudo é feito no referencial preso à Terra (ângulo horário, declinação): nele o eixo da montagem
e o polo ficam parados, mesmo com o céu girando durante a medida. Serve para os dois hemisférios:
ao sul do equador o eixo aponta para o polo SUL.

Módulo de geometria pura (sem hardware): quem aponta e reconhece o céu é quem chama.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

ALIGNED_ARCMIN = 2.0                 # abaixo disto, dá para fotografar minutos sem arrasto
MIN_SPREAD_DEG = 5.0                 # giro mínimo entre os pontos para o círculo ficar definido


@dataclass(frozen=True)
class PolarError:
    """Quanto o eixo da montagem erra o polo, em minutos de arco.

    `alt_arcmin` > 0: o eixo está ALTO demais (abaixe). `az_arcmin` > 0: o eixo está a LESTE do
    polo (gire para oeste). Os lados são os da bússola, e valem ao norte e ao sul do equador."""
    alt_arcmin: float
    az_arcmin: float

    @property
    def total_arcmin(self) -> float:
        return math.hypot(self.alt_arcmin, self.az_arcmin)

    @property
    def aligned(self) -> bool:
        return self.total_arcmin <= ALIGNED_ARCMIN

    def as_dict(self) -> dict:
        return {"alt_arcmin": round(self.alt_arcmin, 1), "az_arcmin": round(self.az_arcmin, 1),
                "total_arcmin": round(self.total_arcmin, 1), "aligned": self.aligned}


def hadec_vector(ha_deg: float, dec_deg: float) -> np.ndarray:
    """Direção no referencial preso à Terra: x para o meridiano sul, y para oeste, z para o
    polo norte. `ha_deg` é o ângulo horário (tempo sideral local menos a ascensão reta)."""
    ha, dec = math.radians(ha_deg), math.radians(dec_deg)
    return np.array([math.cos(dec) * math.cos(ha), math.cos(dec) * math.sin(ha), math.sin(dec)])


def _to_horizontal(v: np.ndarray, lat_deg: float) -> tuple[float, float]:
    """Vetor (ângulo horário, declinação) -> (altitude, azimute) em graus. Azimute a partir do
    norte, crescendo para leste."""
    phi = math.radians(lat_deg)
    x, y, z = (float(c) for c in v)
    south = x * math.sin(phi) - z * math.cos(phi)          # componente para o sul
    up = x * math.cos(phi) + z * math.sin(phi)             # componente para o zênite
    alt = math.degrees(math.asin(max(-1.0, min(1.0, up))))
    az = math.degrees(math.atan2(-y, -south)) % 360.0      # leste = -oeste; norte = -sul
    return alt, az


def from_horizontal(alt_deg: float, az_deg: float, lat_deg: float) -> np.ndarray:
    """O inverso de `_to_horizontal`: usado pelo simulador para montar um eixo desalinhado."""
    phi, alt, az = math.radians(lat_deg), math.radians(alt_deg), math.radians(az_deg)
    north, east, up = math.cos(alt) * math.cos(az), math.cos(alt) * math.sin(az), math.sin(alt)
    south, west = -north, -east
    return np.array([south * math.sin(phi) + up * math.cos(phi), west,
                     -south * math.cos(phi) + up * math.sin(phi)])


def pole_altaz(lat_deg: float) -> tuple[float, float]:
    """Onde o polo celeste visível fica no céu do observador: (altitude, azimute)."""
    return abs(lat_deg), (0.0 if lat_deg >= 0 else 180.0)


def axis_from_three(p1, p2, p3) -> np.ndarray | None:
    """O eixo de rotação que leva p1 a p2 a p3 (vetores unitários), ou None se os três pontos
    estão juntos demais para definir um círculo."""
    a, b, c = (np.asarray(p, dtype=float) for p in (p1, p2, p3))
    spread = min(math.degrees(math.acos(max(-1.0, min(1.0, float(np.dot(u, v))))))
                 for u, v in ((a, b), (b, c)))
    if spread < MIN_SPREAD_DEG:
        return None
    normal = np.cross(b - a, c - b)
    norm = float(np.linalg.norm(normal))
    if norm < 1e-9:
        return None
    return normal / norm


def polar_error(points, lat_deg: float) -> PolarError | None:
    """O erro do eixo polar a partir de três centros de campo `(ha_deg, dec_deg)`, tomados
    girando só a ascensão reta. None se a geometria não deixa medir."""
    if len(points) != 3:
        return None
    axis = axis_from_three(*(hadec_vector(ha, dec) for ha, dec in points))
    if axis is None:
        return None
    pole_alt, pole_az = pole_altaz(lat_deg)
    pole = from_horizontal(pole_alt, pole_az, lat_deg)
    if float(np.dot(axis, pole)) < 0:                      # a normal sai com sinal arbitrário
        axis = -axis
    alt, az = _to_horizontal(axis, lat_deg)
    d_az = (az - pole_az + 180.0) % 360.0 - 180.0
    return PolarError(alt_arcmin=(alt - pole_alt) * 60.0,
                      az_arcmin=_east(lat_deg) * d_az * math.cos(math.radians(pole_alt)) * 60.0)


def _east(lat_deg: float) -> float:
    """Para que lado do AZIMUTE fica o leste de quem olha o polo. O azimute cresce do norte para
    o leste: olhando o polo norte (0 graus), leste é azimute maior; olhando o polo sul (180),
    leste é azimute MENOR. Sem isto, ao sul do equador a conta mandaria girar para o lado errado."""
    return 1.0 if lat_deg >= 0 else -1.0


class SimPolarAxis:
    """Uma montagem de mentira com o eixo polar fora do lugar — o análogo, para o alinhamento,
    do `SimRaDecMount` do goto. Devolve o centro do campo que o plate solve veria depois de
    girar a ascensão reta, com o ruído de uma medida de verdade."""

    def __init__(self, lat_deg: float = -23.55, alt_err_arcmin: float = 38.0,
                 az_err_arcmin: float = -52.0, noise_arcmin: float = 0.15, seed: int = 5):
        self.lat = float(lat_deg)
        self.alt_err, self.az_err = float(alt_err_arcmin), float(az_err_arcmin)
        self.noise = float(noise_arcmin)
        self.rng = np.random.default_rng(seed)

    def axis(self) -> np.ndarray:
        pole_alt, pole_az = pole_altaz(self.lat)
        cos_alt = max(math.cos(math.radians(pole_alt)), 1e-6)
        return from_horizontal(pole_alt + self.alt_err / 60.0,
                               pole_az + _east(self.lat) * self.az_err / 60.0 / cos_alt, self.lat)

    def adjust(self, d_alt_arcmin: float, d_az_arcmin: float) -> None:
        """Os parafusos da montagem: mexem no eixo (com a folga de uma mão de verdade). Mais
        altitude sobe o eixo; mais azimute o leva para LESTE — nos dois hemisférios."""
        slop = lambda v: v * float(self.rng.uniform(0.9, 1.0))          # noqa: E731
        self.alt_err += slop(d_alt_arcmin)
        self.az_err += slop(d_az_arcmin)

    def solve(self, rotation_deg: float, start=(20.0, 35.0)) -> tuple[float, float]:
        """O campo `(ha_deg, dec_deg)` depois de girar a ascensão reta `rotation_deg` a partir
        de uma direção inicial (afastada do polo `start[1]` graus, para o círculo ser largo)."""
        axis = self.axis()
        helper = np.array([1.0, 0.0, 0.0]) if abs(axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(axis, helper)
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        away, turn = math.radians(start[1]), math.radians(start[0] + rotation_deg)
        p = (math.cos(away) * axis
             + math.sin(away) * (math.cos(turn) * u + math.sin(turn) * v))
        p = p + self.rng.normal(0.0, math.radians(self.noise / 60.0), 3)
        p /= np.linalg.norm(p)
        return (math.degrees(math.atan2(p[1], p[0])) % 360.0,
                math.degrees(math.asin(max(-1.0, min(1.0, float(p[2]))))))
