"""Registro de auditoria: quem comandou o quê, e quando. Fica na Jetson, uma linha JSON por
evento. Nunca recebe segredo, token nem prova de pareamento — só o nome do celular e a ação.
"""
from __future__ import annotations

import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 1_000_000          # passou disto, o arquivo atual vira ".1" e começa outro


class AuditLog:
    def __init__(self, path: Path | str | None = None, keep: int = 200, now=None):
        self.path = Path(path) if path else None       # None = só em memória (testes)
        self._recent: deque[dict] = deque(maxlen=keep)
        self._lock = threading.Lock()
        self._now = now or (lambda: datetime.now(timezone.utc))

    def record(self, who: str, action: str, **detail) -> dict:
        entry = {"utc": self._now().strftime("%Y-%m-%dT%H:%M:%SZ"), "who": who, "action": action}
        if detail:
            entry["detail"] = detail
        with self._lock:
            self._recent.append(entry)
            if self.path is not None:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    if self.path.exists() and self.path.stat().st_size > MAX_BYTES:
                        os.replace(self.path, self.path.with_suffix(self.path.suffix + ".1"))
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                except OSError:
                    pass                               # disco cheio não pode derrubar um comando
        return entry

    def recent(self, limit: int = 50) -> list[dict]:
        with self._lock:
            return list(self._recent)[-max(1, min(int(limit), self._recent.maxlen)):][::-1]
