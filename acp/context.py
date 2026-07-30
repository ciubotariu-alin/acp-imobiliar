"""Context de piață: oferta curentă și tensiunea (cine domină negocierea)."""
from __future__ import annotations

import statistics

from acp.modele import Comparabila, ContextPiata


def calculeaza_context(active: list[Comparabila], prag_putin: int = 5, prag_mult: int = 15,
                       days_on_market: list[float] | None = None,
                       nr_cu_reduceri: int | None = None) -> ContextPiata:
    n = len(active)
    if n <= prag_putin:
        tensiune = "piata_vanzatorului"
    elif n >= prag_mult:
        tensiune = "piata_cumparatorului"
    else:
        tensiune = "echilibrata"
    dom_med = statistics.mean(days_on_market) if days_on_market else None
    return ContextPiata(
        nr_active=n,
        days_on_market_med=dom_med,
        nr_cu_reduceri=nr_cu_reduceri,
        tensiune=tensiune,
    )
