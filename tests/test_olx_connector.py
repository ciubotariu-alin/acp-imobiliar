"""Teste pentru OlxConnector (Playwright politicos)."""
import asyncio

import pytest

from acp.connectors.base import ConnectorError
from acp.connectors.olx import OlxConnector, OlxTransientError
from acp.modele import CriteriiCautare


@pytest.fixture
def olx_html():
    """Încarc HTML salvat din olx.ro (search vânzare apartamente/garsoniere, București)."""
    from pathlib import Path

    fixture_path = Path(__file__).parent.parent / "fixtures" / "olx_search_result.html"
    if not fixture_path.exists():
        pytest.skip("Fixture olx_search_result.html nu există")
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def listing_items(olx_html):
    return OlxConnector._extract_listing_items(olx_html)


def criterii_test(**overrides):
    base = dict(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    base.update(overrides)
    return CriteriiCautare(**base)


def _item_by_id(items, listing_id):
    matches = [it for it in items if it.get("id") == listing_id]
    assert matches, f"fixtura ar trebui să conțină anunțul {listing_id}"
    return matches[0]


# ---------- Inițializare ----------

def test_olx_connector_init():
    """OlxConnector se inițializează."""
    connector = OlxConnector()
    assert connector.name == "olx.ro"


def test_olx_search_returns_list():
    """Search returnează list[Comparabila] (interfața de bază, fără rețea reală)."""
    connector = OlxConnector()

    async def fake_fetch(url):
        return "<html></html>"

    connector._fetch_html_with_retry = fake_fetch
    result = connector.search(criterii_test())
    assert isinstance(result, list)


# ---------- Construcție URL ----------

def test_build_search_url_conține_categoria_și_orașul():
    connector = OlxConnector()
    url = connector._build_search_url(criterii_test())
    assert url.startswith(
        "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-vanzare/bucuresti/"
    )


def test_build_search_url_slugifică_zona_cu_diacritice():
    connector = OlxConnector()
    url = connector._build_search_url(criterii_test(zona="Viștei"))
    assert "q-vistei" in url
    assert " " not in url


def test_build_search_url_chirie():
    connector = OlxConnector()
    url = connector._build_search_url(criterii_test(tip="chirie"))
    assert "/apartamente-garsoniere-de-inchiriat/" in url


def test_build_search_url_fara_zona_omite_segmentul():
    connector = OlxConnector()
    url_cu_zona = connector._build_search_url(criterii_test(zona="Viștei"), include_zona=True)
    url_fara_zona = connector._build_search_url(criterii_test(zona="Viștei"), include_zona=False)
    assert "q-vistei" in url_cu_zona
    assert "q-vistei" not in url_fara_zona
    assert url_fara_zona == "https://www.olx.ro/imobiliare/apartamente-garsoniere-de-vanzare/bucuresti/"


# ---------- Extragere __PRERENDERED_STATE__ ----------

def test_extract_listing_items_gaseste_anunturile_din_fixtura(olx_html):
    items = OlxConnector._extract_listing_items(olx_html)
    assert isinstance(items, list)
    assert len(items) > 0


def test_extract_listing_items_html_fara_prerendered_state_intoarce_lista_goala():
    items = OlxConnector._extract_listing_items("<html><body>pagina fara anunturi</body></html>")
    assert items == []


def test_extract_listing_items_json_malformat_nu_crapa():
    html = (
        '<html><script id="olx-init-config">'
        'window.__PRERENDERED_STATE__= "{not valid json";'
        "</script></html>"
    )
    items = OlxConnector._extract_listing_items(html)
    assert items == []


def test_extract_listing_items_json_dublu_encodat_valid():
    """Sanity check pe encoding-ul dublu (string JSON care conține el însuși JSON)."""
    import json

    inner = json.dumps({"listing": {"listing": {"ads": [{"id": 1, "title": "test"}]}}})
    outer = json.dumps(inner)
    html = f'<html><script id="olx-init-config">window.__PRERENDERED_STATE__= {outer};</script></html>'
    items = OlxConnector._extract_listing_items(html)
    assert items == [{"id": 1, "title": "test"}]


# ---------- Parsing unui anunț (_normalize_listing_to_comparabila) ----------

def test_olx_parse_listing_extrage_campurile_de_baza(listing_items):
    """Parsing-ul unui anunț din JSON real (listing.listing.ads) e corect."""
    connector = OlxConnector()
    item = _item_by_id(listing_items, 305642731)  # 2 camere, etaj 7, 70 mp, 249000 EUR
    comp = connector._normalize_listing_to_comparabila(item, tip="vanzare")

    assert comp is not None
    assert comp.sursa == "olx.ro"
    assert comp.pret_eur == pytest.approx(249000)
    assert comp.supr_totala == pytest.approx(70.0)
    assert comp.etaj == 7
    assert comp.an is None  # olx.ro expune doar un interval bucket, nu anul exact
    assert comp.url == "https://www.olx.ro/d/oferta/apartament-2-camere-calea-dorobanti-IDkGrDt.html"
    assert comp.marcaj == "activ"
    assert comp.tip == "vanzare"


def test_olx_parse_listing_parter_mapeaza_la_etaj_zero(listing_items):
    """normalizedValue='parter' trebuie mapat la etaj=0, nu None.

    Aceeași lecție ca la imobiliare.ro/storia.ro: altfel semnătura de
    deduplicare (adresă + supr + etaj + an) ar trata greșit parterul ca
    „etaj necunoscut"."""
    connector = OlxConnector()
    item = _item_by_id(listing_items, 306859053)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj == 0


def test_olx_parse_listing_demisol_mapeaza_la_etaj_minus_unu(listing_items):
    """normalizedValue='demisol' (subsol, sub parter) -> etaj=-1."""
    connector = OlxConnector()
    item = _item_by_id(listing_items, 306921460)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj == -1


def test_olx_parse_listing_fl10_ambiguu_ramane_none(listing_items):
    """normalizedValue='fl_10' ("10 și peste") nu are un etaj exact -> None."""
    connector = OlxConnector()
    item = _item_by_id(listing_items, 306385259)
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.etaj is None


def test_olx_parse_listing_accepta_json_string():
    """_normalize_listing_to_comparabila acceptă și un string JSON."""
    import json

    connector = OlxConnector()
    payload = json.dumps(
        {
            "params": [{"key": "m", "normalizedValue": "65.5"}, {"key": "floor", "normalizedValue": "fl_3"}],
            "price": {"regularPrice": {"value": 150000, "currencyCode": "EUR"}},
            "url": "https://www.olx.ro/d/oferta/test-anunt-1.html",
        }
    )
    comp = connector._normalize_listing_to_comparabila(payload)
    assert comp is not None
    assert comp.pret_eur == pytest.approx(150000)
    assert comp.supr_totala == pytest.approx(65.5)
    assert comp.etaj == 3
    assert comp.url == "https://www.olx.ro/d/oferta/test-anunt-1.html"


def test_olx_parse_listing_string_invalid_intoarce_none():
    connector = OlxConnector()
    comp = connector._normalize_listing_to_comparabila("not json")
    assert comp is None


def test_olx_parse_listing_tip_chirie_se_transmite_din_exterior():
    """Comparabila.tip vine din `tip=` (criterii.tip) — anunțurile individuale
    nu poartă un câmp explicit vanzare/chirie, vezi nota din modul."""
    connector = OlxConnector()
    item = {"params": [{"key": "m", "normalizedValue": "45"}], "price": {}}
    comp = connector._normalize_listing_to_comparabila(item, tip="chirie")
    assert comp.tip == "chirie"


def test_olx_parse_listing_fara_suprafata_returneaza_none():
    connector = OlxConnector()
    item = {"price": {"regularPrice": {"value": 150000, "currencyCode": "EUR"}}}
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp is None


def test_olx_parse_listing_fara_pret_returneaza_pret_none():
    """Un anunț fără regularPrice (ex. 'preț la cerere'/budget) tot produce o
    Comparabila, cu pret_eur=None."""
    connector = OlxConnector()
    item = {
        "params": [{"key": "m", "normalizedValue": "50"}],
        "price": {"budget": True},
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp is not None
    assert comp.pret_eur is None


def test_olx_parse_listing_moneda_non_eur_pret_none():
    """regularPrice într-o altă monedă decât EUR -> pret_eur=None (nu convertim)."""
    connector = OlxConnector()
    item = {
        "params": [{"key": "m", "normalizedValue": "50"}],
        "price": {"regularPrice": {"value": 500000, "currencyCode": "RON"}},
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp is not None
    assert comp.pret_eur is None


def test_olx_parse_listing_fara_url_sau_urlpath_url_none():
    connector = OlxConnector()
    item = {"params": [{"key": "m", "normalizedValue": "50"}]}
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.url is None


def test_olx_parse_listing_urlpath_relativ_devine_absolut():
    connector = OlxConnector()
    item = {
        "params": [{"key": "m", "normalizedValue": "50"}],
        "urlPath": "/d/oferta/test-anunt-2.html",
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert comp.url == "https://www.olx.ro/d/oferta/test-anunt-2.html"


def test_olx_parse_listing_include_compartimentare_in_dotari():
    connector = OlxConnector()
    item = {
        "params": [
            {"key": "m", "normalizedValue": "50"},
            {"key": "compartimentare", "value": "Decomandat", "normalizedValue": "decomandat"},
        ],
    }
    comp = connector._normalize_listing_to_comparabila(item)
    assert "Decomandat" in comp.dotari


# ---------- Extragere camere din titlu (_extract_camere) ----------

def test_extract_camere_numar_explicit_in_titlu():
    assert OlxConnector._extract_camere({"title": "Apartament 2 camere Calea Dorobanți"}) == 2
    assert OlxConnector._extract_camere({"title": "AP 4 camere decomandat"}) == 4


def test_extract_camere_numar_explicit_are_prioritate_peste_studio():
    """'Tip Studio' nu trebuie să suprascrie un număr explicit de camere din titlu."""
    assert (
        OlxConnector._extract_camere(
            {"title": "Apartament 2 camere Tip Studio Weiner Residence VestGroup TVA 21"}
        )
        == 2
    )


def test_extract_camere_garsoniera_mapeaza_la_unu():
    assert OlxConnector._extract_camere({"title": "Garsoniera in centrul Crangasului"}) == 1


def test_extract_camere_studio_fara_numar_mapeaza_la_unu():
    assert OlxConnector._extract_camere({"title": "Studio nou | parc privat | Militari"}) == 1


def test_extract_camere_fara_potrivire_intoarce_none():
    assert OlxConnector._extract_camere({"title": "Apartament,"}) is None
    assert OlxConnector._extract_camere({}) is None


def test_extract_camere_din_fixtura_reala(listing_items):
    item = _item_by_id(listing_items, 306920489)  # titlu nu menționează camere/garsonieră/studio
    assert OlxConnector._extract_camere(item) is None


# ---------- Search end-to-end (cu fixtura, fără Playwright real) ----------

def test_olx_search_filtrează_după_suprafață(olx_html, monkeypatch):
    """Search pe olx.ro (cu fixtura salvată, fără request HTTP real)."""
    connector = OlxConnector()

    async def fake_fetch(url):
        return olx_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=60, supr_max=80, zona="")
    result = connector.search(criterii)

    assert isinstance(result, list)
    assert len(result) > 0
    for comp in result:
        assert 60 <= comp.supr_totala <= 80
        assert comp.sursa == "olx.ro"


def test_search_filters_by_camere(olx_html, listing_items, monkeypatch):
    """criterii.camere trebuie aplicat ca filtru post-parsare (extras din
    titlu), la fel ca supr_min/supr_max — vezi contractul din
    acp/filtrare.py:13 ("Filtrarea pe număr de camere ... se face deja de
    connector") și lecția din Task 3 (storia.ro)."""
    connector = OlxConnector()

    async def fake_fetch(url):
        return olx_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    # supr_min/supr_max largi, ca să izolăm efectul filtrului de camere.
    criterii = criterii_test(camere=2, supr_min=0, supr_max=10000, zona="")
    result = connector.search(criterii)

    assert isinstance(result, list)
    assert len(result) > 0

    # Comparabila nu expune direct `camere`, deci reconstituim titlul din
    # fixtură prin URL și verificăm că fiecare rezultat are exact 2 camere.
    url_to_title = {it.get("url"): it.get("title") for it in listing_items if it.get("url")}
    for comp in result:
        assert comp.url is not None
        assert OlxConnector._extract_camere({"title": url_to_title[comp.url]}) == 2

    # Proba că filtrarea chiar exclude anunțuri: fixtura conține și anunțuri
    # cu alt număr de camere (1, 3, 4, necunoscut) — dacă filtrul ar fi
    # ignorat silențios, rezultatul ar include toată fixtura.
    assert len(result) < len(listing_items)


def test_olx_search_gol_dacă_niciun_anunț_nu_se_potrivește(olx_html, monkeypatch):
    connector = OlxConnector()

    async def fake_fetch(url):
        return olx_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=10000, supr_max=20000, zona="")
    result = connector.search(criterii)
    assert result == []


def test_olx_search_fallback_zona_necunoscuta(olx_html, monkeypatch):
    """Dacă URL-ul cu segment `q-{zona}` întoarce 0 anunțuri (termen fără
    potriviri), search trebuie să reîncerce fără segmentul de zonă și să
    întoarcă rezultatele de la nivel de oraș."""
    connector = OlxConnector()
    calls = []

    async def fake_fetch(url):
        calls.append(url)
        if "q-vistei" in url:
            return "<html><body>0 rezultate</body></html>"
        return olx_html

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch)

    criterii = criterii_test(camere=2, supr_min=60, supr_max=80, zona="Viștei")
    result = connector.search(criterii)

    assert len(calls) == 2  # prima încercare (cu zonă) + fallback (fără zonă)
    assert "q-vistei" in calls[0]
    assert "q-vistei" not in calls[1]
    assert len(result) > 0


def test_olx_search_fara_zona_nu_face_fallback(olx_html, monkeypatch):
    """Dacă zona e deja goală, nu are sens un al doilea fetch identic."""
    connector = OlxConnector()
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

def test_olx_search_ridică_connector_error_la_403(monkeypatch):
    connector = OlxConnector()

    async def fake_fetch_fail(url):
        raise ConnectorError("olx.ro a blocat requestul (403 anti-bot)", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_fail)

    with pytest.raises(ConnectorError):
        connector.search(criterii_test())


def test_olx_search_ridică_connector_error_la_timeout(monkeypatch):
    connector = OlxConnector()

    async def fake_fetch_timeout(url):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr(connector, "_fetch_html_with_retry", fake_fetch_timeout)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())
    assert exc_info.value.connector == "olx.ro"


