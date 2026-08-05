"""Motor pur de îmbogățire cu detalii — fără rețea. Fetcher-ul e injectat."""
from __future__ import annotations

from typing import Callable

from acp.extractie import (
    extrage_structura, extrage_incalzire, extrage_stare,
    extrage_parcare, extrage_dotari, extrage_etaje_total,
)
from acp.modele import Comparabila


def parseaza_detaliu(text: str, an: int | None = None) -> dict:
    """Rulează toți extractorii pe textul paginii de detaliu → dict de câmpuri Comparabila."""
    stare, incredere = extrage_stare(text)
    return {
        "structura": extrage_structura(text),
        "incalzire": extrage_incalzire(text),
        "stare": stare,
        "stare_incredere": incredere,
        "parcare_tip": extrage_parcare(text, an),
        "dotari": extrage_dotari(text),
        "etaje_total": extrage_etaje_total(text),
    }


def imbogateste_detalii(
    comparabile: list[Comparabila],
    fetchers: dict[str, Callable[[str], str | None]],
    cache=None,
) -> int:
    """Îmbogățește comparabilele cu date din pagina de detaliu.

    Pentru fiecare comparabilă cu `url` și o sursă prezentă în `fetchers`:
    - încearcă cache-ul; la miss apelează fetcher-ul (text) și parsează;
    - populează câmpurile și setează `detalii_complete=True`.
    Fetch eșuat (None) sau sursă fără fetcher → sărită (detalii_complete rămâne False).
    Întoarce numărul de comparabile îmbogățite.
    """
    n = 0
    for c in comparabile:
        if not c.url or c.sursa not in fetchers:
            continue
        campuri = cache.get(c.url) if cache is not None else None
        if campuri is None:
            text = fetchers[c.sursa](c.url)
            if not text:
                continue
            campuri = parseaza_detaliu(text, c.an)
            if cache is not None:
                cache.set(c.url, campuri)
        for cheie, valoare in campuri.items():
            setattr(c, cheie, valoare)
        c.detalii_complete = True
        n += 1
    return n
