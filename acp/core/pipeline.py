"""Orchestrare pipeline end-to-end."""
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

from acp.connectors.base import ConnectorBase, ConnectorError
from acp.connectors.imobiliare import ImobiliareConnector
from acp.connectors.storia import StoriaConnector
from acp.connectors.olx import OlxConnector
from acp.connectors.fetch_connectors import (
    Publi24Connector, RomimoConnector, SudrezidentialConnector,
    LajumateConnector, Waa2Connector, AnuntulConnector
)
from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza
from acp.analiza import analizeaza

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Coordonare conectori, filtrare, deduplicare, analiză."""

    CONNECTOR_TIMEOUT_SECONDS = 60  # Timeout per connector

    def __init__(self):
        """Initialize orchestrator with all 9 connectors."""
        self.connectors = [
            ImobiliareConnector(),
            StoriaConnector(),
            OlxConnector(),
            Publi24Connector(),
            RomimoConnector(),
            SudrezidentialConnector(),
            LajumateConnector(),
            Waa2Connector(),
            AnuntulConnector(),
        ]

    def fetch_comparabile_paralel(self, subiect: Subiect, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Fetch din toți connectorii în paralel.

        Uses ThreadPoolExecutor to fetch from all connectors in parallel.
        Each connector has a timeout of CONNECTOR_TIMEOUT_SECONDS.
        If a connector fails, the error is logged and the orchestrator continues
        with the remaining connectors.

        Args:
            subiect: Subiect object (currently used for logging)
            criterii: Search criteria to pass to each connector

        Returns:
            list[Comparabila]: Aggregated list of comparabile from all successful connectors
        """
        comparabile = []

        def fetch_from_connector(connector: ConnectorBase) -> tuple[str, list[Comparabila]]:
            """Fetch from a single connector with error handling."""
            try:
                result = connector.search(criterii)
                logger.info(f"Connector {connector.name} returned {len(result)} comparabile")
                return connector.name, result
            except ConnectorError as e:
                logger.warning(f"Connector {connector.name} failed with ConnectorError: {e}")
                return connector.name, []
            except Exception as e:
                logger.warning(f"Connector {connector.name} failed with unexpected error: {type(e).__name__}: {e}")
                return connector.name, []

        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=len(self.connectors)) as executor:
            futures = {
                executor.submit(fetch_from_connector, connector): connector.name
                for connector in self.connectors
            }

            for future in as_completed(futures, timeout=self.CONNECTOR_TIMEOUT_SECONDS):
                try:
                    connector_name, results = future.result(timeout=self.CONNECTOR_TIMEOUT_SECONDS)
                    comparabile.extend(results)
                except FuturesTimeoutError:
                    connector_name = futures[future]
                    logger.warning(f"Connector {connector_name} exceeded timeout of {self.CONNECTOR_TIMEOUT_SECONDS}s")
                except Exception as e:
                    connector_name = futures[future]
                    logger.error(f"Unexpected error from connector {connector_name}: {type(e).__name__}: {e}")

        logger.info(f"fetch_comparabile_paralel aggregated {len(comparabile)} comparabile from all connectors")
        return comparabile

    def deduplicate_and_analyze(self, subiect: Subiect, comparabile: list[Comparabila]) -> Analiza:
        """
        Deduplicate comparabile and generate analysis.

        Delegates to the existing analizeaza function which handles:
        - Deduplication across portals
        - Filtering of outliers
        - Statistical analysis
        - Market context calculation
        - Price recommendations

        Args:
            subiect: Subject property being analyzed
            comparabile: List of comparable properties from all connectors

        Returns:
            Analiza: Complete analysis object with statistics, context, and recommendations
        """
        # Extract unique sources from comparabile for reporting
        surse = sorted({c.sursa for c in comparabile})
        logger.info(f"deduplicate_and_analyze processing {len(comparabile)} comparabile from {len(surse)} sources")

        # Use the existing analizeaza function which handles dedup, filtering, and analysis
        analiza = analizeaza(subiect, comparabile, tinta_zile=90, surse=surse)

        logger.info(f"Analysis complete: {analiza.stat_ajustat.n} comparabile retained after filtering")
        return analiza