# ---------- Rate limiting politicos ----------

def test_respect_rate_limit_așteaptă_minim_2s(monkeypatch):
    import time

    connector = OlxConnector(min_delay_seconds=2.0)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.olx.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic()  # request "abia" a avut loc
    asyncio.run(connector._respect_rate_limit())

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(2.0, abs=0.05)


def test_respect_rate_limit_nu_așteaptă_dacă_a_trecut_destul_timp(monkeypatch):
    import time

    connector = OlxConnector(min_delay_seconds=2.0)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr("acp.connectors.olx.asyncio.sleep", fake_sleep)

    connector._last_request_monotonic = time.monotonic() - 5.0  # ultimul request acum 5s
    asyncio.run(connector._respect_rate_limit())

    assert sleeps == []


# ---------- Retry (tenacity) și status-branching în _fetch_html ----------


def test_fetch_html_with_retry_reincearcă_după_erori_tranzitorii_și_reușește(monkeypatch):
    connector = OlxConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html(url):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OlxTransientError("eroare tranzitorie simulată", connector=connector.name)
        return "<html>ok</html>"

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html)

    result = asyncio.run(connector._fetch_html_with_retry("https://www.olx.ro/x"))

    assert result == "<html>ok</html>"
    assert calls["n"] == 3


