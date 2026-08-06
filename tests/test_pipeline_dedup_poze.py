from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, Comparabila


def _comp(sursa, url, pret, supr, etaj=2, camere=2):
    return Comparabila(sursa=sursa, url=url, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, camere=camere, tip="vanzare", an=1980)


def test_dedup_poze_elimina_subiect_si_duplicat(monkeypatch):
    orch = PipelineOrchestrator()
    # domeniu non-imobiliare: testul verifică ramura pe poze (fetch + hash)
    # (imobiliare.ro nu mai declanseaza fetch — vezi test_pipeline_imobiliare_subiect.py)
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://storia.ro/subiect")

    # subiectul (propriul anunț) + geamănul lui la altă agenție + un anunț normal
    prop = _comp("storia.ro", "https://storia.ro/subiect", 108000, 59)
    geaman = _comp("storia.ro", "https://storia.ro/geaman", 108000, 60)
    normal = _comp("olx.ro", "https://olx.ro/normal", 95000, 58)
    comparabile = [prop, geaman, normal]

    # fără rețea: nu îmbogățim (poze_urls setate manual), dar rulăm dedup_poze
    prop.poze_urls = ["https://cdn/p1.jpg"]
    geaman.poze_urls = ["https://cdn/p1b.jpg"]
    normal.poze_urls = ["https://cdn/n1.jpg"]

    # subiectul are aceleași poze ca prop și geaman (hash 111); normal are 999
    def _fake_fetch_detaliu(url, user_agent):
        return "text", ["https://cdn/subiect.jpg"]
    monkeypatch.setattr(
        "acp.connectors.detaliu_fetch.fetch_detaliu", _fake_fetch_detaliu
    )

    def _fake_hashuri_din_urls(urls, user_agent, **kw):
        return [111]  # hash-ul subiectului
    monkeypatch.setattr("acp.core.pipeline.hashuri_din_urls", _fake_hashuri_din_urls)

    hash_map = {
        "https://storia.ro/subiect": [111],
        "https://storia.ro/geaman": [111],
        "https://olx.ro/normal": [999999],
    }

    def _fake_construieste_fetch_poze(user_agent, cache=None, **kw):
        def _fetch(c):
            return hash_map.get(c.url, [])
        return _fetch
    monkeypatch.setattr(
        "acp.core.pipeline.construieste_fetch_poze", _fake_construieste_fetch_poze
    )

    analiza = orch.deduplicate_and_analyze(
        subiect, comparabile, imbogateste=False, dedup_poze=True
    )

    urls_ramase = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://storia.ro/subiect" not in urls_ramase  # subiect exclus
    assert "https://storia.ro/geaman" not in urls_ramase   # duplicat/subiect exclus
    assert "https://olx.ro/normal" in urls_ramase          # normalul rămâne


def test_dedup_poze_url_esuat_nu_exclude_agresiv(monkeypatch):
    orch = PipelineOrchestrator()
    # domeniu non-imobiliare: testul verifică ramura "url dat, fetch poze esuat"
    # (imobiliare.ro nu mai declanseaza fetch — vezi test_pipeline_imobiliare_subiect.py)
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://storia.ro/subiect")

    # comparabila care se potriveste pe metadata cu subiectul
    potrivita = _comp("storia.ro", "https://storia.ro/potrivita", 108000, 60)
    normal = _comp("olx.ro", "https://olx.ro/normal", 95000, 58)
    comparabile = [potrivita, normal]

    # fără rețea: nu îmbogățim (poze_urls setate manual)
    potrivita.poze_urls = ["https://cdn/p1b.jpg"]
    normal.poze_urls = ["https://cdn/n1.jpg"]

    # fetch-ul pozelor subiectului esueaza (Playwright/Cloudflare) -> (None, [])
    def _fake_fetch_detaliu(url, user_agent):
        return None, []
    monkeypatch.setattr(
        "acp.connectors.detaliu_fetch.fetch_detaliu", _fake_fetch_detaliu
    )

    def _fake_hashuri_din_urls(urls, user_agent, **kw):
        return []  # nimic de descarcat, urls e gol
    monkeypatch.setattr("acp.core.pipeline.hashuri_din_urls", _fake_hashuri_din_urls)

    def _fake_construieste_fetch_poze(user_agent, cache=None, **kw):
        def _fetch(c):
            raise AssertionError("nu ar trebui sa descarcam poze pentru comparabila pastrata")
        return _fetch
    monkeypatch.setattr(
        "acp.core.pipeline.construieste_fetch_poze", _fake_construieste_fetch_poze
    )

    analiza = orch.deduplicate_and_analyze(
        subiect, comparabile, imbogateste=False, dedup_poze=True
    )

    urls_ramase = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://storia.ro/potrivita" in urls_ramase  # NU exclus agresiv pe metadata
    assert "https://olx.ro/normal" in urls_ramase


def test_dedup_poze_dezactivat_pastreaza_tot(monkeypatch):
    orch = PipelineOrchestrator()
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://imobiliare.ro/subiect")
    prop = _comp("imobiliare.ro", "https://imobiliare.ro/subiect", 108000, 59)
    normal = _comp("olx.ro", "https://olx.ro/normal", 95000, 58)
    analiza = orch.deduplicate_and_analyze(
        subiect, [prop, normal], imbogateste=False, dedup_poze=False
    )
    urls = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://imobiliare.ro/subiect" in urls
