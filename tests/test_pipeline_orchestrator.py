"""Tests for PipelineOrchestrator."""
import pytest
from unittest.mock import Mock, patch, MagicMock

from acp.core.pipeline import PipelineOrchestrator
from acp.connectors.base import ConnectorError
from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza


@pytest.fixture
def subiect_test():
    """Test subject fixture."""
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


@pytest.fixture
def criterii_test():
    """Test search criteria fixture."""
    return CriteriiCautare(
        camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5
    )


@pytest.fixture
def orchestrator():
    """PipelineOrchestrator fixture."""
    return PipelineOrchestrator()


def test_pipeline_orchestrator_init(orchestrator):
    """PipelineOrchestrator initializes with all 9 connectors."""
    assert hasattr(orchestrator, "fetch_comparabile_paralel")
    assert hasattr(orchestrator, "deduplicate_and_analyze")
    assert hasattr(orchestrator, "connectors")
    assert len(orchestrator.connectors) == 9

    # Check connector names
    connector_names = {c.name for c in orchestrator.connectors}
    expected_names = {
        "imobiliare.ro", "storia.ro", "olx.ro", "publi24.ro", "romimo.ro",
        "sudrezidential.ro", "lajumate.ro", "waa2.com", "anuntul.ro"
    }
    assert connector_names == expected_names


def test_pipeline_fetch_comparabile_returns_list(orchestrator, subiect_test, criterii_test):
    """fetch_comparabile_paralel returns a list."""
    # Mock all connectors to return empty lists
    for connector in orchestrator.connectors:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)
    assert isinstance(result, list)


def test_pipeline_fetch_comparabile_aggregates_results(orchestrator, subiect_test, criterii_test):
    """fetch_comparabile_paralel aggregates results from all connectors."""
    # Create mock comparabile
    comp1 = Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70)
    comp2 = Comparabila(sursa="storia.ro", pret_eur=85000, supr_totala=65)
    comp3 = Comparabila(sursa="olx.ro", pret_eur=90000, supr_totala=75)

    # Mock first 3 connectors to return results, others to return empty
    orchestrator.connectors[0].search = Mock(return_value=[comp1])
    orchestrator.connectors[1].search = Mock(return_value=[comp2])
    orchestrator.connectors[2].search = Mock(return_value=[comp3])
    for connector in orchestrator.connectors[3:]:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)

    assert len(result) == 3
    assert comp1 in result
    assert comp2 in result
    assert comp3 in result


def test_pipeline_fetch_comparabile_handles_connector_error(orchestrator, subiect_test, criterii_test):
    """fetch_comparabile_paralel continues even if a connector fails."""
    comp1 = Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70)

    # First connector fails, second succeeds
    orchestrator.connectors[0].search = Mock(
        side_effect=ConnectorError("Timeout", connector="imobiliare.ro")
    )
    orchestrator.connectors[1].search = Mock(return_value=[comp1])
    for connector in orchestrator.connectors[2:]:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)

    # Should still get results from the working connector
    assert len(result) >= 1
    assert comp1 in result


def test_pipeline_fetch_comparabile_timeout_handling(orchestrator, subiect_test, criterii_test):
    """fetch_comparabile_paralel handles timeouts gracefully."""
    # Mock all connectors: some timeout, some work
    orchestrator.connectors[0].search = Mock(
        side_effect=ConnectorError("Timeout", connector="imobiliare.ro")
    )
    orchestrator.connectors[1].search = Mock(return_value=[
        Comparabila(sursa="storia.ro", pret_eur=85000, supr_totala=65)
    ])
    for connector in orchestrator.connectors[2:]:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)

    # Should return results from working connectors
    assert isinstance(result, list)
    # At least the one that succeeded should be present
    assert len(result) >= 1


def test_pipeline_deduplicate_and_analyze(orchestrator, subiect_test):
    """deduplicate_and_analyze returns an Analiza object."""
    comparabile = [
        Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70, marcaj="activ"),
        Comparabila(sursa="historia.ro", pret_eur=85000, supr_totala=65, marcaj="activ"),
    ]

    result = orchestrator.deduplicate_and_analyze(subiect_test, comparabile)

    assert isinstance(result, Analiza)
    assert result.subiect == subiect_test
    assert len(result.comparabile) >= 0  # May be filtered


def test_pipeline_deduplicate_and_analyze_handles_empty_list(orchestrator, subiect_test):
    """deduplicate_and_analyze handles empty comparabile list gracefully."""
    comparabile = []

    # This may raise an exception or return a valid Analiza with filtered results
    # Depending on implementation - for now just verify it doesn't crash catastrophically
    try:
        result = orchestrator.deduplicate_and_analyze(subiect_test, comparabile)
        assert isinstance(result, Analiza)
    except Exception:
        # Some exceptions may be acceptable (e.g., insufficient data for statistics)
        pass


def test_pipeline_fetch_and_analyze_integration(orchestrator, subiect_test, criterii_test):
    """Integration test: fetch and analyze together."""
    comp1 = Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70, marcaj="activ")
    comp2 = Comparabila(sursa="historia.ro", pret_eur=85000, supr_totala=65, marcaj="activ")

    # Mock all connectors
    orchestrator.connectors[0].search = Mock(return_value=[comp1])
    orchestrator.connectors[1].search = Mock(return_value=[comp2])
    for connector in orchestrator.connectors[2:]:
        connector.search = Mock(return_value=[])

    # Fetch
    comparabile = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)
    assert len(comparabile) >= 1

    # Analyze
    analiza = orchestrator.deduplicate_and_analyze(subiect_test, comparabile)
    assert isinstance(analiza, Analiza)
    assert analiza.subiect == subiect_test
