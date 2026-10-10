"""O céu visto pela API: lista de alvos com altitude agora e a ficha de um alvo na noite.

Reusa o catálogo real (`core.catalog`, OpenNGC) e a nossa óptica (`DEFAULT_RIG`). A altitude de
todos os objetos sai de uma conta vetorizada, então filtrar "o que está alto agora e cabe no
campo" entre 12 mil objetos custa milissegundos.
"""
from __future__ import annotations

import os
import re
from datetime import timedelta

from ..core import catalog as cat

NIGHT_SUN_ALT = -12.0          # Sol abaixo disto: escuro o bastante para céu profundo
MIN_TARGET_ALT = 25.0          # abaixo disto a atmosfera estraga a imagem
TYPES = ("nebula", "galaxy", "cluster", "other")

_TYPES = {"nebula": ("Nebula", "Emission Nebula", "Reflection Nebula", "Planetary Nebula",
                     "HII Ionized region", "Supernova remnant", "Dark Nebula",
                     "Star cluster + Nebula"),
          "galaxy": ("Galaxy", "Galaxy Pair", "Galaxy Triplet", "Group of galaxies"),
          "cluster": ("Open Cluster", "Globular Cluster")}
# alvos com resultado real do nosso pipeline: id do alvo -> chave do stack (as do estúdio)
_STACK_OF = {"M8": "lagoon_trifid", "M20": "lagoon_trifid", "NGC2239": "rosette", "M51": "m51"}
_ID = re.compile(r"[A-Za-z0-9]{1,24}")
_ISO = "%Y-%m-%dT%H:%M:%SZ"


def type_of(kind: str) -> str:
    for t, kinds in _TYPES.items():
        if kind in kinds:
            return t
    return "other"


def short_id(name: str) -> str:
    """`NGC0253` -> `NGC253`, `IC0434` -> `IC434`: como as pessoas escrevem."""
    for prefix in ("NGC", "IC"):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return prefix + str(int(name[len(prefix):]))
    return name


def target_id(obj) -> str:
    """O identificador do alvo na API: o número Messier quando existe, senão o do catálogo."""
    return obj.messier or short_id(obj.name)


def _objects():
    try:
        return cat.load() if cat.HAS_ONGC else []
    except Exception:
        return []


def find(text: str):
    """Resolve o que o app mandou (`M8`, `NGC 253`, `ic434`) num objeto do catálogo, ou None.
    Só letras, números e espaços chegam ao catálogo: o texto vem de fora."""
    name = "".join(str(text or "").split())
    if not _ID.fullmatch(name) or not cat.HAS_ONGC:
        return None
    try:
        return cat.find(name)
    except Exception:
        return None


def resolve_id(text: str) -> str | None:
    """O identificador do alvo que vai para o Controller, ou None se não existe. Sem o
    catálogo instalado aceita o nome simples como veio: o Controller tem os alvos de bancada."""
    name = "".join(str(text or "").split())
    if not _ID.fullmatch(name):
        return None
    if not cat.HAS_ONGC:
        return name.upper()
    obj = find(name)
    return target_id(obj) if obj is not None else None


def _fits(obj, rig) -> bool | None:
    """Cabe no campo? None quando o catálogo não traz o tamanho."""
    if obj.size_arcmin is None:
        return None
    fov_min = min(rig.fov_deg()) * 60.0
    return 0.03 * fov_min <= obj.size_arcmin <= 0.9 * fov_min


def thumb_key(obj) -> str | None:
    """Chave de imagem do alvo (as mesmas do console), se houver imagem. A chave sai do
    identificador do CATÁLOGO, nunca do texto recebido: nada de fora vira nome de arquivo."""
    tid = target_id(obj)
    if tid in _STACK_OF:
        return _STACK_OF[tid]
    if _ID.fullmatch(tid) and os.path.exists(f"data/sky_{tid}.jpg"):
        return "@sky:" + tid
    return None


def _item(obj, alt, rig) -> dict:
    tid = target_id(obj)
    return {"id": tid, "name": obj.common or tid, "catalog": short_id(obj.name),
            "type": type_of(obj.kind),
            "ra_deg": round(obj.ra_deg, 4), "dec_deg": round(obj.dec_deg, 4),
            "mag": None if obj.mag is None else round(obj.mag, 1),
            "size_arcmin": obj.size_arcmin,
            "alt_deg": round(float(alt), 1), "fits": _fits(obj, rig),
            "has_thumb": thumb_key(obj) is not None}


def _match(obj, needle: str) -> int | None:
    """Quão bem o objeto casa com a busca: 0 = é este, 1 = começa assim, 2 = contém; None = não."""
    best = None
    for text in (obj.messier, short_id(obj.name), obj.name, obj.common):
        t = text.lower().replace(" ", "")
        if not t or needle not in t:
            continue
        rank = 0 if t == needle else (1 if t.startswith(needle) else 2)
        best = rank if best is None else min(best, rank)
    return best


def list_targets(lat, lon, when, q="", type_="", visible=False, fits=False,
                 limit=50, offset=0, rig=cat.DEFAULT_RIG) -> dict:
    """Busca no catálogo. Sem texto: do mais alto para o mais baixo. Com texto: primeiro o que
    casa melhor. `visible`: só acima de 25 graus agora. `fits`: só o que cabe no nosso campo."""
    objs = _objects()
    if not objs:
        return {"total": 0, "items": []}
    alts = cat.altitudes_deg(objs, lat, lon, when)
    needle = "".join(q.lower().split())
    rows = []
    for obj, alt in zip(objs, alts):
        if visible and alt < MIN_TARGET_ALT:
            continue
        if type_ and type_of(obj.kind) != type_:
            continue
        if fits and not _fits(obj, rig):
            continue
        rank = _match(obj, needle) if needle else 0
        if rank is None:
            continue
        rows.append((rank, -float(alt), obj))
    rows.sort(key=lambda r: r[:2])
    start = max(0, int(offset))
    page = rows[start:start + max(1, min(int(limit), 200))]
    return {"total": len(rows), "items": [_item(o, -neg_alt, rig) for _, neg_alt, o in page]}


def target_detail(text: str, lat, lon, when, rig=cat.DEFAULT_RIG) -> dict | None:
    """A ficha: os dados do alvo, a altitude ao longo da próxima noite e a melhor janela."""
    obj = find(text)
    if obj is None:
        return None
    out = _item(obj, cat.altitudes_deg([obj], lat, lon, when)[0], rig)
    step = timedelta(minutes=20)
    curve, best, run = [], [], []
    for i in range(72):                                    # 24 h em passos de 20 min
        t = when + i * step
        if cat.sun_altitude_deg(lat, lon, t) > NIGHT_SUN_ALT:
            if curve:                                      # a noite acabou
                break
            continue
        alt = float(cat.altitudes_deg([obj], lat, lon, t)[0])
        curve.append({"utc": t.strftime(_ISO), "alt_deg": round(alt, 1)})
        if alt >= MIN_TARGET_ALT:
            run.append(t)
        else:
            best, run = (run if len(run) > len(best) else best), []
    best = run if len(run) > len(best) else best
    out["night"] = {"altitude": curve,
                    "best_from": best[0].strftime(_ISO) if best else None,
                    "best_to": best[-1].strftime(_ISO) if best else None}
    fov = rig.fov_deg()
    out["framing"] = {"fov_deg": [round(fov[0], 2), round(fov[1], 2)],
                      "fills": (None if obj.size_arcmin is None
                                else round(obj.size_arcmin / (min(fov) * 60.0), 2))}
    return out
