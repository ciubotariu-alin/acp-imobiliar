import pytest

from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class StubConnector(ConnectorBase):
    """Stub connector pentru testing."""

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        return [
            Comparabila(
                sursa="stub",
                url=None,
                pret_eur=100000,
                supr_totala=70,
                etaj=5,
                an=2015,
                dotari=[],
                marcaj="activ",
                tip="vanzare",
                ajustari=[],
            )
        ]


def test_connector_base_subclass():
    """Subclasa ConnectorBase e validă."""
    connector = StubConnector(name="stub")
    criterii = CriteriiCautare(
        camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5
    )
    result = connector.search(criterii)
    assert len(result) == 1
    assert result[0].sursa == "stub"
    assert result[0].euro_mp == pytest.approx(1428.57, abs=0.1)


def test_connector_error():
    """ConnectorError e raisable."""
    with pytest.raises(ConnectorError) as exc_info:
        raise ConnectorError("timeout", connector="test")
    assert "timeout" in str(exc_info.value)
    assert exc_info.value.connector == "test"