def test_fetch_html_with_retry_ridică_connector_error_după_max_retries(monkeypatch):
    connector = OlxConnector(min_delay_seconds=0, max_retries=3)
    calls = {"n": 0}

    async def fake_fetch_html_always_fails(url):
        calls["n"] += 1
        raise OlxTransientError("eroare tranzitorie persistentă", connector=connector.name)

    monkeypatch.setattr(connector, "_fetch_html", fake_fetch_html_always_fails)

    with pytest.raises(ConnectorError):
        asyncio.run(connector._fetch_html_with_retry("https://www.olx.ro/x"))

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
    connector = OlxConnector(min_delay_seconds=0)
    monkeypatch.setattr("acp.connectors.olx.async_playwright", _fake_async_playwright(403))

    with pytest.raises(ConnectorError) as exc_info:
        asyncio.run(connector._fetch_html("https://www.olx.ro/x"))

    assert not isinstance(exc_info.value, OlxTransientError)


def test_fetch_html_5xx_ridică_olx_transient_error(monkeypatch):
    connector = OlxConnector(min_delay_seconds=0)
    monkeypatch.setattr("acp.connectors.olx.async_playwright", _fake_async_playwright(503))

    with pytest.raises(OlxTransientError):
        asyncio.run(connector._fetch_html("https://www.olx.ro/x"))


