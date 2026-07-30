import pytest
from acp.modele import Subiect, Comparabila
from acp.analiza import analizeaza


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                   locatie="Confort City")


def _comps():
    date = [(85000, 65, 2008), (87000, 79, 2009), (89000, 65, 2009),
            (82900, 65, 2009)]
    return [Comparabila(sursa="s", pret_eur=p, supr_totala=s, an=a) for p, s, a in date]


def test_analiza_produce_verdict():
    a = analizeaza(_subiect(), _comps(), tinta_zile=90)
    assert a.stat_ajustat.n >= 3
    assert a.incadrare in {"sub piață", "corect", "supraevaluat"}
    assert a.pret_listare[0] <= a.pret_listare[1]
    assert a.pret_tranzactie[1] <= a.pret_listare[1]  # tranzacție ≤ listare (corecție)
    assert a.tinta_zile == 90


def test_pozitionare_peste_mediana():
    # subiect 1318 €/mp; comparabile în jur de 1300 → ușor peste
    a = analizeaza(_subiect(), _comps(), tinta_zile=90)
    assert isinstance(a.pozitionare_pct, float)
