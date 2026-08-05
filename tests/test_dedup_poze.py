from acp.dedup_poze import (
    sunt_candidat_duplicat, potrivire_metadata_subiect, confirma_si_dedup,
)
from acp.modele import Subiect, Comparabila


def _c(sursa, pret, supr, etaj=2, camere=2, poze=None):
    return Comparabila(sursa=sursa, pret_eur=pret, supr_totala=supr, etaj=etaj,
                       camere=camere, poze_urls=poze or [])


# ---- pre-filtru metadata ----

def test_candidat_pe_praguri():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 108500, 60)  # +0,46% pret, +1mp
    assert sunt_candidat_duplicat(a, b) is True


def test_nu_candidat_pret_prea_diferit():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 120000, 60)  # +11%
    assert sunt_candidat_duplicat(a, b) is False


def test_nu_candidat_etaj_diferit():
    a = _c("imobiliare.ro", 108000, 59, etaj=2)
    b = _c("storia.ro", 108000, 59, etaj=5)
    assert sunt_candidat_duplicat(a, b) is False


def test_nu_candidat_suprafata_prea_diferita():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 108000, 63)  # +4mp
    assert sunt_candidat_duplicat(a, b) is False


def test_camere_necunoscute_nu_blocheaza():
    a = _c("imobiliare.ro", 108000, 59, camere=None)
    b = _c("storia.ro", 108000, 60, camere=2)
    assert sunt_candidat_duplicat(a, b) is True


def test_potrivire_subiect_pe_praguri():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    c = _c("storia.ro", 108000, 60, etaj=2, camere=2)
    assert potrivire_metadata_subiect(s, c) is True


def test_potrivire_subiect_esueaza_etaj():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    c = _c("storia.ro", 108000, 60, etaj=4, camere=2)
    assert potrivire_metadata_subiect(s, c) is False


# ---- confirmare + dedup (fetch_poze injectat, fără rețea) ----

def _fetch_din_dict(mapping):
    def _fetch(c):
        return mapping.get(c.url, [])
    return _fetch


def test_doua_candidate_cu_hash_comun_una_eliminata():
    a = _c("imobiliare.ro", 108000, 59); a.url = "a"
    b = _c("storia.ro", 108000, 60); b.url = "b"
    subiect = Subiect(pret_eur=999999, supr_totala=200, camere=5, etaj=9)  # nu se potrivește
    fetch = _fetch_din_dict({"a": [111], "b": [111]})  # aceeași poză
    pastrate, dup, subj = confirma_si_dedup([a, b], subiect, [], fetch)
    assert len(pastrate) == 1 and pastrate[0] is a
    assert dup == [b]
    assert subj == []


def test_doua_candidate_fara_hash_comun_ambele_pastrate():
    a = _c("imobiliare.ro", 108000, 59); a.url = "a"
    b = _c("storia.ro", 108000, 60); b.url = "b"
    subiect = Subiect(pret_eur=999999, supr_totala=200, camere=5, etaj=9)
    fetch = _fetch_din_dict({"a": [111], "b": [999999999]})  # poze diferite
    pastrate, dup, subj = confirma_si_dedup([a, b], subiect, [], fetch)
    assert set(id(x) for x in pastrate) == {id(a), id(b)}
    assert dup == []


def test_comparabila_cu_hash_de_subiect_e_eliminata():
    a = _c("imobiliare.ro", 108000, 59, etaj=2, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    fetch = _fetch_din_dict({"a": [111]})
    pastrate, dup, subj = confirma_si_dedup([a], subiect, [111], fetch)
    assert pastrate == []
    assert subj == [a]


def test_comparabila_fara_grup_candidat_neatinsa_fara_fetch():
    a = _c("imobiliare.ro", 90000, 50, etaj=1, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=200000, supr_totala=90, camere=4, etaj=9)

    def _fetch_boom(c):
        raise AssertionError("fetch_poze nu trebuia apelat pentru non-candidat")

    pastrate, dup, subj = confirma_si_dedup([a], subiect, [111], _fetch_boom)
    assert pastrate == [a]
    assert dup == [] and subj == []


def test_fallback_fara_subiect_hashes_exclude_pe_metadata():
    a = _c("imobiliare.ro", 108000, 59, etaj=2, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)

    def _fetch_boom(c):
        raise AssertionError("fara subiect_hashes nu descarcam poze pentru excludere")

    pastrate, dup, subj = confirma_si_dedup([a], subiect, [], _fetch_boom)
    assert subj == [a]
    assert pastrate == []


def test_url_esuat_fara_fallback_pastreaza_comparabila():
    a = _c("imobiliare.ro", 108000, 59, etaj=2, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)

    def _fetch_boom(c):
        raise AssertionError("nu descarcam poze cand fallback e dezactivat si nu avem hash-uri")

    pastrate, dup, subj = confirma_si_dedup(
        [a], subiect, [], _fetch_boom, fallback_metadata_subiect=False
    )
    assert subj == []
    assert pastrate == [a]
