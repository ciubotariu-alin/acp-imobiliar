import pytest

from acp.modele import Subiect, Comparabila, Ajustare
from acp.filtrare import filtreaza, dedup, marcheaza_outlieri


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009, locatie="Confort City")


def _comp(pret, supr, an=2009, etaj=None, sursa="storia"):
    return Comparabila(sursa=sursa, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, an=an, dotari=[])


def test_filtreaza_dupa_suprafata():
    comps = [_comp(85000, 65), _comp(85900, 86)]  # 86mp = +30% > 20%
    rezultat = filtreaza(_subiect(), comps)
    suprafete = {c.supr_totala for c in rezultat}
    assert 65 in suprafete and 86 not in suprafete


def test_filtreaza_dupa_vechime():
    comps = [_comp(85000, 65, an=2009), _comp(85000, 65, an=1985)]
    rezultat = filtreaza(_subiect(), comps)
    ani = {c.an for c in rezultat}
    assert 2009 in ani and 1985 not in ani


def test_dedup_elimina_duplicate():
    a = _comp(85000, 65, etaj=10, an=2008, sursa="storia")
    b = _comp(85000, 65, etaj=10, an=2008, sursa="olx")  # aceeași proprietate, alt portal
    c = _comp(89000, 65, etaj=3, an=2009, sursa="publi24")
    rezultat = dedup([a, b, c])
    assert len(rezultat) == 2


def test_marcheaza_outlieri():
    comps = [_comp(p * 65 / 1000, 65) for p in [1101, 1275, 1308, 1369, 300]]
    pastrate, outlieri = marcheaza_outlieri(comps)
    assert len(outlieri) == 1
    assert outlieri[0].euro_mp < 500


def test_marcheaza_outlieri_foloseste_baza_ajustata():
    """marcheaza_outlieri trebuie să evalueze IQR pe euro_mp_ajustat, nu pe euro_mp brut.

    Grup normal (fără ajustări): 1101, 1275, 1308, 1369 €/mp -> bandă ~[902, 1548].

    - `ieftin_brut_dar_ajustat_normal`: brut 500 €/mp (outlier brut, sub bandă), dar
      ajustările (etaj bun + o corecție suplimentară) îi ridică €/mp ajustat la 1300,
      în bandă -> trebuie PĂSTRAT (nu marcat outlier).
    - `normal_brut_dar_ajustat_extrem`: brut 1300 €/mp (normal, în bandă), dar
      ajustările (parter + o corecție suplimentară, ambele negative) îi coboară
      €/mp ajustat la 325, sub bandă -> trebuie MARCAT outlier.
    """
    supr = 65
    grup_normal = [_comp(p * supr, supr) for p in [1101, 1275, 1308, 1369]]

    ieftin_brut_dar_ajustat_normal = Comparabila(
        sursa="storia", pret_eur=500 * supr, supr_totala=supr, dotari=[],
        ajustari=[
            Ajustare(factor="etaj", procent=0.05, motiv="etaj foarte căutat"),
            Ajustare(factor="corectie_test", procent=1.55,
                     motiv="ajustare artificială mare, doar pt izolarea testului"),
        ],
    )
    assert ieftin_brut_dar_ajustat_normal.euro_mp == 500
    assert ieftin_brut_dar_ajustat_normal.euro_mp_ajustat == pytest.approx(1300)

    normal_brut_dar_ajustat_extrem = Comparabila(
        sursa="storia", pret_eur=1300 * supr, supr_totala=supr, dotari=[],
        ajustari=[
            Ajustare(factor="etaj", procent=-0.05, motiv="parter"),
            Ajustare(factor="corectie_test", procent=-0.70,
                     motiv="ajustare artificială mare, doar pt izolarea testului"),
        ],
    )
    assert normal_brut_dar_ajustat_extrem.euro_mp == 1300
    assert normal_brut_dar_ajustat_extrem.euro_mp_ajustat == pytest.approx(325)

    comps = grup_normal + [ieftin_brut_dar_ajustat_normal, normal_brut_dar_ajustat_extrem]
    pastrate, outlieri = marcheaza_outlieri(comps)

    assert ieftin_brut_dar_ajustat_normal in pastrate
    assert ieftin_brut_dar_ajustat_normal not in outlieri
    assert normal_brut_dar_ajustat_extrem in outlieri
    assert normal_brut_dar_ajustat_extrem not in pastrate
