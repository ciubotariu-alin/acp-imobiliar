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
