"""O plano da noite: a fila de alvos que o dono montou, e quando cada um cabe.

Três peças:

  * `normalize` confere o que o app mandou (nome do campo no erro) e resolve cada alvo no
    catálogo;
  * `PlanStore` guarda a fila num arquivo: ela sobrevive a reinício;
  * `schedule` diz, para esta noite e este lugar, quando cada item começa e termina, e por que
    algum não cabe (nunca sobe o bastante, passa do amanhecer, se põe antes do fim).

A fila roda NA ORDEM em que o dono a deixou. Reordenar é mandar a lista de novo.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

from ..core import catalog as cat
from ..core.mosaic import panel_grid_radec
from . import sky

MAX_ITEMS = 40
STEP = timedelta(minutes=5)
OVERHEAD_S = 120                    # apontar, reconhecer o céu e focar — por painel
_ISO = "%Y-%m-%dT%H:%M:%SZ"
_LIMITS = {"frames": (1, 5000), "exposure_s": (1.0, 600.0), "min_alt_deg": (0.0, 80.0)}
_DEFAULTS = {"frames": 40, "exposure_s": 30.0, "min_alt_deg": sky.MIN_TARGET_ALT}


def _number(item: dict, key: str, where: str):
    value = item.get(key, _DEFAULTS[key])
    lo, hi = _LIMITS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        raise ValueError(f"{where}.{key}: use um número de {lo:g} a {hi:g}")
    return int(value) if key == "frames" else float(value)


def _grid(item: dict, where: str) -> list[int]:
    grid = item.get("mosaic", [1, 1])
    if (not isinstance(grid, (list, tuple)) or len(grid) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 6 for v in grid)):
        raise ValueError(f"{where}.mosaic: use [linhas, colunas], de 1 a 6")
    return [int(grid[0]), int(grid[1])]


def _ok_id(value) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 24 and value.replace("-", "").isalnum()


def normalize(items) -> list[dict]:
    """A fila como veio do app -> a fila como é guardada. `ValueError` diz o campo que não serve."""
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError(f"items: use uma lista de até {MAX_ITEMS} alvos")
    explicit = {i.get("id") for i in items if isinstance(i, dict) and _ok_id(i.get("id"))}
    out, seen = [], set()
    for n, item in enumerate(items):
        where = f"items[{n}]"
        if not isinstance(item, dict):
            raise ValueError(f"{where}: use um objeto")
        target = sky.resolve_id(item.get("target"))
        if target is None:
            raise ValueError(f"{where}.target: alvo fora do catálogo")
        obj = sky.find(target)
        item_id = item.get("id")
        if not _ok_id(item_id) or item_id in seen:        # sem id (ou repetido): ganha um
            k = 1
            while f"p-{k}" in seen or f"p-{k}" in explicit:
                k += 1
            item_id = f"p-{k}"
        seen.add(item_id)
        overlap = item.get("overlap", 0.15)
        if isinstance(overlap, bool) or not isinstance(overlap, (int, float)) or not 0.05 <= overlap <= 0.5:
            raise ValueError(f"{where}.overlap: use um número de 0.05 a 0.5")
        out.append({
            "id": item_id, "target": target,
            "name": (obj.common or target) if obj is not None else target,
            "type": sky.type_of(obj.kind) if obj is not None else "other",
            "ra_deg": None if obj is None else round(obj.ra_deg, 4),
            "dec_deg": None if obj is None else round(obj.dec_deg, 4),
            "frames": _number(item, "frames", where),
            "exposure_s": _number(item, "exposure_s", where),
            "min_alt_deg": _number(item, "min_alt_deg", where),
            "mosaic": _grid(item, where), "overlap": float(overlap)})
    return out


class PlanStore:
    """A fila da noite, num arquivo JSON (gravado de uma vez: nunca fica pela metade)."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else None
        self._lock = threading.Lock()
        self._items: list[dict] = []
        if self._path is not None and self._path.exists():
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._items = [i for i in data.get("items", []) if isinstance(i, dict)]
            except (OSError, ValueError, AttributeError):
                self._items = []                  # arquivo estragado: começa de fila vazia

    def items(self) -> list[dict]:
        with self._lock:
            return [dict(i) for i in self._items]

    def replace(self, items: list[dict]) -> list[dict]:
        """Troca a fila inteira (já conferida por `normalize`)."""
        with self._lock:
            self._items = [dict(i) for i in items]
            if self._path is not None:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._path.with_name(f"{self._path.name}.{os.getpid()}.tmp")
                tmp.write_text(json.dumps({"items": self._items}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
                os.replace(tmp, self._path)
            return [dict(i) for i in self._items]


def night_bounds(lat: float, lon: float, now: datetime) -> tuple[datetime | None, datetime | None]:
    """A noite em curso, ou a próxima: do escuro (Sol abaixo de -12 graus) até o amanhecer."""
    start = None
    for i in range(24 * 12 + 1):
        t = now + i * STEP
        dark = cat.sun_altitude_deg(lat, lon, t) <= sky.NIGHT_SUN_ALT
        if start is None and dark:
            start = t
        elif start is not None and not dark:
            return start, t
    return start, (now + timedelta(hours=24) if start is not None else None)


def duration_s(item: dict) -> int:
    panels = item["mosaic"][0] * item["mosaic"][1]
    return int(round(panels * (OVERHEAD_S + item["frames"] * item["exposure_s"])))


def schedule(items: list[dict], lat: float, lon: float, now: datetime) -> dict:
    """Quando cada item da fila acontece nesta noite. `status` de cada um:

      `ok`           cabe;
      `never_up`     não chega à altitude mínima enquanto há noite (e não entra na conta);
      `after_dawn`   começa, mas termina depois do amanhecer;
      `sets_early`   começa, mas desce abaixo da altitude mínima antes de terminar;
      `unknown`      sem coordenadas (catálogo ausente).
    """
    start, end = night_bounds(lat, lon, now)
    cursor, rows, used = start, [], 0
    for item in items:
        row = dict(item, duration_s=duration_s(item), start=None, end=None,
                   alt_start_deg=None, alt_end_deg=None, status="never_up")
        if item.get("ra_deg") is None or item.get("dec_deg") is None:
            row["status"] = "unknown"
        elif start is not None and cursor is not None:
            def alt(t, _i=item):
                return float(cat._alt_from_radec(_i["ra_deg"], _i["dec_deg"], lat, lon, t))
            t = cursor
            while t < end and alt(t) < item["min_alt_deg"]:
                t += STEP
            if t < end:
                finish = t + timedelta(seconds=row["duration_s"])
                row.update(start=t.strftime(_ISO), end=finish.strftime(_ISO),
                           alt_start_deg=round(alt(t), 1), alt_end_deg=round(alt(finish), 1))
                row["status"] = ("after_dawn" if finish > end
                                 else "sets_early" if row["alt_end_deg"] < item["min_alt_deg"] else "ok")
                used += int((min(finish, end) - t).total_seconds())
                cursor = min(finish, end)
        rows.append(row)
    night_s = int((end - start).total_seconds()) if start is not None and end is not None else 0
    return {"night": {"start": start.strftime(_ISO) if start else None,
                      "end": end.strftime(_ISO) if end else None},
            "items": rows, "total_s": sum(r["duration_s"] for r in rows),
            "free_s": max(0, night_s - used)}


def runnable(items: list[dict], lat: float, lon: float, now: datetime) -> list[dict]:
    """A fila do jeito que o Controller executa. O que não sobe nesta noite vai marcado para
    ser pulado, com o motivo — a tela da noite mostra por quê.

    O simulador roda os itens em sequência, sem esperar a hora marcada; com a câmera e a
    montagem reais, é aqui que entra a espera pelo horário de cada alvo.
    """
    planned = schedule(items, lat, lon, now)["items"]
    return [{"id": r["id"], "target": r["target"], "frames": r["frames"], "type": r["type"],
             "mosaic": r["mosaic"], "skip": "below_horizon" if r["status"] == "never_up" else None}
            for r in planned]


def mosaic(target: str, rows: int, cols: int, overlap: float, rig=cat.DEFAULT_RIG) -> dict | None:
    """A grade de um mosaico sobre um alvo do catálogo, ou None se o alvo não existe."""
    obj = sky.find(target)
    if obj is None:
        return None
    fov = rig.fov_deg()
    panels, covers = panel_grid_radec(obj.ra_deg, obj.dec_deg, rows, cols, fov, overlap)
    size = obj.size_arcmin
    return {"target": sky.target_id(obj), "name": obj.common or sky.target_id(obj),
            "rows": rows, "cols": cols, "overlap": overlap,
            "field_deg": [round(fov[0], 2), round(fov[1], 2)], "covers_deg": list(covers),
            "object_arcmin": size,
            # o eixo maior do alvo cabe no lado maior da grade, com folga de 10%? (o catálogo
            # só traz o eixo maior, sem a orientação: é uma indicação, não uma garantia)
            "covers_object": None if size is None else bool(size * 1.1 <= max(covers) * 60.0),
            "panels": panels}
