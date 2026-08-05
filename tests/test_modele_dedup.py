from acp.modele import Subiect, Comparabila


def test_subiect_are_url_optional():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2)
    assert s.url is None
    s2 = Subiect(pret_eur=108000, supr_totala=59, camere=2, url="https://x.ro/a")
    assert s2.url == "https://x.ro/a"


def test_comparabila_are_camere_si_poze():
    c = Comparabila(sursa="imobiliare.ro", supr_totala=60)
    assert c.camere is None
    assert c.poze_urls == []
    c2 = Comparabila(sursa="imobiliare.ro", supr_totala=60, camere=2,
                     poze_urls=["https://x.ro/p1.jpg"])
    assert c2.camere == 2
    assert c2.poze_urls == ["https://x.ro/p1.jpg"]


def test_poze_urls_nu_sunt_partajate_intre_instante():
    a = Comparabila(sursa="s", supr_totala=50)
    b = Comparabila(sursa="s", supr_totala=50)
    a.poze_urls.append("x")
    assert b.poze_urls == []
