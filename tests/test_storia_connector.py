"""Teste pentru StoriaConnector (Playwright politicos)."""
import asyncio
import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from acp.connectors.base import ConnectorError
from acp.connectors.storia import StoriaConnector, StoriaTransientError
from acp.modele import CriteriiCautare


@pytest.fixture
def storia_html():
    """Încarc HTML salvat din storia.ro (search vânzare apartamente, sector 3)."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "storia_search_result.html"
    if not fixture_path.exists():
        pytest.skip("Fixture storia_search_result.html nu există")
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def listing_items(storia_html):
    soup = BeautifulSoup(storia_html, "html.parser")
    tag = soup.find("script", id="__NEXT_DATA__")
    data = json.loads(tag.string)
    return data["props"]["pageProps"]["data"]["searchAds"]["items"]


def criterii_test(**overrides):
    base = dict(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    base.update(overrides)
    return CriteriiCautare(**base)


def _item_by_id(items, listing_id):
    matches = [it for it in items if it.get("id") == listing_id]
    assert matches, f"fixtura ar trebui să conțină anunțul {listing_id}"
    return matches[0]


# ---------- Inițializare ----------

def test_storia_connector_init():
    """StoriaConnector se inițializează."""
    connector = StoriaConnector()
    assert connector.name == "storia.ro"


def test_storia_search_returns_list():
    """Search returnează list[Comparabila] (interfața de bază, fără rețea reală)."""
    connector = StoriaConnector()

    async def fake_fetch(url):
        return "<html></html>"

    connector._fetch_html_with_retry = fake_fetch
    result = connector.search(criterii_test())
    assert isinstance(result, list)


# ---------- Construcție URL ----------

def test_build_search_url_conține_tipul_de_tranzacție_și_orașul():
    connector = StoriaConnector()
    url = connector._build_search_url(criterii_test())
    assert url.startswith("https://www.storia.ro/ro/rezultate/vanzare/apartament/bucuresti")


def test_build_search_url_slugifică_zona_cu_diacritice():
    connector = StoriaConnector()
    url = connector._build_search_url(criterii_test(zona="Viștei"))
    assert "vistei" in url
    assert " " not in url


def test_build_search_url_chirie():
    connector = StoriaConnector()
    url = connector._build_search_url(criterii_test(tip="chirie"))
    assert "/inchiriere/apartament/" in url


def test_build_search_url_fara_zona_omite_segmentul():
    connector = StoriaConnector()
    url_cu_zona = connector._build_search_url(criterii_test(zona="Viștei"), include_zona=True)
    url_fara_zona = connector._build_search_url(criterii_test(zona="Viștei"), include_zona=False)
    assert "vistei" in url_cu_zona
    assert "vistei" not in url_fara_zona
    assert url_fara_zona == "https://www.storia.ro/ro/rezultate/vanzare/apartament/bucuresti"


# ---------- Extragere __NEXT_DATA__ ----------

def test_extract_listing_items_gaseste_anunturile_din_fixtura(storia_html):
    items = StoriaConnector._extract_listing_items(storia_html)
    assert isinstance(items, list)
    assert len(items) > 0


def test_extract_listing_items_html_fara_next_data_intoarce_lista_goala():
    items = StoriaConnector._extract_listing_items("<html><body>pagina 404</body></html>")
    assert items == []


def test_extract_listing_items_json_malformat_nu_crapa():
    html = '<html><script id="__NEXT_DATA__">{not valid json</script></html>'
    items = StoriaConnector._extract_listing_items(html)
    assert items == []


# ---------- Parsing unui anunț (_normalize_listing_to_comparabila) ----------

def test_storia_parse_listing_extrage_campurile_de_baza(listing_items):
    """Parsing-ul unui anunț din JSON real (searchAds.items) e corect."""
    connector = StoriaConnector()
    item = _item_by_id(listing_items, 10447634)  # 2 camere, etaj 1, 65.21 mp, 86777 EUR
    comp = connector._normalize_listing_to_comparabila(item)

    assert comp is not None
    assert comp.sursa == "storia.ro"
    assert comp.pret_eur == pytest.approx(86777)
    assert comp.supr_totala == pytest.approx(65.21)
    assert comp.etaj == 1
    assert comp.an is None  # storia.ro nu expune anul de construcție în JSON-ul de căutare
    assert comp.url == (
        "https://www.storia.ro/ro/oferta/"
        "apartament-2-camere-decomandat-pallady-oferta-parcare-comision-0-IDHPUe"
    )
    assert comp.marcaj == "activ"
    assert comp.tip == "vanzare"
    assert "SECURE_BUILDING" in comp.dotari


def test_storia_parse_listing_ground_mapeaza_la_etaj_zero(listing_items):
    """floorNumber='GROUND' (parter) trebuie mapat la etaj=0, nu None.

    Aceeași lecție ca la imobiliare.ro: altfel semnătura de deduplicare
    (adresă + supr + etaj + an) ar trata greșit parterul ca „etaj necunoscut".
    """
    connector = StoriaConnector()
    item = _item_by_id(listing_items, 10504496)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj == 0


def test_storia_parse_listing_ground_al_doilea_caz(listing_items):
    connector = StoriaConnector()
    item = _item_by_id(listing_items, 10328312)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj == 0


def test_storia_parse_listing_above_tenth_ramane_none(listing_items):
    """floorNumber='ABOVE_TENTH' nu are un etaj exact -> None (nu ghicim greșit)."""
    connector = StoriaConnector()
    item = _item_by_id(listing_items, 10238484)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj is None


def test_storia_parse_listing_accepta_json_string():
    """_normalize_listing_to_comparabila acceptă și un string JSON."""
    connector = StoriaConnector()
    payload = json.dumps(
        {
            "areaInSquareMeters": 65.5,
            "floorNumber": "THIRD",
            "totalPrice": {"value": 150000, "currency": "EUR"},
            "transaction": "SELL",
            "slug": "test-anunt-1",
            "tags": [],
        }
    )
    comp = connector._normalize_listing_to_comparabila(payload)
    assert comp is not None
    assert comp.pret_eur == pytest.approx(150000)
    assert comp.supr_totala == pytest.approx(65.5)
    assert comp.etaj == 3
    assert comp.url == "https://www.storia.ro/ro/oferta/test-anunt-1"


def test_storia_parse_listing_string_invalid_intoarce_none():
    connector = StoriaConnector()
    comp = connector._normalize_listing_to_comparabila("not json")
    assert comp is None


def test_storia_parse_listing_transaction_rent_mapeaza_la_chirie():
    """Comparabila.tip trebuie să folosească vocabularul modelului: 'vanzare' | 'chirie'."""
    connector = StoriaConnector()
    item = {
        "areaInSquareMeters": 45,
        "floorNumber": "SECOND",
        "totalPrice": {"value": 500, "currency": "EUR"},
        "transaction": "RENT",
        "slug": "test-chirie",
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.tip == "chirie"


def test_storia_parse_listing_fara_suprafata_returnează_none():
    connector = StoriaConnector()
    item = {"totalPrice": {"value": 150000}, "slug": "fara-suprafata"}
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp is None


def test_storia_parse_listing_fara_pret_returnează_pret_none():
    """Un anunț fără preț (hidePrice) tot produce o Comparabila, cu pret_eur=None."""
    connector = StoriaConnector()
    item = {
        "areaInSquareMeters": 50,
        "floorNumber": "FIRST",
        "totalPrice": None,
        "transaction": "SELL",
        "slug": "fara-pret",
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp is not None
    assert comp.pret_eur is None


def test_storia_parse_listing_fara_slug_url_none():
    connector = StoriaConnector()
    item = {"areaInSquareMeters": 50, "floorNumber": "FIRST", "totalPrice": {"value": 1000}}
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.url is None


# ---------- Search end-to-end (cu fixtura, fără Playwright real) ----------

def test_storia_search_filtrează_după_suprafață(storia_html, monkeypatch):
    """Search pe storia.ro (cu fixtura salvată, fără request HTTP real)."""
    connector = StoriaConnector()

    async def fake_fetch(url):
        return storia_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=60, supr_max=80, zona="Sectorul 3")
    result = connector.search(criterii)

    assert isinstance(result, list)
    assert len(result) > 0
    for comp in result:
        assert 60 <= comp.supr_totala <= 80
        assert comp.sursa == "storia.ro"


def test_search_filters_by_camere(storia_html, listing_items, monkeypatch):
    """criterii.camere trebuie aplicat ca filtru post-parsare (roomsNumber),
    la fel ca supr_min/supr_max — vezi contractul din acp/filtrare.py:13
    ("Filtrarea pe număr de camere ... se face deja de connector")."""
    connector = StoriaConnector()

    async def fake_fetch(url):
        return storia_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    # supr_min/supr_max largi, ca să izolăm efectul filtrului de camere.
    criterii = criterii_test(camere=2, supr_min=0, supr_max=1000, zona="Sectorul 3")
    result = connector.search(criterii)

    assert isinstance(result, list)
    assert len(result) > 0

    # Comparabila nu expune direct `camere`, deci reconstituim roomsNumber
    # din fixtură prin slug (extras din URL-ul anunțului) și verificăm că
    # se mapează la exact 2 camere.
    slug_to_rooms = {
        item.get("slug"): item.get("roomsNumber") for item in listing_items if item.get("slug")
    }
    for comp in result:
        assert comp.url is not None
        slug = comp.url.rsplit("/", 1)[-1]
        assert StoriaConnector._extract_camere({"roomsNumber": slug_to_rooms[slug]}) == 2

    # Proba că filtrarea chiar exclude anunțuri: fixtura conține și anunțuri
    # cu alt număr de camere (ex. THREE, ONE) — dacă filtrul ar fi ignorat
    # silențios, rezultatul ar include toată fixtura.
    assert len(result) < len(listing_items)


def test_storia_search_gol_dacă_niciun_anunț_nu_se_potrivește(storia_html, monkeypatch):
    connector = StoriaConnector()

    async def fake_fetch(url):
        return storia_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=1000, supr_max=2000, zona="Sectorul 3")
    result = connector.search(criterii)
    assert result == []


def test_storia_search_fallback_zona_necunoscuta(storia_html, monkeypatch):
    """Dacă URL-ul cu zonă întoarce 0 anunțuri (zonă neacceptată de taxonomia
    storia.ro), search trebuie să reîncerce fără segmentul de zonă și să
    întoarcă rezultatele de la nivel de oraș."""
    connector = StoriaConnector()
    calls = []

    async def fake_fetch(url):
        calls.append(url)
        if "vistei" in url:
            return "<html><body>pagina 404, fara anunturi</body></html>"
        return storia_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=60, supr_max=80, zona="Viștei")
    result = connector.search(criterii)

    assert len(calls) == 2  # prima încercare (cu zonă) + fallback (fără zonă)
    assert "vistei" in calls[0]
    assert "vistei" not in calls[1]
    assert len(result) > 0


def test_storia_search_fara_zona_nu_face_fallback(storia_html, monkeypatch):
    """Dacă zona e deja goală, nu are sens un al doilea fetch identic."""
    connector = StoriaConnector()
    calls = []

    async def fake_fetch(url):
        calls.append(url)
        return "<html><body>fara anunturi</body></html>"

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(zona="")
    result = connector.search(criterii)

    assert len(calls) == 1
    assert result == []


# ---------- Gestionare erori ----------

def test_storia_search_ridică_connector_error_la_403(monkeypatch):
    connector = StoriaConnector()

    async def fake_fetch_fail(url):
        raise ConnectorError("storia.ro a blocat requestul (403 anti-bot)", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_fail)

    with pytest.raises(ConnectorError):
        connector.search(criterii_test())


def test_storia_search_ridică_connector_error_la_timeout(monkeypatch):
    connector = StoriaConnector()

    async def fake_fetch_timeout(url):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_timeout)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())
    assert exc_info.value.connector == "storia.ro"


# ---------- Rate limiting politicos ----------

def test_respect_rate_limit_așteaptă_minim_2s(monkeypatch):
    import time

    connector = StoriaConnector(min_delay_seconds=2.0)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.storia.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic()  # request "abia" a avut loc
    asyncio.run(connector._respect_rate_limit())

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(2.0, abs=0.05)


def test_respect_rate_limit_nu_așteaptă_dacă_a_trecut_destul_timp(monkeypatch):
    import time

    connector = StoriaConnector(min_delay_seconds=2.0)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.storia.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic() - 5.0  # ultimul request acum 5s
    asyncio.run(connector._respect_rate_limit())

    assert sleeps == []


# ---------- Retry (tenacity) și status-branching în _fetch_html ----------


def test_fetch_html_with_retry_reincearcă_după_erori_tranzitorii_și_reușește(monkeypatch):
    connector = StoriaConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html(url):
        calls["n"] += 1
        if calls["n"] < 3:
            raise StoriaTransientError("eroare tranzitorie simulată", connector=connector.name)
        return "<html>ok</html>"

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html)

    result = asyncio.run(connector._fetch_html_with_retry("https://www.storia.ro/x"))

    assert result == "<html>ok</html>"
    assert calls["n"] == 3


def test_fetch_html_with_retry_ridică_connector_error_după_max_retries(monkeypatch):
    connector = StoriaConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html_always_fails(url):
        calls["n"] += 1
        raise StoriaTransientError("eroare tranzitorie persistentă", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html_always_fails)

    with pytest.raises(ConnectorError):
        asyncio.run(connector._fetch_html_with_retry("https://www.storia.ro/x"))

    assert calls["n"] == connector.max_retries


class _FakeResponse:
    def __init__(self, status: int):
        self.status = status


class _FakePage:
    def __init__(self, status: int, content: str):
        self._status = status
        self._content = content

    async def goto(self, url, timeout=None, wait_until=None):
        return _FakeResponse(self._status)

    async def content(self):
        return self._content


class _FakeContext:
    def __init__(self, status: int, content: str):
        self._status = status
        self._content = content

    async def new_page(self):
        return _FakePage(self._status, self._content)


class _FakeBrowser:
    def __init__(self, status: int, content: str):
        self._status = status
        self._content = content
        self.closed = False

    async def new_context(self, **kwargs):
        return _FakeContext(self._status, self._content)

    async def close(self):
        self.closed = True


class _FakeChromium:
    def __init__(self, status: int, content: str):
        self._status = status
        self._content = content

    async def launch(self, headless=True):
        return _FakeBrowser(self._status, self._content)


class _FakePlaywrightManager:
    def __init__(self, status: int, content: str):
        self.chromium = _FakeChromium(status, content)


class _FakePlaywrightContextManager:
    def __init__(self, status: int, content: str):
        self._status = status
        self._content = content

    async def __aenter__(self):
        return _FakePlaywrightManager(self._status, self._content)

    async def __aexit__(self, *exc_info):
        return False


def _fake_async_playwright(status: int, content: str = "<html>ok</html>"):
    def factory():
        return _FakePlaywrightContextManager(status, content)

    return factory


def test_fetch_html_403_ridică_connector_error_nu_transient(monkeypatch):
    connector = StoriaConnector(min_delay_seconds=0)
    monkeypatch.setattr("acp.connectors.storia.async_playwright", _fake_async_playwright(403))

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(connector._fetch_html("https://www.storia.ro/x"))

    assert not isinstance(exc_info.value, StoriaTransientError)


def test_fetch_html_5xx_ridică_storia_transient_error(monkeypatch):
    connector = StoriaConnector(min_delay_seconds=0)
    monkeypatch.setattr("acp.connectors.storia.async_playwright", _fake_async_playwright(503))

    with pytest.raises(StoriaTransientError):
        asyncio.run(connector._fetch_html("https://www.storia.ro/x"))


def test_fetch_html_status_200_întoarce_conținutul_paginii(monkeypatch):
    connector = StoriaConnector(min_delay_seconds=0)
    monkeypatch.setattr(
        "acp.connectors.storia.async_playwright",
        _fake_async_playwright(200, content="<html>rezultate</html>"),
    )

    result = asyncio.run(connector._fetch_html("https://www.storia.ro/x"))

    assert result == "<html>rezultate</html>"


def test_fetch_html_404_nu_ridică_eroare_intoarce_continutul(monkeypatch):
    """404 (zonă necunoscută) nu e o eroare de conector — se lasă în seama
    fallback-ului de zonă din `_search_async` (bazat pe 0 anunțuri parsate)."""
    connector = StoriaConnector(min_delay_seconds=0)
    monkeypatch.setattr(
        "acp.connectors.storia.async_playwright",
        _fake_async_playwright(404, content="<html>not found</html>"),
    )

    result = asyncio.run(connector._fetch_html("https://www.storia.ro/x"))
    assert result == "<html>not found</html>"


# ---------- Constrângere timeout ≤30s per portal (search()) ----------


def test_search_convertește_timeout_wait_for_în_connector_error(monkeypatch):
    import acp.connectors.storia as storia_module

    connector = StoriaConnector()

    async def fake_search_async(criterii):
        raise asyncio.TimeoutError("simulated overall timeout")

    monkeypatch.setattr(connector, "_search_async", fake_search_async)
    monkeypatch.setattr(storia_module, "SEARCH_TIMEOUT_SECONDS", 30)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "storia.ro"


def test_search_aplică_wait_for_cu_timeout_de_30s(monkeypatch):
    import acp.connectors.storia as storia_module

    connector = StoriaConnector()
    monkeypatch.setattr(storia_module, "SEARCH_TIMEOUT_SECONDS", 0.05)

    async def fake_search_async_lent(criterii):
        await asyncio.sleep(10)
        return []

    monkeypatch.setattr(connector, "_search_async", fake_search_async_lent)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "storia.ro"
