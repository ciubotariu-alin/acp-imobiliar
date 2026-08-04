"""Motor pur de îmbogățire cu detalii — fără rețea. Fetcher-ul e injectat."""
from __future__ import annotations

from acp.extractie import (
    extrage_structura, extrage_incalzire, extrage_stare,
    extrage_parcare, extrage_dotari, extrage_etaje_total,
)


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
