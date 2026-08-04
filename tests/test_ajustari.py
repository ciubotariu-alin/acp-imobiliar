from acp.modele import Subiect, Comparabila
from acp.ajustari import calculeaza_ajustari


def _subiect(**kw):
    baza = dict(pret_eur=100000.0, supr_totala=60.0, camere=2)
    baza.update(kw)
    return Subiect(**baza)


def _comp(**kw):
    baza = dict(sursa="test", pret_eur=100000.0, supr_totala=60.0)
    baza.update(kw)
    return Comparabila(**baza)


def _factor(ajustari, factor):
    for a in ajustari:
        if a.factor == factor:
            return a
    return None


def test_etaj_parter_comparabila_ajustata_in_sus():
    # subiect etaj intermediar (0.0), comparabila parter (-0.05) → +0.05
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=0)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert a is not None
    assert round(a.procent, 4) == 0.05


def test_etaj_unu_este_premium():
    # subiect intermediar (0.0), comparabila etaj 1 (+0.02) → -0.02
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=1)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert round(a.procent, 4) == -0.02


def test_etaj_acelasi_nivel_fara_ajustare():
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=6)  # ambele intermediare → 0
    assert _factor(calculeaza_ajustari(s, c), "etaj") is None


def test_etaj_ultimul_bloc_vechi():
    # comparabila la ultimul etaj (-0.03) vs subiect intermediar (0.0) → +0.03
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=8, etaje_total=8)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert round(a.procent, 4) == 0.03


def test_etaj_lipsa_fara_ajustare():
    s = _subiect(etaj=None)
    c = _comp(etaj=3)
    assert _factor(calculeaza_ajustari(s, c), "etaj") is None


def test_vechime_comparabila_mai_veche_ajustata_in_sus():
    s = _subiect(an=2010)
    c = _comp(an=2003)  # 7 ani mai veche → +0.07
    a = _factor(calculeaza_ajustari(s, c), "vechime")
    assert round(a.procent, 4) == 0.07


def test_vechime_plafonata_la_10_la_suta():
    s = _subiect(an=2020)
    c = _comp(an=2000)  # 20 ani → plafon +0.10
    a = _factor(calculeaza_ajustari(s, c), "vechime")
    assert round(a.procent, 4) == 0.10


def test_vechime_lipsa_fara_ajustare():
    s = _subiect(an=None)
    c = _comp(an=2000)
    assert _factor(calculeaza_ajustari(s, c), "vechime") is None


def test_marime_comparabila_mai_mare_ajustata_in_sus():
    # €/mp scade cu suprafața → comparabilă mai mare primește +
    s = _subiect(supr_totala=60.0)
    c = _comp(supr_totala=70.0)  # +10mp * 0.003 = +0.03
    a = _factor(calculeaza_ajustari(s, c), "marime")
    assert round(a.procent, 4) == 0.03


def test_marime_plafonata_la_3_la_suta():
    s = _subiect(supr_totala=60.0)
    c = _comp(supr_totala=100.0)  # +40mp * 0.003 = 0.12 → plafon 0.03
    a = _factor(calculeaza_ajustari(s, c), "marime")
    assert round(a.procent, 4) == 0.03
