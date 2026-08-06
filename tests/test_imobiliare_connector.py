"""Teste pentru ImobiliareConnector (Playwright politicos)."""
import asyncio
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from acp.connectors.base import ConnectorError
from acp.connectors.imobiliare import ImobiliareConnector, ImobiliareTransientError
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


def test_imobiliare_parse_listing_parter_mapează_la_etaj_zero(listing_articles):
    """Anunțurile cu 'Parter / N' (nu 'Etaj N') trebuie mapate la etaj=0, nu None.

    Altfel semnătura de deduplicare (adresă + supr + etaj + an) tratează greșit
    parterul ca „etaj necunoscut", ceea ce poate fuziona incorect anunțuri distincte.
    """
    connector = ImobiliareConnector()
    parter = [a for a in listing_articles if a.get("data-listing-id") == "267389809"]
    assert parter, "fixtura ar trebui să conțină anunțul 267389809 (Parter / 11)"
    comp = connector._normalize_listing_to_comparabila(parter[0])
    assert comp.etaj == 0


def test_imobiliare_parse_listing_parter_al_doilea_caz(listing_articles):
    """Al doilea anunț cu 'Parter' din fixtură (204163666) e mapat la fel la 0."""
    connector = ImobiliareConnector()
    parter = [a for a in listing_articles if a.get("data-listing-id") == "204163666"]
    assert parter, "fixtura ar trebui să conțină anunțul 204163666 (Parter / 11)"
    comp = connector._normalize_listing_to_comparabila(parter[0])
    assert comp.etaj == 0


def test_imobiliare_parse_listing_fara_niciun_span_de_etaj_returnează_none():
    """Dacă niciun span .listing-attribute nu conține text de etaj ('Etaj N' sau
    'Parter'), _extract_etaj rămâne defensiv și întoarce None (nu crash)."""
    connector = ImobiliareConnector()
    html = (
        '<article data-listing-id="9" data-item-price="150000" data-surface="65.5" '
        'data-year="2020" data-status="sale" data-availability="available">'
        '<a href="/oferta/test-9">x</a>'
        '<span class="listing-attribute">2 camere</span>'
        '<span class="listing-attribute">65,5 mp</span>'
        "</article>"
    )
    comp = connector._normalize_listing_to_comparabila(html)
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


def test_imobiliare_parse_listing_status_rent_mapează_la_chirie():
    """Comparabila.tip trebuie să folosească vocabularul modelului: 'vanzare' | 'chirie'."""
    connector = ImobiliareConnector()
    html = (
        '<article data-listing-id="3" data-item-price="500" data-surface="45" '
        'data-year="2018" data-status="rent" data-availability="available">'
        '<a href="/oferta/test-3">x</a>'
        "</article>"
    )
    comp = connector._normalize_listing_to_comparabila(html)
    assert comp.tip == "chirie"


def test_imobiliare_parse_listing_fara_suprafata_returnează_none():
    """Un articol fără data-surface nu poate fi convertit -> None (skip, nu crash)."""
    connector = ImobiliareConnector()
    html = '<article data-listing-id="2" data-item-price="150000"></article>'
    comp = connector._normalize_listing_to_comparabila(html)
    assert comp is None


def test_imobiliare_parse_listing_populeaza_campuri_noi_din_text():
    """structura/incalzire/stare/parcare_tip se extrag din textul vizibil al elementului."""
    connector = ImobiliareConnector()
    html = (
        '<article data-listing-id="10" data-item-price="90000" data-surface="60" '
        'data-year="2015" data-status="sale" data-availability="available">'
        '<a href="/oferta/test-10">x</a>'
        "Apartament renovat, centrala proprie, caramida, garaj subteran"
        "</article>"
    )
    comp = connector._normalize_listing_to_comparabila(html)
    assert comp.structura == "caramida"
    assert comp.incalzire == "centrala_proprie"
    assert comp.stare == "renovat"
    assert comp.stare_incredere == pytest.approx(0.7)
    assert comp.parcare_tip == "owned"


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


# ---------- Retry (tenacity) și status-branching în _fetch_html ----------
#
# Testele de mai sus mock-uiesc `_fetch_html_with_retry` direct, ceea ce
# ocolește complet logica de retry (tenacity) și branching-ul pe cod de
# status din `_fetch_html`. Testele de aici mock-uiesc un nivel mai jos —
# `_fetch_html` (pentru retry) și lanțul Playwright fals (pentru branching)
# — ca să exercite efectiv codul real.


