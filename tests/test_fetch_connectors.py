"""Teste pentru fetch connectors (publi24, romimo, sudrezidential, lajumate, waa2, anuntul)."""
import pytest
from unittest.mock import patch, MagicMock

from acp.connectors.fetch_connectors import (
    Publi24Connector,
    RomimoConnector,
    SudrezidentialConnector,
    LajumateConnector,
    Waa2Connector,
    AnuntulConnector,
)
from acp.modele import CriteriiCautare


@pytest.mark.parametrize(
    "connector_class, expected_name",
    [
        (Publi24Connector, "publi24.ro"),
        (RomimoConnector, "romimo.ro"),
        (SudrezidentialConnector, "sudrezidential.ro"),
        (LajumateConnector, "lajumate.ro"),
        (Waa2Connector, "waa2.com"),
        (AnuntulConnector, "anuntul.ro"),
    ],
)
def test_fetch_connector_init(connector_class, expected_name):
    """Toți fetch connectorii se inițializează."""
    connector = connector_class()
    assert connector.name == expected_name


@pytest.mark.parametrize(
    "connector_class",
    [
        Publi24Connector,
        RomimoConnector,
        SudrezidentialConnector,
        LajumateConnector,
        Waa2Connector,
        AnuntulConnector,
    ],
)
def test_fetch_search_returns_list(connector_class):
    """Search returnează list[Comparabila]."""
    connector = connector_class()
    criterii = CriteriiCautare(
        camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5
    )

    # Mock HTTP response cu placeholder HTML
    with patch('httpx.get') as mock_get:
        mock_response = MagicMock()
        mock_response.text = "<!-- placeholder HTML -->"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = connector.search(criterii)
        assert isinstance(result, list)


# ---------- RomimoConnector: parsare + post-filtrare ----------

def _romimo_card(href, titlu, ppm, pret, loc):
    return (
        '<div class="article-item">'
        f'<a href="{href}">link</a>'
        f'<div class="article-title">{titlu}</div>'
        f'<div class="article-short-info article-lbl">{ppm} EUR/m 2 |</div>'
        f'<div class="article-location">{loc}</div>'
        f'<span class="article-price">{pret} EUR</span>'
        '</div>'
    )

_H = "https://www.romimo.ro/anunturi/imobiliare/de-vanzare/apartamente/apartamente-2-camere/anunt/x/A.html"
_H_INCH = "https://www.romimo.ro/anunturi/imobiliare/de-inchiriat/apartamente/apartamente-2-camere/anunt/x/B.html"


def _crit():
    return CriteriiCautare(camere=2, supr_min=50, supr_max=80, zona="Colentina")


def test_romimo_parse_apartament_colentina_potrivit():
    conn = RomimoConnector()
    html = _romimo_card(_H, "Apartament de vanzare 2 camere zona Colentina",
                        "1328", "85 000", "Colentina, Sector 2, Bucuresti")
    r = conn._parse_html(html, _crit())
    assert len(r) == 1
    c = r[0]
    assert c.sursa == "romimo.ro"
    assert c.pret_eur == 85000.0
    assert c.supr_totala == 64.0  # 85000 / 1328 ≈ 64
    assert c.camere == 2
    assert c.url == _H


def test_romimo_parse_filtreaza_alta_zona():
    conn = RomimoConnector()
    html = _romimo_card(_H, "Apartament de vanzare 2 camere Titan",
                        "1328", "85 000", "Titan, Sector 3, Bucuresti")
    assert conn._parse_html(html, _crit()) == []


def test_romimo_parse_filtreaza_camere_gresite():
    conn = RomimoConnector()
    html = _romimo_card(_H, "Apartament de vanzare 3 camere zona Colentina",
                        "1328", "120 000", "Colentina, Sector 2, Bucuresti")
    assert conn._parse_html(html, _crit()) == []


def test_romimo_parse_exclude_inchiriere():
    conn = RomimoConnector()
    html = _romimo_card(_H_INCH, "Apartament de inchiriat 2 camere zona Colentina",
                        "10", "500", "Colentina, Sector 2, Bucuresti")
    assert conn._parse_html(html, _crit()) == []


def test_romimo_parse_filtreaza_suprafata_in_afara():
    conn = RomimoConnector()
    # 300000 / 1500 = 200mp -> în afara [50,80]
    html = _romimo_card(_H, "Apartament de vanzare 2 camere zona Colentina",
                        "1500", "300 000", "Colentina, Sector 2, Bucuresti")
    assert conn._parse_html(html, _crit()) == []


def test_romimo_parse_pret_redus_foloseste_new_price():
    conn = RomimoConnector()
    card = (
        '<div class="article-item">'
        f'<a href="{_H}">link</a>'
        '<div class="article-title">Apartament de vanzare 2 camere zona Colentina</div>'
        '<div class="article-short-info">1200 EUR/m 2 |</div>'
        '<div class="article-location">Colentina, Sector 2, Bucuresti</div>'
        '<span class="article-price"><span class="old-price">90 000 EUR</span>'
        '<span class="new-price">72 000 EUR</span></span>'
        '</div>'
    )
    r = conn._parse_html(card, _crit())
    assert len(r) == 1
    assert r[0].pret_eur == 72000.0  # prețul redus, nu cel vechi
    assert r[0].supr_totala == 60.0  # 72000 / 1200
