from acp.detalii import parseaza_detaliu, imbogateste_detalii
from acp.modele import Comparabila


def _c(sursa="imobiliare.ro", url="https://imobiliare.ro/x", an=2015):
    return Comparabila(sursa=sursa, pret_eur=90000.0, supr_totala=60.0, url=url, an=an)


def test_imbogateste_populeaza_si_seteaza_flag():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: "structură beton, mobilat, garaj subteran"}
    n = imbogateste_detalii([c], fetchers)
    assert n == 1
    assert c.detalii_complete is True
    assert c.structura == "beton"
    assert "mobilat" in c.dotari
    assert c.parcare_tip == "owned"


def test_imbogateste_fetch_esuat_lasa_flag_false():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: None}
    n = imbogateste_detalii([c], fetchers)
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_sursa_fara_fetcher_sarita():
    c = _c(sursa="publi24.ro")
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: "beton"})
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_fara_url_sarita():
    c = _c(url=None)
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: "beton"})
    assert n == 0


def test_imbogateste_foloseste_cache_evita_fetch(tmp_path):
    from acp.cache_detalii import CacheDetalii
    cache = CacheDetalii(dir=str(tmp_path / "d"))
    c = _c()
    cache.set(c.url, {"structura": "caramida", "incalzire": None, "stare": None,
                      "stare_incredere": 0.0, "parcare_tip": None, "dotari": [],
                      "etaje_total": None})

    def _raise(url):
        raise AssertionError("fetcher nu trebuia apelat (cache hit)")

    n = imbogateste_detalii([c], {"imobiliare.ro": _raise}, cache=cache)
    assert n == 1
    assert c.structura == "caramida"
    assert c.detalii_complete is True


def test_parseaza_detaliu_extrage_toate_campurile():
    text = (
        "Apartament renovat, structură beton, centrală proprie, mobilat, "
        "aer condiționat, balcon. Garaj subteran inclus. Regim înălțime: P+8E"
    )
    d = parseaza_detaliu(text, an=2015)
    assert d["structura"] == "beton"
    assert d["incalzire"] == "centrala_proprie"
    assert d["stare"] == "renovat"
    assert d["stare_incredere"] > 0.5
    assert d["parcare_tip"] == "owned"
    assert "mobilat" in d["dotari"]
    assert "balcon" in d["dotari"]
    assert d["etaje_total"] == 8


def test_parseaza_detaliu_camp_necunoscut_none():
    d = parseaza_detaliu("apartament 2 camere", an=None)
    assert d["structura"] is None
    assert d["stare"] is None
    assert d["dotari"] == []
    assert d["etaje_total"] is None
