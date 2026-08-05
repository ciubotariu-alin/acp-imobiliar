"""Cache pe disc pentru liste de hash-uri de poze (paralel cu CacheDetalii)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class CacheHashuri:
    def __init__(self, dir: str = ".cache/hashuri", ttl_zile: float = 1.0):
        self.dir = Path(dir)
        self.ttl_secunde = ttl_zile * 86400
        self.dir.mkdir(parents=True, exist_ok=True)

    def _cale(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, url: str) -> list[int] | None:
        p = self._cale(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("fetched_at", 0.0) > self.ttl_secunde:
            return None
        return data.get("hashuri")

    def set(self, url: str, hashuri: list[int]) -> None:
        payload = {"fetched_at": time.time(), "hashuri": hashuri}
        self._cale(url).write_text(json.dumps(payload), encoding="utf-8")
