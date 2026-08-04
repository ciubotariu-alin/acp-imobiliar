import pytest
from acp.modele import Subiect, Comparabila, Ajustare


def _subiect():
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


def test_subiect_euro_mp():
    assert _subiect().euro_mp == pytest.approx(1318.18, abs=0.01)


def test_comparabila_euro_mp():
    c = Comparabila(sursa="storia", url=None, pret_eur=89000, supr_totala=65,
                    etaj=None, an=2009, dotari=[], marcaj="activ", tip="vanzare",
                    ajustari=[])
    assert c.euro_mp == pytest.approx(1369.23, abs=0.01)


def test_comparabila_pret_ajustat():
    c = Comparabila(sursa="storia", url=None, pret_eur=89000, supr_totala=65,
                    etaj=None, an=2009, dotari=[], marcaj="activ", tip="vanzare",
                    ajustari=[Ajustare(factor="parcare", procent=-0.034,
                                       motiv="are parcare inclusă, subiectul nu")])
    assert c.pret_ajustat == pytest.approx(85974.0, abs=1.0)
    assert c.euro_mp_ajustat == pytest.approx(1322.68, abs=0.1)


def test_comparabila_fara_pret():
    c = Comparabila(sursa="sudrez", url=None, pret_eur=None, supr_totala=65,
                    etaj=10, an=2008, dotari=[], marcaj="listat", tip="vanzare",
                    ajustari=[])
    assert c.euro_mp is None
    assert c.pret_ajustat is None


def test_ajustare_suporta_procent_si_absolut():
    a = Ajustare(factor="parcare", valoare_abs=8000.0, motiv="parcare owned")
    assert a.procent == 0.0
    assert a.valoare_abs == 8000.0


def test_pret_ajustat_combina_procent_si_absolut():
    c = Comparabila(
        sursa="test", pret_eur=100000.0, supr_totala=50.0,
        ajustari=[
            Ajustare(factor="etaj", procent=0.05, motiv="etaj"),
            Ajustare(factor="parcare", valoare_abs=8000.0, motiv="parcare"),
        ],
    )
    # 100000 * (1 + 0.05) + 8000 = 113000
    assert c.pret_ajustat == 113000.0
    assert c.euro_mp_ajustat == 113000.0 / 50.0


def test_comparabila_campuri_noi_default():
    c = Comparabila(sursa="test", pret_eur=90000.0, supr_totala=60.0)
    assert c.etaje_total is None
    assert c.structura is None
    assert c.incalzire is None
    assert c.stare is None
    assert c.stare_incredere == 0.0
    assert c.parcare_tip is None
    assert c.ajustare_neta_mare is False


def test_pret_ajustat_none_cand_lipseste_pretul():
    c = Comparabila(sursa="test", pret_eur=None, supr_totala=60.0,
                    ajustari=[Ajustare(factor="etaj", procent=0.05, motiv="x")])
    assert c.pret_ajustat is None
    assert c.euro_mp_ajustat is None


def test_comparabila_detalii_complete_default_false():
    c = Comparabila(sursa="test", pret_eur=90000.0, supr_totala=60.0)
    assert c.detalii_complete is False
