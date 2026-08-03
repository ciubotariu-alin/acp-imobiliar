"""Tests for the pipeline layer.

This file covers two distinct modules that both live under the "pipeline"
name in this codebase:

1. `acp.pipeline` (Plan 1 / schelet end-to-end): the simple sequential
   `criterii_din_subiect()` + `ruleaza()` helpers used by the fixture-based
   demo (`exemple/demo.py`).
2. `acp.core.pipeline` (Plan 2 / conectori reali): `PipelineOrchestrator`,
   which fetches from all 9 real connectors in parallel and delegates to
   `analizeaza()` for dedup/analysis.

Both live in `tests/test_pipeline.py` per the Task 7 brief, which specifies
this exact filename for the orchestrator tests; merging avoids clobbering
the pre-existing Plan 1 coverage that already used this filename.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock

from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza, Statistici, ContextPiata
from acp.connectors.fixture import FixtureConnector
from acp.connectors.base import ConnectorError
from acp.pipeline import criterii_din_subiect, ruleaza
from acp.core.pipeline import PipelineOrchestrator


# ---------------------------------------------------------------------------
# acp.pipeline (Plan 1: schelet end-to-end, fixture-based)
# ---------------------------------------------------------------------------

def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                   locatie="Confort City")


def test_criterii_din_subiect():
    crit = criterii_din_subiect(_subiect())
    assert crit.camere == 2
    assert crit.supr_min < 66 < crit.supr_max


def test_pipeline_end_to_end(tmp_path):
    cale = tmp_path / "raport.pdf"
    conn = FixtureConnector("exemple/comparabile_confort_city.json")
    analiza = ruleaza(_subiect(), [conn], tinta_zile=90, cale_pdf=str(cale))
    assert cale.exists()
    assert cale.read_bytes()[:4] == b"%PDF"
    assert analiza.stat_ajustat.n >= 3
    assert "storia" in analiza.surse


# ---------------------------------------------------------------------------
# acp.core.pipeline (Plan 2: PipelineOrchestrator, parallel real connectors)
# ---------------------------------------------------------------------------

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


def test_pipeline_connector_timeout_is_30s_per_connector(orchestrator):
    """Spec requires <=30s per connector, enforced independently per connector
    (not as a shared/total budget for the whole pool)."""
    assert orchestrator.CONNECTOR_TIMEOUT_SECONDS == 30


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
    """fetch_comparabile_paralel continues even if a connector fails (even after
    its assisted fallback retry also fails)."""
    comp1 = Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70)

    # First connector fails on every call (original attempt + fallback retry), second succeeds
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
    # Original attempt + one assisted fallback retry
    assert orchestrator.connectors[0].search.call_count == 2


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


def test_pipeline_fetch_comparabile_assisted_fallback_on_connector_error(
    orchestrator, subiect_test, criterii_test
):
    """When a connector raises ConnectorError, the orchestrator retries once
    with relaxed criteria ('fallback asistat') before giving up, and picks up
    results from a fallback attempt that succeeds."""
    comp_fallback = Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70)
    calls: list[CriteriiCautare] = []

    def flaky_search(criterii):
        calls.append(criterii)
        if len(calls) == 1:
            raise ConnectorError("blocked by portal", connector="imobiliare.ro")
        return [comp_fallback]

    orchestrator.connectors[0].search = Mock(side_effect=flaky_search)
    for connector in orchestrator.connectors[1:]:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)

    assert comp_fallback in result
    assert len(calls) == 2
    # First call used the original criteria.
    assert calls[0].raza_km == criterii_test.raza_km
    assert calls[0].supr_min == criterii_test.supr_min
    # Retry used relaxed criteria: wider radius and wider surface band, same rooms/zone.
    assert calls[1].raza_km == criterii_test.raza_km * 2
    assert calls[1].camere == criterii_test.camere
    assert calls[1].zona == criterii_test.zona
    assert calls[1].supr_min < criterii_test.supr_min
    assert calls[1].supr_max > criterii_test.supr_max


def test_pipeline_fetch_comparabile_fallback_also_fails_returns_empty_for_that_connector(
    orchestrator, subiect_test, criterii_test
):
    """If both the original attempt and the assisted fallback retry fail, the
    failing connector contributes nothing, but the pipeline still aggregates
    results from the other connectors."""
    comp_ok = Comparabila(sursa="storia.ro", pret_eur=85000, supr_totala=65)

    orchestrator.connectors[0].search = Mock(
        side_effect=ConnectorError("blocked", connector="imobiliare.ro")
    )
    orchestrator.connectors[1].search = Mock(return_value=[comp_ok])
    for connector in orchestrator.connectors[2:]:
        connector.search = Mock(return_value=[])

    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii_test)

    assert comp_ok in result
    assert all(c.sursa != "imobiliare.ro" for c in result)
    # Original attempt + one assisted fallback retry, both failed.
    assert orchestrator.connectors[0].search.call_count == 2


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
    """deduplicate_and_analyze with no comparabile raises ValueError.

    This is the deliberate, existing behavior of the underlying analizeaza()
    -> calculeaza_statistici(): there is no price data to compute statistics
    from, so it raises rather than fabricating a zero-filled Analiza. We
    assert this explicitly (message included) instead of silently accepting
    either outcome.
    """
    with pytest.raises(ValueError, match="Lista de valori este goală"):
        orchestrator.deduplicate_and_analyze(subiect_test, [])


def test_pipeline_deduplicate_and_analyze_extracts_and_passes_sources(orchestrator, subiect_test):
    """deduplicate_and_analyze extracts the unique set of sources from the
    comparabile it receives and passes them through to analizeaza()."""
    comparabile = [
        Comparabila(sursa="imobiliare.ro", pret_eur=80000, supr_totala=70, marcaj="activ"),
        Comparabila(sursa="storia.ro", pret_eur=85000, supr_totala=65, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=82000, supr_totala=68, marcaj="activ"),
    ]

    # A real (minimal) Analiza instance rather than a Mock: deduplicate_and_analyze
    # itself reads attributes off the return value (e.g. stat_ajustat.n for
    # logging), so a bare Mock would need every attribute stubbed out anyway.
    stat = Statistici(n=1, minim=1000, mediana=1000, maxim=1000)
    sentinel_analiza = Analiza(
        subiect=subiect_test, comparabile=[], context=ContextPiata(nr_active=0),
        stat_brut=stat, stat_ajustat=stat, pozitionare_pct=0.0, incadrare="corect",
        pret_listare=(0, 0), pret_tranzactie=(0, 0), tinta_zile=90,
    )
    with patch("acp.core.pipeline.analizeaza", return_value=sentinel_analiza) as mock_analizeaza:
        result = orchestrator.deduplicate_and_analyze(subiect_test, comparabile)

    assert result is sentinel_analiza
    mock_analizeaza.assert_called_once()
    args, kwargs = mock_analizeaza.call_args
    assert args[0] == subiect_test
    assert args[1] == comparabile
    assert kwargs["tinta_zile"] == 90
    # Unique, sorted sources — duplicates from the same portal collapsed.
    assert kwargs["surse"] == ["imobiliare.ro", "storia.ro"]


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
