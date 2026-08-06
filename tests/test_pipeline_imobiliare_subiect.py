from acp.core.pipeline import PipelineOrchestrator, _este_imobiliare
from acp.modele import Subiect, Comparabila


def test_este_imobiliare():
    assert _este_imobiliare("https://www.imobiliare.ro/oferta/x-123") is True
    assert _este_imobiliare("https://www.olx.ro/d/oferta/y.html") is False
    assert _este_imobiliare(None) is False


def _comp(sursa, url, pret, supr, etaj=2, camere=2):
    return Comparabila(sursa=sursa, url=url, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, camere=camere, tip="vanzare", an=1980)


def test_subiect_imobiliare_exclus_pe_metadata_fara_fetch_poze(monkeypatch):
    """Subiect pe imobiliare: NU se descarcă poze subiect; subiect+geamăn excluși pe metadata."""
    orch = PipelineOrchestrator()
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://www.imobiliare.ro/oferta/x-275238880")
    propriu = _comp("imobiliare.ro", "https://www.imobiliare.ro/oferta/x-275238880", 108000, 59)
    geaman = _comp("imobiliare.ro", "https://www.imobiliare.ro/oferta/y-275736626", 108000, 60)
    normal = _comp("olx.ro", "https://www.olx.ro/d/oferta/z.html", 95000, 58, etaj=7)
    comparabile = [propriu, geaman, normal]

    # dacă s-ar încerca fetch poze subiect, testul ar pica (nu trebuie apelat)
    def _boom(url, ua):
        raise AssertionError("nu trebuie descărcate poze pentru subiect imobiliare")
    monkeypatch.setattr("acp.connectors.detaliu_fetch.fetch_detaliu", _boom)
    # fetch_poze pentru comparabile (olx) nu are candidați aici → nu se apelează pe imobiliare
    monkeypatch.setattr("acp.core.pipeline.construieste_fetch_poze",
                        lambda ua, cache=None, **kw: (lambda c: []))

    analiza = orch.deduplicate_and_analyze(subiect, comparabile, imbogateste=False, dedup_poze=True)

    urls = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://www.imobiliare.ro/oferta/x-275238880" not in urls  # propriul anunț exclus
    assert "https://www.imobiliare.ro/oferta/y-275736626" not in urls  # geamănul exclus (metadata)
    assert "https://www.olx.ro/d/oferta/z.html" in urls                # normalul rămâne
