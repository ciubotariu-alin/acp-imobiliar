"""Orchestrarea analizei: filtrare → statistici → context → verdict de poziționare."""
from __future__ import annotations

from acp.modele import Subiect, Comparabila, Analiza
from acp.statistica import calculeaza_statistici
from acp.filtrare import filtreaza, dedup, marcheaza_outlieri
from acp.context import calculeaza_context


def _incadrare(pozitionare_pct: float) -> str:
    if pozitionare_pct > 5:
        return "supraevaluat"
    if pozitionare_pct < -5:
        return "sub piață"
    return "corect"


def analizeaza(subiect: Subiect, comparabile: list[Comparabila], tinta_zile: int,
               corectie: tuple[float, float] = (0.04, 0.08),
               surse: list[str] | None = None) -> Analiza:
    # randament din chirii: Plan 3
    vanzari = [c for c in comparabile if c.tip == "vanzare"]
    filtrate = filtreaza(subiect, dedup(vanzari))
    pastrate, outlieri = marcheaza_outlieri(filtrate)

    valori_brut = [c.euro_mp for c in pastrate if c.euro_mp is not None]
    valori_ajustat = [c.euro_mp_ajustat for c in pastrate if c.euro_mp_ajustat is not None]
    stat_brut = calculeaza_statistici(valori_brut)
    stat_ajustat = calculeaza_statistici(valori_ajustat)

    pozitionare_pct = (subiect.euro_mp - stat_ajustat.mediana) / stat_ajustat.mediana * 100

    # Preț de listare recomandat: bandă în jurul medianei ajustate × suprafața subiectului.
    pret_median = stat_ajustat.mediana * subiect.supr_totala
    pret_listare = (round(pret_median * 0.99, -2), round(pret_median * 1.03, -2))
    # Preț de tranzacționare: corecția anunț→tranzacție aplicată benzii de listare.
    lo, hi = corectie
    pret_tranzactie = (round(pret_listare[0] * (1 - hi), -2),
                       round(pret_listare[1] * (1 - lo), -2))

    active = [c for c in comparabile if c.tip == "vanzare" and c.marcaj == "activ"]
    context = calculeaza_context(active or vanzari)

    return Analiza(
        subiect=subiect,
        comparabile=pastrate,
        outlieri=outlieri,
        context=context,
        stat_brut=stat_brut,
        stat_ajustat=stat_ajustat,
        pozitionare_pct=pozitionare_pct,
        incadrare=_incadrare(pozitionare_pct),
        pret_listare=pret_listare,
        pret_tranzactie=pret_tranzactie,
        tinta_zile=tinta_zile,
        surse=surse or sorted({c.sursa for c in comparabile}),
    )
