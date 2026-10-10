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
    messier: str = ""            # número Messier como se escreve (ex.: "M51"); vazio se não tem

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
              "HII Ionized region", "Globular Cluster", "Open Cluster", "Star cluster + Nebula",
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
        messier = ""
        if ids and ids[0]:                                # "M031" -> "M31"
            messier = "M" + str(int(str(ids[0]).lstrip("Mm")))
        return SkyObject(name=o.name, ra_deg=_parse_ra(o.ra), dec_deg=_parse_dec(o.dec),
                         kind=o.type, mag=mag, size_arcmin=size, common=common, messier=messier)
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


_ASTROPY_OFFLINE = False


def configure_astropy_offline() -> bool:
    """Desliga o download automático de tabelas IERS do astropy. Idempotente.

    O telescópio opera em campo SEM internet (docs/33). Na primeira transformação de
    coordenada o astropy tenta BAIXAR a tabela IERS mais recente; medido no Orin, isso
    custou ~70 s do arranque do Atlas (e em campo vira timeout de DNS/TCP a cada boot).

    Desligar o download exige DUAS travas, senão o cálculo passa a levantar exceção (é o que
    o teste de regressão pega):
      * `auto_download=False`  — não sai para a rede; usa a tabela embutida;
      * `auto_max_age=None`    — aceita a tabela embutida mesmo "velha". Sem isto o astropy
        levanta `ValueError: interpolating from IERS_Auto using predictive values that are
        more than 30.0 days old` — exatamente o caso do Orin, cujo log já acusava
        `IERSStaleWarning`. É a saída recomendada pelo próprio astropy para uso offline.

    A perda de precisão é de milissegundos de arco (orientação da Terra); filtramos
    visibilidade em GRAUS. Ver docs/34.
    """
    global _ASTROPY_OFFLINE
    if _ASTROPY_OFFLINE:
        return True
    try:
        from astropy.utils import iers
    except Exception:
        return False
    iers.conf.auto_download = False
    iers.conf.auto_max_age = None                     # aceita a tabela embutida "velha"
    try:
        iers.conf.iers_degraded_accuracy = "ignore"   # astropy >= 5.1 (datas fora da cobertura)
    except Exception:
        pass
    _ASTROPY_OFFLINE = True
    return True


def altitude_deg(obj: SkyObject, lat: float, lon: float, when) -> float:
    """Altitude do objeto (graus) para um observador (lat, lon) num instante `when` (astropy Time).
    >0 acima do horizonte. Usa astropy (reuso)."""
    configure_astropy_offline()          # nunca sair para a internet no meio do campo
    from astropy.coordinates import EarthLocation, SkyCoord, AltAz
    import astropy.units as u
    loc = EarthLocation(lat=lat * u.deg, lon=lon * u.deg)
    c = SkyCoord(ra=obj.ra_deg * u.deg, dec=obj.dec_deg * u.deg)
    return float(c.transform_to(AltAz(obstime=when, location=loc)).alt.deg)


def _days_since_j2000(when) -> float:
    """Dias desde J2000.0 para um `datetime` com fuso (UTC)."""
    return when.timestamp() / 86400.0 + 2440587.5 - 2451545.0


def _alt_from_radec(ra_deg, dec_deg, lat: float, lon: float, when):
    """Altitude (graus) por trigonometria esférica direta; `ra_deg`/`dec_deg` escalares ou arrays."""
    import numpy as np
    gmst = (280.46061837 + 360.98564736629 * _days_since_j2000(when)) % 360.0
    hour_angle = np.radians(gmst + lon - np.asarray(ra_deg, dtype=float))
    phi, dec = math.radians(lat), np.radians(np.asarray(dec_deg, dtype=float))
    return np.degrees(np.arcsin(np.clip(
        math.sin(phi) * np.sin(dec) + math.cos(phi) * np.cos(dec) * np.cos(hour_angle), -1, 1)))


def altitudes_deg(objects, lat: float, lon: float, when):
    """Altitude de MUITOS objetos de uma vez (NumPy). Filtra o catálogo inteiro (12 mil objetos)
    em milissegundos, onde `altitude_deg` (astropy) levaria segundos. Sem precessão nem refração:
    erra menos de 1 grau, o que basta para decidir visibilidade. Para UM objeto com precisão,
    `altitude_deg` continua sendo a referência. `when`: datetime com fuso."""
    import numpy as np
    objects = list(objects)
    if not objects:
        return np.zeros(0)
    return _alt_from_radec([o.ra_deg for o in objects], [o.dec_deg for o in objects], lat, lon, when)


def sun_altitude_deg(lat: float, lon: float, when) -> float:
    """Altitude do Sol (graus), fórmula de baixa precisão (~0,1 grau): serve para saber se é
    noite. Abaixo de -12 graus o céu já está escuro o bastante para céu profundo."""
    d = _days_since_j2000(when)
    g = math.radians((357.528 + 0.9856003 * d) % 360.0)
    lam = math.radians((280.460 + 0.9856474 * d) % 360.0 + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * d)
    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360.0
    dec = math.degrees(math.asin(math.sin(eps) * math.sin(lam)))
    return float(_alt_from_radec(ra, dec, lat, lon, when))


def visible(objects, lat: float, lon: float, when, min_alt: float = 25.0):
    """Filtra os objetos acima de `min_alt` graus no horizonte, do mais alto p/ o mais baixo."""
    scored = [(altitude_deg(o, lat, lon, when), o) for o in objects]
    return [o for alt, o in sorted(scored, key=lambda t: -t[0]) if alt >= min_alt]
