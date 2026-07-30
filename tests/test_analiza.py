import pytest
from acp.modele import Subiect, Comparabila, Ajustare
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
    assert a.pozitionare_pct > 0


def _comps_cu_ajustare():
    """Comparabile la care una are o ajustare semnificativă (fără parcare, spre
    deosebire de subiect), astfel încât mediana ajustată să difere clar de cea brută."""
    date = [(85000, 65, 2008), (89000, 65, 2009), (82900, 65, 2009), (87000, 65, 2010)]
    comps = [Comparabila(sursa="s", pret_eur=p, supr_totala=s, an=a) for p, s, a in date]
    # a doua comparabilă (89000 €, 65 mp → ~1369 €/mp) primește o ajustare negativă
    # mare (lipsă parcare), care îi scade €/mp ajustat sub restul grupului.
    comps[1] = comps[1].model_copy(update={
        "ajustari": [Ajustare(factor="parcare", procent=-0.15, motiv="fără parcare, spre deosebire de subiect")]
    })
    return comps


def test_verdict_foloseste_mediana_ajustata_nu_bruta():
    subiect = _subiect()
    comps = _comps_cu_ajustare()
    a = analizeaza(subiect, comps, tinta_zile=90)

    # ajustarea trebuie să schimbe efectiv mediana folosită pentru verdict
    assert a.stat_ajustat.mediana != a.stat_brut.mediana

    # poziționarea trebuie calculată față de mediana AJUSTATĂ, nu față de cea brută
    asteptat = (subiect.euro_mp - a.stat_ajustat.mediana) / a.stat_ajustat.mediana * 100
    assert a.pozitionare_pct == pytest.approx(asteptat)


def _comps_cu_outlier():
    """Cinci comparabile în jur de 1300 €/mp și una clar atipică (300 €/mp),
    suficiente (n=6 cu preț) pentru ca regula IQR să marcheze outlierul."""
    date = [(85000, 65, 2008), (87000, 79, 2009), (89000, 65, 2009),
            (82900, 65, 2009), (86000, 65, 2010)]
    comps = [Comparabila(sursa="s", pret_eur=p, supr_totala=s, an=a) for p, s, a in date]
    outlier = Comparabila(sursa="s", pret_eur=19500, supr_totala=65, an=2009)  # 300 €/mp
    return comps, outlier


def test_outlierii_sunt_expusi_dar_excluse_din_mediana():
    subiect = _subiect()
    comps, outlier = _comps_cu_outlier()
    a = analizeaza(subiect, comps + [outlier], tinta_zile=90)

    assert outlier in a.outlieri
    assert outlier not in a.comparabile
    # outlierul (300 €/mp) nu a tras mediana/minimul în jos
    assert a.stat_ajustat.minim > 300
