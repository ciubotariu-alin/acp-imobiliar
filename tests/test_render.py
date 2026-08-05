from acp.modele import (Subiect, Comparabila, ContextPiata, Statistici, Analiza)
from acp.raport.render import formateaza_eur, construieste_html, scrie_pdf


def _analiza():
    subiect = Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                      locatie="Confort City, Splaiul Unirii 9")
    comps = [Comparabila(sursa="storia", pret_eur=85000, supr_totala=65, an=2008)]
    stat = Statistici(n=4, minim=1101, mediana=1275, maxim=1369)
    return Analiza(subiect=subiect, comparabile=comps,
                   context=ContextPiata(nr_active=8, tensiune="echilibrata"),
                   stat_brut=stat, stat_ajustat=stat, pozitionare_pct=3.4,
                   incadrare="corect", pret_listare=(84000, 87000),
                   pret_tranzactie=(80000, 84000), tinta_zile=90, surse=["storia", "olx"])


def test_formateaza_eur():
    assert formateaza_eur(87000) == "87.000 €"


def test_html_contine_datele_cheie():
    html = construieste_html(_analiza())
    assert "87.000 €" in html
    assert "Confort City" in html
    assert "ANEVAR" in html  # disclaimerul fix


def test_html_comparabila_cu_url_are_link():
    subiect = Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                      locatie="Confort City")
    comps = [Comparabila(sursa="imobiliare.ro", url="https://imobiliare.ro/oferta/x-123",
                         pret_eur=85000, supr_totala=65, an=2008)]
    stat = Statistici(n=4, minim=1101, mediana=1275, maxim=1369)
    analiza = Analiza(subiect=subiect, comparabile=comps,
                      context=ContextPiata(nr_active=8, tensiune="echilibrata"),
                      stat_brut=stat, stat_ajustat=stat, pozitionare_pct=3.4,
                      incadrare="corect", pret_listare=(84000, 87000),
                      pret_tranzactie=(80000, 84000), tinta_zile=90)
    html = construieste_html(analiza)
    assert '<a href="https://imobiliare.ro/oferta/x-123">imobiliare.ro</a>' in html


def test_html_comparabila_fara_url_ramane_text():
    # fallback: comparabila fără url → numele sursei ca text simplu, fără <a>
    html = construieste_html(_analiza())  # comps din _analiza() n-au url
    assert "storia" in html
    assert "<a href" not in html


def test_scrie_pdf(tmp_path):
    cale = tmp_path / "raport.pdf"
    scrie_pdf(_analiza(), str(cale))
    date = cale.read_bytes()
    assert date[:4] == b"%PDF"
    assert len(date) > 1000
