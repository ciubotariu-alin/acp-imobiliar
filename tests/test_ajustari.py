from acp.modele import Subiect, Comparabila
from acp.ajustari import calculeaza_ajustari, aplica_ajustari


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


def test_parcare_owned_subiect_comparabila_fara():
    s = _subiect(parcare="garaj subteran propriu", an=2015)
    c = _comp(parcare_tip="none")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a is not None
    assert a.valoare_abs == 8000.0


def test_parcare_resedinta_nu_produce_ajustare():
    # subiect fără parcare owned, comparabila reședință → fără capital
    s = _subiect(parcare=None)
    c = _comp(parcare_tip="resedinta")
    assert _factor(calculeaza_ajustari(s, c), "parcare") is None


def test_parcare_comparabila_owned_subiect_fara():
    s = _subiect(parcare=None)
    c = _comp(parcare_tip="owned")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a.valoare_abs == -8000.0


def test_boxa_pe_diferenta_dotari():
    s = _subiect(dotari=["boxă", "AC"])
    c = _comp(dotari=["AC"])
    a = _factor(calculeaza_ajustari(s, c, valoare_boxa_eur=2000.0), "boxa")
    assert a.valoare_abs == 2000.0


def test_mobilat_procent():
    s = _subiect(dotari=["mobilat", "utilat"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "mobilat")
    assert round(a.procent, 4) == 0.04


def test_ac_pe_numar_de_unitati_plafonat():
    s = _subiect(dotari=["aer condiționat", "aer condiționat", "aer condiționat", "aer condiționat"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "ac")
    # 4 unități * 0.01 = 0.04 → plafon 0.03
    assert round(a.procent, 4) == 0.03


def test_balcon_procent():
    s = _subiect(dotari=["balcon"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "balcon")
    assert round(a.procent, 4) == 0.03


def test_structura_caramida_vs_panou():
    s = _subiect(structura="caramida")
    c = _comp(structura="panou")
    a = _factor(calculeaza_ajustari(s, c), "structura")
    # 0.02 - (-0.03) = 0.05
    assert round(a.procent, 4) == 0.05


def test_structura_necunoscuta_fara_ajustare():
    s = _subiect(structura=None)
    c = _comp(structura="panou")
    assert _factor(calculeaza_ajustari(s, c), "structura") is None


def test_incalzire_centrala_proprie_vs_termoficare():
    s = _subiect(incalzire="centrala_proprie")
    c = _comp(incalzire="termoficare")
    a = _factor(calculeaza_ajustari(s, c), "incalzire")
    # 0.03 - (-0.02) = 0.05
    assert round(a.procent, 4) == 0.05


def test_stare_aplicata_doar_peste_prag_incredere():
    s = _subiect(stare="renovat")
    c_slab = _comp(stare="necesita_renovare", stare_incredere=0.4)  # sub prag
    assert _factor(calculeaza_ajustari(s, c_slab), "stare") is None
    c_bun = _comp(stare="necesita_renovare", stare_incredere=0.8)   # peste prag
    a = _factor(calculeaza_ajustari(s, c_bun), "stare")
    # 0.10 - (-0.15) = 0.25 → plafon 0.15
    assert round(a.procent, 4) == 0.15


def test_parcare_subiect_owned_vs_comp_resedinta_ajusteaza_in_sus():
    # subiect cu parcare owned, comparabila doar reședință (zero capital) → comp inferior → +8000
    s = _subiect(parcare="garaj subteran propriu", an=2015)
    c = _comp(parcare_tip="resedinta")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a is not None
    assert a.valoare_abs == 8000.0


def test_parcare_subiect_resedinta_vs_comp_owned_ajusteaza_in_jos():
    # subiect doar reședința (zero capital), comparabila owned → comp superior → -8000
    s = _subiect(parcare="loc de reședință închiriat de la primărie", an=1985)
    c = _comp(parcare_tip="owned")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a is not None
    assert a.valoare_abs == -8000.0


def test_parcare_ambele_resedinta_fara_ajustare():
    # ambele reședința → niciun activ de capital de comparat → fără ajustare
    s = _subiect(parcare="loc de reședința", an=1985)
    c = _comp(parcare_tip="resedinta")
    assert _factor(calculeaza_ajustari(s, c), "parcare") is None


def test_aplica_populeaza_ajustari_pe_comparabile():
    s = _subiect(an=2010, etaj=5, etaje_total=10)
    c = _comp(an=2003, etaj=0, pret_eur=100000.0, supr_totala=60.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert len(excluse) == 0
    assert len(pastrate[0].ajustari) >= 2  # vechime + etaj
    assert pastrate[0].pret_ajustat != pastrate[0].pret_eur


def test_garda_exclude_comparabila_supra_ajustata():
    # brut > 0.25: vechime +0.10 (plafon) + stare +0.15 (plafon) = 0.25 brut ...
    # adăugăm și mărime +0.03 → brut = 0.28 > 0.25 → exclusă
    s = _subiect(an=2025, supr_totala=60.0, stare="renovat")
    c = _comp(an=2000, supr_totala=80.0, stare="necesita_renovare",
              stare_incredere=0.9, pret_eur=100000.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(excluse) == 1
    assert len(pastrate) == 0


def test_garda_marcheaza_ajustare_neta_mare_dar_pastreaza():
    # net > 0.15 dar brut <= 0.25: vechime +0.10 + etaj +0.05 = net 0.15 brut 0.15
    # facem net 0.16: vechime +0.10, structura +0.05 (caramida vs panou), balcon +0.03 = 0.18
    s = _subiect(an=2020, structura="caramida", dotari=["balcon"])
    c = _comp(an=2010, structura="panou", dotari=[], pret_eur=100000.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert pastrate[0].ajustare_neta_mare is True


def test_garda_ignora_comparabila_fara_pret():
    s = _subiect(an=2010)
    c = _comp(an=2000, pret_eur=None)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert pastrate[0].ajustare_neta_mare is False
