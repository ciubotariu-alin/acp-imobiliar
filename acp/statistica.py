"""Statistici pe valori €/mp."""
from __future__ import annotations

import statistics

from acp.modele import Statistici


def calculeaza_statistici(valori: list[float]) -> Statistici:
    if not valori:
        raise ValueError("Lista de valori este goală — nu există comparabile cu preț.")
    ordonate = sorted(valori)
    q1 = q3 = None
    if len(ordonate) >= 4:
        quartile = statistics.quantiles(ordonate, n=4)
        q1, q3 = quartile[0], quartile[2]
    return Statistici(
        n=len(ordonate),
        minim=ordonate[0],
        mediana=statistics.median(ordonate),
        maxim=ordonate[-1],
        q1=q1,
        q3=q3,
    )
