"""Teste pentru ImobiliareConnector (Playwright politicos)."""
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from acp.connectors.base import ConnectorError
from acp.connectors.imobiliare import ImobiliareConnector
from acp.modele import CriteriiCautare


@pytest.fixture
def imobiliare_html():
    """Încarc HTML salvat din imobiliare.ro (search 2 camere, sector 3)."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "imobiliare_search_result.html"
    if not fixture_path.exists():
        pytest.skip("Fixture imobiliare_search_result.html nu există")
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def listing_articles(imobiliare_html):
    soup = BeautifulSoup(imobiliare_html, "html.parser")
    return soup.select("article[data-listing-id]")


def criterii_test(**overrides):
    base = dict(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    base.update(overrides)
    return CriteriiCautare(**base)


# ---------- Construcție URL ----------

def test_build_search_url_conține_numarul_de_camere():
    connector = ImobiliareConnector()
    url = connector._build_search_url(criterii_test(camere=2))
    assert "2-camere" in url
    assert url.startswith("https://www.imobiliare.ro/vanzare-apartamente/")


def test_build_search_url_slugifică_zona_cu_diacritice():
    connector = ImobiliareConnector()
    url = connector._build_search_url(criterii_test(zona="Viștei"))
    assert "vistei" in url
    assert " " not in url


def test_build_search_url_chirie():
    connector = ImobiliareConnector()
    url = connector._build_search_url(criterii_test(tip="chirie"))
    assert "inchiriere-apartamente" in url


# ---------- Parsing unui anunț (_normalize_listing_to_comparabila) ----------

def test_imobiliare_parse_listing_extrage_campurile_de_baza(listing_articles):
    """Parsing-ul unui anunț din HTML real (data-* attrs) e corect."""
    connector = ImobiliareConnector()
    art = listing_articles[0]  # 3 camere, Theodor Pallady, 180290 EUR, 74.26 mp, etaj 1/10
    comp = connector._normalize_listing_to_comparabila(art)

    assert comp is not None
    assert comp.sursa == "imobiliare.ro"
    assert comp.pret_eur == pytest.approx(180290)
    assert comp.supr_totala == pytest.approx(74.26)
    assert comp.etaj == 1
    assert comp.an is None  # data-year="0" -> necunoscut
    assert comp.url is not None
    assert comp.url.startswith("https://www.imobiliare.ro/oferta/")
    assert comp.marcaj == "activ"
    assert comp.tip == "vanzare"


def test_imobiliare_parse_listing_an_cunoscut(listing_articles):
    """An de construcție valid (non-zero) e păstrat ca int."""
    connector = ImobiliareConnector()
    # al doilea anunț din fixtură are data-year="2025"
    art = listing_articles[1]
    comp = connector._normalize_listing_to_comparabila(art)
    assert comp.an == 2025


def test_imobiliare_parse_listing_fara_etaj_returnează_none(listing_articles):
    """Unele anunțuri nu au atributul de etaj în cele 4 listing-attribute spans."""
    connector = ImobiliareConnector()
    fara_etaj = [
        a for a in listing_articles if a.get("data-listing-id") == "267389809"
    ]
    assert fara_etaj, "fixtura ar trebui să conțină anunțul 267389809 (fără etaj)"
    comp = connector._normalize_listing_to_comparabila(fara_etaj[0])
    assert comp.etaj is None


def test_imobiliare_parse_listing_accepta_string_html():
    """_normalize_listing_to_comparabila acceptă și un fragment HTML (string)."""
    connector = ImobiliareConnector()
    html = (
        '<article data-listing-id="1" data-item-price="150000" data-surface="65.5" '
        'data-year="2020" data-status="sale" data-availability="available">'
        '<a href="/oferta/test-1">x</a>'
        '<span class="listing-attribute">Etaj 3 / 8</span>'
        "</article>"
    )
    comp = connector._normalize_listing_to_comparabila(html)
    assert comp.pret_eur == pytest.approx(150000)
    assert comp.supr_totala == pytest.approx(65.5)
    assert comp.etaj == 3
    assert comp.an == 2020
    assert comp.url == "https://www.imobiliare.ro/oferta/test-1"


def test_imobiliare_parse_listing_fara_suprafata_returnează_none():
    """Un articol fără data-surface nu poate fi convertit -> None (skip, nu crash)."""
    connector = ImobiliareConnector()
    html = '<article data-listing-id="2" data-item-price="150000"></article>'
    comp = connector._normalize_listing_to_comparabila(html)
    assert comp is None


# ---------- Search end-to-end (cu fixtura, fără Playwright real) ----------

def test_imobiliare_search_filtrează_după_suprafață(imobiliare_html, monkeypatch):
    """Search pe imobiliare.ro (cu fixtura salvată, fără request HTTP real)."""
    connector = ImobiliareConnector()

    async def fake_fetch(url):
        return imobiliare_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=60, supr_max=80, zona="Viștei")
    result = connector.search(criterii)

    assert isinstance(result, list)
    assert len(result) > 0
    for comp in result:
        assert 60 <= comp.supr_totala <= 80
        assert comp.sursa == "imobiliare.ro"


def test_imobiliare_search_gol_dacă_niciun_anunț_nu_se_potrivește(imobiliare_html, monkeypatch):
    connector = ImobiliareConnector()

    async def fake_fetch(url):
        return imobiliare_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=1000, supr_max=2000, zona="Viștei")
    result = connector.search(criterii)
    assert result == []


# ---------- Gestionare erori ----------

def test_imobiliare_search_ridică_connector_error_la_403(monkeypatch):
    connector = ImobiliareConnector()

    async def fake_fetch_fail(url):
        raise ConnectorError("imobiliare.ro a blocat requestul (403 anti-bot)", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_fail)

    with pytest.raises(ConnectorError):
        connector.search(criterii_test())


def test_imobiliare_search_ridică_connector_error_la_timeout(monkeypatch):
    connector = ImobiliareConnector()

    async def fake_fetch_timeout(url):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_timeout)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())
    assert exc_info.value.connector == "imobiliare.ro"


def test_imobiliare_search_gol_daca_nu_exista_anunturi(monkeypatch):
    """Pagină validă dar fără anunțuri -> listă goală, nu excepție."""
    connector = ImobiliareConnector()

    async def fake_fetch_empty(url):
        return "<html><body><div class='listing-results-container'></div></body></html>"

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_empty)

    result = connector.search(criterii_test())
    assert result == []


# ---------- Rate limiting politicos ----------

def test_respect_rate_limit_așteaptă_minim_2s(monkeypatch):
    import asyncio
    import time

    connector = ImobiliareConnector(min_delay_seconds=2.0)

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.imobiliare.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic()  # request "abia" a avut loc
    asyncio.run(connector._respect_rate_limit())

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(2.0, abs=0.05)


def test_respect_rate_limit_nu_așteaptă_dacă_a_trecut_destul_timp(monkeypatch):
    import asyncio
    import time

    connector = ImobiliareConnector(min_delay_seconds=2.0)

    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.imobiliare.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic() - 5.0  # ultimul request acum 5s
    asyncio.run(connector._respect_rate_limit())

    assert sleeps == []
