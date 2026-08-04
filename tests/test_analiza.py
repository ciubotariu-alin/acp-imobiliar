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
    assert a.pozitionare_pct > 0


def _comps_cu_ajustare():
    """Comparabile care diferă de subiect (66mp, an 2009) ca suprafață și vechime,
    astfel încât `aplica_ajustari` le calculează ajustări reale (marime, vechime)
    neuniforme între ele -> mediana ajustată diferă clar de cea brută.

    Toate au 65mp (vs subiectul 66mp) -> ajustare "marime" mică, uniformă. Anii
    diferă însă vs subiectul (2008, 2009, 2009, 2010) -> ajustare "vechime"
    pozitivă pentru comparabila mai veche, negativă pentru cea mai nouă, ceea ce
    schimbă poziția relativă a comparabilelor și deci mediana."""
    date = [(85000, 65, 2008), (89000, 65, 2009), (82900, 65, 2009), (87000, 65, 2010)]
    return [Comparabila(sursa="s", pret_eur=p, supr_totala=s, an=a) for p, s, a in date]


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


def test_analizeaza_populeaza_ajustari_si_difera_de_brut():
    subiect = Subiect(pret_eur=100000.0, supr_totala=60.0, camere=2,
                      an=2010, etaj=5, etaje_total=10)
    # comparabile care diferă de subiect ca an/etaj → ajustări nenule
    comparabile = [
        Comparabila(sursa="a", pret_eur=95000.0, supr_totala=60.0, an=2000, etaj=0, marcaj="activ"),
        Comparabila(sursa="b", pret_eur=98000.0, supr_totala=62.0, an=2004, etaj=1, marcaj="activ"),
        Comparabila(sursa="c", pret_eur=102000.0, supr_totala=58.0, an=2008, etaj=3, marcaj="activ"),
        Comparabila(sursa="d", pret_eur=100000.0, supr_totala=61.0, an=2012, etaj=6, marcaj="activ"),
    ]
    analiza = analizeaza(subiect, comparabile, tinta_zile=90)
    # cel puțin o comparabilă păstrată are ajustări nenule
    assert any(len(c.ajustari) > 0 for c in analiza.comparabile)
    # mediana ajustată diferă de cea brută (ajustările au efect)
    assert analiza.stat_ajustat.mediana != analiza.stat_brut.mediana
