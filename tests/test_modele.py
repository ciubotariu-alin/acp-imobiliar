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
