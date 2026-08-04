"""Motor de ajustare a prețului comparabilelor la nivelul subiectului.

Direcția: subiect − comparabila. Comparabila inferioară → ajustare pozitivă.
"""
from __future__ import annotations

from acp.modele import Subiect, Comparabila, Ajustare

CAP_ETAJ = 0.05
CAP_VECHIME = 0.10
CAP_MARIME = 0.03


def _plafon(x: float, cap: float) -> float:
    return max(-cap, min(cap, x))


def _nivel_etaj(etaj: int | None, etaje_total: int | None) -> float | None:
    """Valoarea de nivel a etajului (curbă, nu liniar). None dacă etaj necunoscut."""
    if etaj is None:
        return None
    if etaj == 0:
        return -0.05          # parter
    if etaj == 1:
        return 0.02           # cel mai căutat
    if etaj in (2, 3):
        return 0.01
    if etaje_total is not None and etaj >= 4 and etaj == etaje_total:
        return -0.03          # ultimul etaj
    return 0.0                # intermediar (baseline)


def _ajustare_etaj(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    ns = _nivel_etaj(subiect.etaj, subiect.etaje_total)
    nc = _nivel_etaj(comp.etaj, comp.etaje_total)
    if ns is None or nc is None:
        return None
    procent = _plafon(ns - nc, CAP_ETAJ)
    if procent == 0:
        return None
    return Ajustare(factor="etaj", procent=procent,
                    motiv=f"Etaj {comp.etaj} vs subiect {subiect.etaj}")


def _ajustare_vechime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if subiect.an is None or comp.an is None:
        return None
    procent = _plafon((subiect.an - comp.an) * 0.01, CAP_VECHIME)
    if procent == 0:
        return None
    return Ajustare(factor="vechime", procent=procent,
                    motiv=f"An {comp.an} vs subiect {subiect.an}")


def _ajustare_marime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    procent = _plafon((comp.supr_totala - subiect.supr_totala) * 0.003, CAP_MARIME)
    if procent == 0:
        return None
    return Ajustare(factor="marime", procent=procent,
                    motiv=f"{comp.supr_totala}mp vs subiect {subiect.supr_totala}mp")


def calculeaza_ajustari(subiect: Subiect, comparabila: Comparabila,
                        valoare_parcare_eur: float = 8000.0,
                        valoare_boxa_eur: float = 2000.0) -> list[Ajustare]:
    candidati = [
        _ajustare_etaj(subiect, comparabila),
        _ajustare_vechime(subiect, comparabila),
        _ajustare_marime(subiect, comparabila),
    ]
    return [a for a in candidati if a is not None]
