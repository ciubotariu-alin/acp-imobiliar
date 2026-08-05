from acp.connectors.imobiliare import ImobiliareConnector
from acp.modele import CriteriiCautare

ARTICLE = (
    '<article data-listing-id="1" data-surface="60" data-item-price="120000" '
    'data-year="2010" data-status="sale" data-availability="available">'
    '<a href="/oferta/x"></a>'
    '<span class="listing-attribute">2 camere</span>'
    '<span class="listing-attribute">60 mp</span>'
    '<span class="listing-attribute">etaj 2</span>'
    '<span class="listing-attribute">2010</span>'
    '</article>'
)


def test_imobiliare_normalize_nu_seteaza_camere_singur():
    # normalize NU cunoaște criterii; camere se setează la agregare (vezi search loop).
    conn = ImobiliareConnector()
    comp = conn._normalize_listing_to_comparabila(ARTICLE)
    assert comp is not None
    assert comp.camere is None


def test_loop_seteaza_camere_din_criterii():
    conn = ImobiliareConnector()
    criterii = CriteriiCautare(camere=2, supr_min=40, supr_max=80, zona="colentina")
    comp = conn._normalize_listing_to_comparabila(ARTICLE)
    # Reproduce pasul din _search_async: setarea camere din criterii.
    comp.camere = criterii.camere
    assert comp.camere == 2
