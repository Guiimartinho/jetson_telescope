"""Catálogo do céu (real) + filtro pela NOSSA óptica — o "atlas" do telescópio.

Não é simulação: são ~14.000 objetos reais (NGC/IC/Messier via OpenNGC/pyongc) com RA/DEC, tipo,
magnitude e tamanho. O ponto-chave (que o usuário levantou): nem todo objeto é observável com a NOSSA
lente — o que dá para capturar depende do **campo de visão** (distância focal + sensor) e da **magnitude
limite** (abertura + empilhamento). Este módulo carrega o catálogo e filtra pelo rig, além de calcular
visibilidade (altitude) num dado local/hora. O GOTO (T16) usa `find()` para apontar em qualquer alvo.

Requer `pyongc` (pip install pyongc — OpenNGC, licença livre). Ver docs/26.
"""
from __future__ import annotations
from dataclasses import dataclass
import math

try:
    from pyongc import ongc
    HAS_ONGC = True
except Exception:
    HAS_ONGC = False


@dataclass(frozen=True)
class SkyObject:
    name: str                    # designação principal (ex.: "M051", "NGC5194")
    ra_deg: float
    dec_deg: float
    kind: str                    # "Galaxy", "Nebula", "Globular Cluster", ...
    mag: float | None            # magnitude (V se houver, senão a melhor disponível)
    size_arcmin: float | None    # eixo maior aparente
    common: str = ""             # nome popular (ex.: "Whirlpool Galaxy")

    @property
    def label(self) -> str:
        return f"{self.name}" + (f" — {self.common}" if self.common else "")


@dataclass(frozen=True)
class Rig:
    """Óptica do telescópio. FOV e magnitude limite saem daqui."""
    focal_mm: float
    aperture_mm: float
    sensor_w_mm: float
    sensor_h_mm: float
    stacking: bool = True        # empilhamento aprofunda a magnitude limite

    def fov_deg(self) -> tuple[float, float]:
        """Campo de visão (largura, altura) em graus."""
        fw = math.degrees(2 * math.atan(self.sensor_w_mm / (2 * self.focal_mm)))
        fh = math.degrees(2 * math.atan(self.sensor_h_mm / (2 * self.focal_mm)))
        return (fw, fh)

    def limiting_mag(self) -> float:
        """Magnitude limite aproximada. Visual: 2.5 + 5·log10(D_mm). Empilhando, ~+4.5."""
        vis = 2.5 + 5 * math.log10(max(self.aperture_mm, 1.0))
        return vis + (4.5 if self.stacking else 0.0)


# rig padrão do projeto: IMX585 (1/1.2", ~11.2×6.3mm) + refrator ~250mm f/5 classe RedCat
DEFAULT_RIG = Rig(focal_mm=250.0, aperture_mm=51.0, sensor_w_mm=11.2, sensor_h_mm=6.3)

_DSO_KINDS = {"Galaxy", "Nebula", "Emission Nebula", "Reflection Nebula", "Planetary Nebula",
              "HII Ionized region", "Globular Cluster", "Open Cluster", "Cluster+Nebula",
              "Galaxy Pair", "Galaxy Triplet", "Supernova remnant"}


def _parse_ra(s: str) -> float:
    h, m, sec = (s.strip().split(":") + ["0", "0"])[:3]
    return (float(h) + float(m) / 60 + float(sec) / 3600) * 15.0


def _parse_dec(s: str) -> float:
    s = s.strip()
    sign = -1.0 if s.startswith("-") else 1.0
    d, m, sec = (s.lstrip("+-").split(":") + ["0", "0"])[:3]
    return sign * (float(d) + float(m) / 60 + float(sec) / 3600)


def _best_mag(mags):
    if not mags:
        return None
    v = mags[1] if len(mags) > 1 and mags[1] is not None else None   # V
    if v is not None:
        return float(v)
    for x in mags:                                                   # senão a 1ª disponível
        if x is not None:
            return float(x)
    return None


def _to_obj(o) -> SkyObject | None:
    try:
        mag = _best_mag(getattr(o, "magnitudes", None))
        dims = getattr(o, "dimensions", None)
        size = float(dims[0]) if dims and dims[0] is not None else None
        ids = getattr(o, "identifiers", None)
        common = ""
        if ids and len(ids) > 3 and ids[3]:
            common = ids[3][0]
        return SkyObject(name=o.name, ra_deg=_parse_ra(o.ra), dec_deg=_parse_dec(o.dec),
                         kind=o.type, mag=mag, size_arcmin=size, common=common)
    except Exception:
        return None


_CACHE: list[SkyObject] | None = None


def load(dso_only: bool = True) -> list[SkyObject]:
    """Carrega o catálogo (cacheado). `dso_only` mantém só objetos de céu profundo com RA/DEC."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    if not HAS_ONGC:
        raise RuntimeError("pyongc não instalado — pip install pyongc (catálogo OpenNGC)")
    out = []
    for o in ongc.listObjects():
        if not getattr(o, "ra", None) or not getattr(o, "dec", None):
            continue
        so = _to_obj(o)
        if so is None:
            continue
        if dso_only and so.kind not in _DSO_KINDS:
            continue
        out.append(so)
    _CACHE = out
    return out


def find(name: str) -> SkyObject | None:
    """Resolve um alvo pelo nome (ex.: 'M51', 'NGC5194', 'Whirlpool')."""
    if not HAS_ONGC:
        return None
    try:
        o = ongc.get(name=name)
        return _to_obj(o) if o else None
    except Exception:
        # busca por nome popular no catálogo carregado
        n = name.lower()
        for so in load():
            if n in so.common.lower() or n == so.name.lower():
                return so
        return None


def framable(objects, rig: Rig = DEFAULT_RIG, min_frac: float = 0.03, max_frac: float = 0.9):
    """Objetos que CABEM no campo e são brilhantes o bastante para a nossa óptica.

    Mantém: magnitude ≤ limite do rig (ou desconhecida) E tamanho entre min_frac e max_frac do menor
    lado do FOV (nem pontinho, nem maior que o quadro)."""
    fov_w, fov_h = rig.fov_deg()
    fov_min_arcmin = min(fov_w, fov_h) * 60.0
    maglim = rig.limiting_mag()
    out = []
    for o in objects:
        if o.mag is not None and o.mag > maglim:
            continue
        if o.size_arcmin is not None:
            if not (min_frac * fov_min_arcmin <= o.size_arcmin <= max_frac * fov_min_arcmin):
                continue
        out.append(o)
    return out


def altitude_deg(obj: SkyObject, lat: float, lon: float, when) -> float:
    """Altitude do objeto (graus) para um observador (lat, lon) num instante `when` (astropy Time).
    >0 acima do horizonte. Usa astropy (reuso)."""
    from astropy.coordinates import EarthLocation, SkyCoord, AltAz
    import astropy.units as u
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    c = SkyCoord(ra=obj.ra_deg * u.deg, dec=obj.dec_deg * u.deg)
    return float(c.transform_to(AltAz(obstime=when, location=loc)).alt.deg)


def visible(objects, lat: float, lon: float, when, min_alt: float = 25.0):
    """Filtra os objetos acima de `min_alt` graus no horizonte, do mais alto p/ o mais baixo."""
    scored = [(altitude_deg(o, lat, lon, when), o) for o in objects]
    return [o for alt, o in sorted(scored, key=lambda t: -t[0]) if alt >= min_alt]
