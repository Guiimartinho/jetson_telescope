"""Sol, Lua e planetas em baixa precisão: "o que está no céu agora" e o ponto de partida do goto.

Sem dependência nem tabela externa (roda no campo, sem internet):

  * planetas e Sol — elementos keplerianos aproximados do JPL ("Approximate Positions of the
    Planets", válidos de 1800 a 2050): erro de poucos minutos de arco;
  * Lua — a série curta do Astronomical Almanac: erro de ~0,3 grau, mais a paralaxe (até 1
    grau), que entra na altitude.

As coordenadas saem em J2000, como as do catálogo. Para fotografar, isso é só o ponto de
partida: quem centraliza é o laço apontar → reconhecer o céu → corrigir.
"""
from __future__ import annotations

import math
from datetime import datetime

from .catalog import _alt_from_radec, _days_since_j2000

OBLIQUITY_J2000 = 23.43928
PRECESSION_DEG_PER_CENTURY = 1.397          # precessão geral em longitude

# a (UA), e, I, L, ϖ (longitude do periélio), Ω — valor em J2000 e variação por século
_ELEMENTS = {
    "mercury": ((0.38709927, 0.00000037), (0.20563593, 0.00001906), (7.00497902, -0.00594749),
                (252.25032350, 149472.67411175), (77.45779628, 0.16047689), (48.33076593, -0.12534081)),
    "venus": ((0.72333566, 0.00000390), (0.00677672, -0.00004107), (3.39467605, -0.00078890),
              (181.97909950, 58517.81538729), (131.60246718, 0.00268329), (76.67984255, -0.27769418)),
    "earth": ((1.00000261, 0.00000562), (0.01671123, -0.00004392), (-0.00001531, -0.01294668),
              (100.46457166, 35999.37244981), (102.93768193, 0.32327364), (0.0, 0.0)),
    "mars": ((1.52371034, 0.00001847), (0.09339410, 0.00007882), (1.84969142, -0.00813131),
             (-4.55343205, 19140.30268499), (-23.94362959, 0.44441088), (49.55953891, -0.29257343)),
    "jupiter": ((5.20288700, -0.00011607), (0.04838624, -0.00013253), (1.30439695, -0.00183714),
                (34.39644051, 3034.74612775), (14.72847983, 0.21252668), (100.47390909, 0.20469106)),
    "saturn": ((9.53667594, -0.00125060), (0.05386179, -0.00050991), (2.48599187, 0.00193609),
               (49.95424423, 1222.49362201), (92.59887831, -0.41897216), (113.66242448, -0.28867794)),
    "uranus": ((19.18916464, -0.00196176), (0.04725744, -0.00004397), (0.77263783, -0.00242939),
               (313.23810451, 428.48202785), (170.95427630, 0.40805281), (74.01692503, 0.04240589)),
    "neptune": ((30.06992276, 0.00026291), (0.00859048, 0.00005105), (1.77004347, 0.00035372),
                (-55.12002969, 218.45945325), (44.96476227, -0.32241464), (131.78422574, -0.00508664)),
}

# o que o app mostra, na ordem: (id, nome, tipo)
BODIES = (("moon", "Lua", "moon"), ("mercury", "Mercúrio", "planet"), ("venus", "Vênus", "planet"),
          ("mars", "Marte", "planet"), ("jupiter", "Júpiter", "planet"), ("saturn", "Saturno", "planet"),
          ("uranus", "Urano", "planet"), ("neptune", "Netuno", "planet"), ("sun", "Sol", "sun"))


def _heliocentric(name: str, t: float) -> tuple[float, float, float]:
    """Posição heliocêntrica (eclíptica J2000, UA) no século juliano `t` desde J2000."""
    a, e, inc, lon, peri, node = (v0 + v1 * t for v0, v1 in _ELEMENTS[name])
    w = math.radians(peri - node)
    m = math.radians((lon - peri + 180.0) % 360.0 - 180.0)
    ecc = m
    for _ in range(12):                                   # Kepler: E - e sen E = M
        ecc -= (ecc - e * math.sin(ecc) - m) / (1.0 - e * math.cos(ecc))
    x, y = a * (math.cos(ecc) - e), a * math.sqrt(1.0 - e * e) * math.sin(ecc)
    o, i = math.radians(node), math.radians(inc)
    cw, sw, co, so, ci, si = math.cos(w), math.sin(w), math.cos(o), math.sin(o), math.cos(i), math.sin(i)
    return ((cw * co - sw * so * ci) * x + (-sw * co - cw * so * ci) * y,
            (cw * so + sw * co * ci) * x + (-sw * so + cw * co * ci) * y,
            (sw * si) * x + (cw * si) * y)