def test_fetch_html_with_retry_reincearcă_după_erori_tranzitorii_și_reușește(monkeypatch):
    """_fetch_html_with_retry trebuie să reîncerce (tenacity) pe ImobiliareTransientError
    și să întoarcă rezultatul de îndată ce o încercare reușește."""
    connector = ImobiliareConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html(url):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ImobiliareTransientError("eroare tranzitorie simulată", connector=connector.name)
        return "<html>ok</html>"

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html)

    result = asyncio.run(connector._fetch_html_with_retry("https://www.imobiliare.ro/x"))

    assert result == "<html>ok</html>"
    assert calls["n"] == 3  # a eșuat de 2 ori, a reușit a 3-a oară


def test_fetch_html_with_retry_ridică_connector_error_după_max_retries(monkeypatch):
    """Dacă _fetch_html eșuează cu ImobiliareTransientError la fiecare încercare,
    dincolo de max_retries, tenacity trebuie să propage (reraise) eroarea —
    care e deja un ConnectorError (ImobiliareTransientError e subclasă)."""
    connector = ImobiliareConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html_always_fails(url):
        calls["n"] += 1
        raise ImobiliareTransientError("eroare tranzitorie persistentă", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html_always_fails)

    with pytest.raises(ConnectorError):
        asyncio.run(connector._fetch_html_with_retry("https://www.imobiliare.ro/x"))

    assert calls["n"] == connector.max_retries  # exact max_retries încercări, nu mai mult


# ---------- Constrângere timeout ≤30s per portal (search()) ----------


def test_search_convertește_timeout_wait_for_în_connector_error(monkeypatch):
    """search() trebuie să respecte constrângerea de ≤30s per portal din spec:
    dacă _search_async depășește SEARCH_TIMEOUT_SECONDS, asyncio.wait_for
    ridică asyncio.TimeoutError, iar search() trebuie să-l convertească
    într-un ConnectorError (nu să-l lase să scape necontrolat)."""
    import acp.connectors.imobiliare as imobiliare_module

    connector = ImobiliareConnector()

    async def fake_search_async(criterii):
        raise asyncio.TimeoutError("simulated overall timeout")

    monkeypatch.setattr(connector, "_search_async", fake_search_async)
    # Nu mai depindem de scurgerea reală a 30s: testăm doar conversia excepției.
    monkeypatch.setattr(imobiliare_module, "SEARCH_TIMEOUT_SECONDS", 30)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "imobiliare.ro"


def test_search_aplică_wait_for_cu_timeout_de_30s(monkeypatch):
    """search() trebuie să oprească efectiv un _search_async care nu se
    termină la timp — verificăm cu un timeout foarte mic că wait_for chiar
    întrerupe execuția, în loc să aștepte la nesfârșit."""
    import acp.connectors.imobiliare as imobiliare_module

    connector = ImobiliareConnector()
    # Timeout foarte mic ca testul să ruleze rapid, dar suficient să dovedească
    # că asyncio.wait_for(...) chiar limitează execuția lui _search_async.
    monkeypatch.setattr(imobiliare_module, "SEARCH_TIMEOUT_SECONDS", 0.05)

    async def fake_search_async_lent(criterii):
        await asyncio.sleep(10)  # mult mai lent decât timeout-ul de mai sus
        return []

    monkeypatch.setattr(connector, "_search_async", fake_search_async_lent)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "imobiliare.ro"


# ---------- Chrome real (Task 2) ----------


def test_search_ridica_connector_error_daca_chrome_indisponibil(monkeypatch):
    """Fără Google Chrome real, search ridică ConnectorError (orchestratorul continuă)."""
    from acp.connectors import real_chrome
    monkeypatch.setattr(real_chrome, "chrome_disponibil", lambda: False)
    connector = ImobiliareConnector(min_delay_seconds=0)
    crit = CriteriiCautare(camere=2, supr_min=40, supr_max=80, zona="colentina")
    with pytest.raises(ConnectorError):
        connector.search(crit)


def test_fetch_html_mapeaza_esecul_real_chrome_la_connector_error(monkeypatch):
    """Dacă real_chrome eșuează (challenge nerezolvat), _fetch_html ridică ConnectorError."""
    from acp.connectors import real_chrome

    async def _boom(url, user_agent, **kw):
        raise RuntimeError("Cloudflare challenge nerezolvat")
    monkeypatch.setattr(real_chrome, "fetch_html_async", _boom)
    connector = ImobiliareConnector(min_delay_seconds=0)
    with pytest.raises(ConnectorError):
        asyncio.run(connector._fetch_html("https://www.imobiliare.ro/x"))
