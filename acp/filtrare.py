"""Filtrare comparabilitate, deduplicare și detectare outlieri."""
from __future__ import annotations

import statistics

from acp.modele import Subiect, Comparabila


def filtreaza(subiect: Subiect, comps: list[Comparabila],
              prag_supr: float = 0.20, prag_an: int = 5) -> list[Comparabila]:
    """Păstrează comparabilele apropiate ca suprafață (±prag_supr) și vechime (±prag_an ani).

    Filtrarea pe număr de camere și zonă se face deja de connector la momentul căutării;
    aici rafinăm pe suprafață și vechime față de subiect.
    """
    supr_min = subiect.supr_totala * (1 - prag_supr)
    supr_max = subiect.supr_totala * (1 + prag_supr)
    rezultat = []
    for c in comps:
        if not (supr_min <= c.supr_totala <= supr_max):
            continue
        if subiect.an is not None and c.an is not None and abs(c.an - subiect.an) > prag_an:
            continue
        rezultat.append(c)
    return rezultat


def _semnatura(c: Comparabila) -> tuple:
    """Semnătură pentru deduplicare cross-portal: aceleași caracteristici fizice + preț."""
    return (round(c.supr_totala), c.etaj, c.an, round(c.pret_eur) if c.pret_eur else None)


def dedup(comps: list[Comparabila]) -> list[Comparabila]:
    vazute: dict[tuple, Comparabila] = {}
    for c in comps:
        cheie = _semnatura(c)
        if cheie not in vazute:
            vazute[cheie] = c
    return list(vazute.values())


def marcheaza_outlieri(comps: list[Comparabila], k: float = 1.5
                       ) -> tuple[list[Comparabila], list[Comparabila]]:
    """Separă outlierii după regula IQR pe €/mp AJUSTAT (doar cei cu preț).

    Cele fără preț (euro_mp_ajustat None) rămân în 'pastrate'. Se folosește baza
    ajustată (nu brută) pentru că o comparabilă poate fi atipică brut dar normală
    după ajustările de etaj/vechime/stare etc. — sau invers.
    """
    cu_pret = [c for c in comps if c.euro_mp_ajustat is not None]
    fara_pret = [c for c in comps if c.euro_mp_ajustat is None]
    if len(cu_pret) < 4:
        return comps, []
    valori = sorted(c.euro_mp_ajustat for c in cu_pret)
    q = statistics.quantiles(valori, n=4, method='inclusive')
    q1, q3 = q[0], q[2]
    iqr = q3 - q1
    jos, sus = q1 - k * iqr, q3 + k * iqr
    pastrate, outlieri = list(fara_pret), []
    for c in cu_pret:
        (outlieri if not (jos <= c.euro_mp_ajustat <= sus) else pastrate).append(c)
    return pastrate, outlieri