def _equatorial(x: float, y: float, z: float) -> tuple[float, float]:
    """Vetor eclíptico J2000 -> (RA, DEC) em graus."""
    eps = math.radians(OBLIQUITY_J2000)
    ye, ze = y * math.cos(eps) - z * math.sin(eps), y * math.sin(eps) + z * math.cos(eps)
    return math.degrees(math.atan2(ye, x)) % 360.0, math.degrees(math.atan2(ze, math.hypot(x, ye)))


def planet_radec(name: str, when: datetime) -> tuple[float, float]:
    """RA/DEC geocêntricos (J2000, graus) de um planeta — ou do Sol (`sun`)."""
    t = _days_since_j2000(when) / 36525.0
    ex, ey, ez = _heliocentric("earth", t)
    if name == "sun":
        return _equatorial(-ex, -ey, -ez)
    px, py, pz = _heliocentric(name, t)
    return _equatorial(px - ex, py - ey, pz - ez)


def moon(when: datetime) -> dict:
    """A Lua: RA/DEC geocêntricos (J2000), paralaxe horizontal e fração iluminada (0 a 1)."""
    t = _days_since_j2000(when) / 36525.0

    def s(a, b):
        return math.sin(math.radians(a + b * t))

    def c(a, b):
        return math.cos(math.radians(a + b * t))

    lon = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87) - 1.27 * s(259.3, -413335.36)
           + 0.66 * s(235.7, 890534.22) + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03))
    lat = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89) - 0.28 * s(318.3, 6003.15)
           - 0.17 * s(217.6, -407332.21))
    parallax = (0.9508 + 0.0518 * c(135.0, 477198.87) + 0.0095 * c(259.3, -413335.36)
                + 0.0078 * c(235.7, 890534.22) + 0.0028 * c(269.9, 954397.74))
    lon -= PRECESSION_DEG_PER_CENTURY * t                 # equinócio da data -> J2000
    lam, beta = math.radians(lon), math.radians(lat)
    ra, dec = _equatorial(math.cos(beta) * math.cos(lam), math.cos(beta) * math.sin(lam), math.sin(beta))
    # fase: o ângulo entre a Lua e o Sol vistos daqui
    ex, ey, _ = _heliocentric("earth", t)
    sun_lon = math.atan2(-ey, -ex)
    elongation = math.acos(max(-1.0, min(1.0, math.cos(beta) * math.cos(lam - sun_lon))))
    return {"ra_deg": ra, "dec_deg": dec, "parallax_deg": parallax,
            "phase": (1.0 - math.cos(elongation)) / 2.0}


def bodies(lat: float, lon: float, when: datetime) -> list[dict]:
    """Lua, planetas e Sol, com a altitude de agora para este observador."""
    out = []
    for body_id, name, kind in BODIES:
        if body_id == "moon":
            m = moon(when)
            ra, dec = m["ra_deg"], m["dec_deg"]
            alt = float(_alt_from_radec(ra, dec, lat, lon, when))
            alt -= m["parallax_deg"] * math.cos(math.radians(alt))     # vista da superfície
            phase = round(m["phase"], 2)
        else:
            ra, dec = planet_radec(body_id, when)
            alt, phase = float(_alt_from_radec(ra, dec, lat, lon, when)), None
        out.append({"id": body_id, "name": name, "kind": kind,
                    "ra_deg": round(ra, 3), "dec_deg": round(dec, 3),
                    "alt_deg": round(alt, 1), "up": alt > 0.0, "phase": phase})
    return out


def body_radec(body_id: str, when: datetime) -> tuple[float, float] | None:
    """RA/DEC (J2000, graus) de um corpo pelo id (`moon`, `mars`, `sun`...), ou None."""
    if body_id == "moon":
        m = moon(when)
        return m["ra_deg"], m["dec_deg"]
    if body_id == "sun" or (body_id in _ELEMENTS and body_id != "earth"):
        return planet_radec(body_id, when)
    return None
