"""Cache pe disc pentru câmpurile parsate din paginile de detaliu."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class CacheDetalii:
    def __init__(self, dir: str = ".cache/detalii", ttl_zile: float = 1.0):
        self.dir = Path(dir)
        self.ttl_secunde = ttl_zile * 86400
        self.dir.mkdir(parents=True, exist_ok=True)

    def _cale(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, url: str) -> dict | None:
        p = self._cale(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("fetched_at", 0.0) > self.ttl_secunde:
            return None
        return data.get("campuri")

    def set(self, url: str, campuri: dict) -> None:
        payload = {"fetched_at": time.time(), "campuri": campuri}
        self._cale(url).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