def test_fetch_html_status_200_întoarce_conținutul_paginii(monkeypatch):
    connector = OlxConnector(min_delay_seconds=0)
    monkeypatch.setattr(
        "acp.connectors.olx.async_playwright",
        _fake_async_playwright(200, content="<html>rezultate</html>"),
    )

    result = asyncio.run(connector._fetch_html("https://www.olx.ro/x"))

    assert result == "<html>rezultate</html>"


def test_fetch_html_404_nu_ridică_eroare_intoarce_continutul(monkeypatch):
    """404 (termen de căutare fără potriviri) nu e o eroare de conector — se
    lasă în seama fallback-ului de zonă din `_search_async` (bazat pe 0
    anunțuri parsate)."""
    connector = OlxConnector(min_delay_seconds=0)
    monkeypatch.setattr(
        "acp.connectors.olx.async_playwright",
        _fake_async_playwright(404, content="<html>not found</html>"),
    )

    result = asyncio.run(connector._fetch_html("https://www.olx.ro/x"))
    assert result == "<html>not found</html>"


# ---------- Constrângere timeout ≤30s per portal (search()) ----------


def test_search_convertește_timeout_wait_for_în_connector_error(monkeypatch):
    import acp.connectors.olx as olx_module

    connector = OlxConnector()

    async def fake_search_async(criterii):
        raise asyncio.TimeoutError("simulated overall timeout")

    monkeypatch.setattr(connector, "_search_async", fake_search_async)
    monkeypatch.setattr(olx_module, "SEARCH_TIMEOUT_SECONDS", 30)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "olx.ro"


def test_search_aplică_wait_for_cu_timeout_de_30s(monkeypatch):
    import acp.connectors.olx as olx_module

    connector = OlxConnector()
    monkeypatch.setattr(olx_module, "SEARCH_TIMEOUT_SECONDS", 0.05)

    async def fake_search_async_lent(criterii):
        await asyncio.sleep(10)
        return []

    monkeypatch.setattr(connector, "_search_async", fake_search_async_lent)

    with pytest.raises(ConnectorError) as exc_info:
        connector.search(criterii_test())

    assert exc_info.value.connector == "olx.ro"
