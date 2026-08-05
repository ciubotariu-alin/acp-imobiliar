"""Descărcare poze + calcul dHash. I/O izolat (urllib); motorul de dedup rămâne pur."""
from __future__ import annotations

import urllib.request
from typing import Callable

from acp.imagini import dhash
from acp.modele import Comparabila


def descarca_bytes(url: str, user_agent: str, timeout: float = 10.0) -> bytes | None:
    """Descarcă conținutul unui URL de poză. None la orice eroare."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as raspuns:
            return raspuns.read()
    except Exception:
        return None


def hashuri_din_urls(
    urls: list[str],
    user_agent: str,
    descarca: Callable[..., bytes | None] = descarca_bytes,
    max_poze: int = 4,
) -> list[int]:
    """Descarcă primele `max_poze` URL-uri și întoarce lista de dHash-uri valide."""
    hashuri: list[int] = []
    for url in urls[:max_poze]:
        octeti = descarca(url, user_agent)
        if octeti is None:
            continue
        h = dhash(octeti)
        if h is not None:
            hashuri.append(h)
    return hashuri


def construieste_fetch_poze(
    user_agent: str,
    cache=None,
    descarca: Callable[..., bytes | None] = descarca_bytes,
    max_poze: int = 4,
) -> Callable[[Comparabila], list[int]]:
    """Construiește un `fetch_poze(c)` care descarcă `c.poze_urls` → dHash-uri, cu cache pe disc."""
    def fetch_poze(c: Comparabila) -> list[int]:
        if cache is not None and c.url:
            din_cache = cache.get(c.url)
            if din_cache is not None:
                return din_cache
        hashuri = hashuri_din_urls(c.poze_urls, user_agent, descarca=descarca, max_poze=max_poze)
        if cache is not None and c.url:
            cache.set(c.url, hashuri)
        return hashuri

    return fetch_poze
