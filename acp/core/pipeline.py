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
from acp.filtrare import filtreaza, dedup
from acp.detalii import imbogateste_detalii
from acp.cache_detalii import CacheDetalii

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Coordonare conectori, filtrare, deduplicare, analiză."""

    # Timeout PER connector (spec: ≤30s/connector) — NU un timeout total pentru
    # întregul pool. Fiecare connector primește propriul buget, aplicat izolat
    # în _search_cu_timeout(), astfel încât un connector lent nu erodează
    # bugetul de timp al celorlalți connectori care rulează în paralel.
    CONNECTOR_TIMEOUT_SECONDS = 30

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

    @staticmethod
    def _relaxeaza_criterii(criterii: CriteriiCautare) -> CriteriiCautare:
        """
        Construiește criterii de căutare relaxate pentru fallback asistat.

        Folosit când un connector eșuează (ConnectorError) sau depășește
        timeout-ul per-connector: se reîncearcă o singură dată cu o rază
        dublată și un interval de suprafață mai larg (±20% suplimentar),
        păstrând totuși numărul de camere și zona originale.
        """
        return CriteriiCautare(
            camere=criterii.camere,
            supr_min=criterii.supr_min * 0.8,
            supr_max=criterii.supr_max * 1.2,
            an_min=criterii.an_min,
            an_max=criterii.an_max,
            zona=criterii.zona,
            raza_km=(criterii.raza_km * 2) if criterii.raza_km else 2,
            tip=criterii.tip,
        )

    def _search_cu_timeout(self, connector: ConnectorBase, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Rulează connector.search() cu un timeout propriu de CONNECTOR_TIMEOUT_SECONDS.

        Timeout-ul este aplicat per-apel (per-connector), nu la nivel de pool:
        folosește un executor dedicat, cu un singur worker, astfel încât
        future.result(timeout=...) mărginește strict acest connector, indiferent
        de cât durează ceilalți connectori care rulează concurent în alte thread-uri.

        NOTE: deliberately NOT using the executor as a context manager. `with
        ThreadPoolExecutor(...) as executor:` calls `shutdown(wait=True)` on
        exit, which blocks until the submitted task actually finishes — even
        after we've already given up on it via `future.result(timeout=...)`.
        That would silently turn our per-connector timeout back into an
        unbounded wait. Python cannot force-kill a running thread, so on
        timeout we shut down with `wait=False` and let the orphaned thread
        finish in the background instead of blocking the caller on it.
        """
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(connector.search, criterii)
        try:
            return future.result(timeout=self.CONNECTOR_TIMEOUT_SECONDS)
        finally:
            executor.shutdown(wait=False)

    def _fetch_cu_fallback(self, connector: ConnectorBase, criterii: CriteriiCautare) -> tuple[str, list[Comparabila]]:
        """
        Fetch de la un singur connector, cu timeout per-connector și fallback asistat.

        Dacă connectorul eșuează cu ConnectorError sau depășește timeout-ul
        per-connector (blocaj de portal, rate-limiting etc.), se reîncearcă o
        singură dată cu criterii relaxate ("fallback asistat dacă se blochează",
        conform specificației) înainte de a renunța. Toate încercările — inclusiv
        reîncercarea — sunt logate cu motivul și rezultatul.
        """
        try:
            result = self._search_cu_timeout(connector, criterii)
            logger.info(f"Connector {connector.name} returned {len(result)} comparabile")
            return connector.name, result
        except FuturesTimeoutError:
            logger.warning(
                f"Connector {connector.name} exceeded per-connector timeout of "
                f"{self.CONNECTOR_TIMEOUT_SECONDS}s — attempting assisted fallback with relaxed criteria"
            )
        except ConnectorError as e:
            logger.warning(
                f"Connector {connector.name} failed with ConnectorError: {e} — "
                f"attempting assisted fallback with relaxed criteria"
            )
        except Exception as e:
            logger.warning(f"Connector {connector.name} failed with unexpected error: {type(e).__name__}: {e}")
            return connector.name, []

        # Fallback asistat: o singură reîncercare, cu criterii relaxate.
        relaxate = self._relaxeaza_criterii(criterii)
        try:
            result = self._search_cu_timeout(connector, relaxate)
            logger.info(
                f"Connector {connector.name} assisted fallback SUCCEEDED "
                f"(raza_km={relaxate.raza_km}, supr=[{relaxate.supr_min:.1f}, {relaxate.supr_max:.1f}]) "
                f"returned {len(result)} comparabile"
            )
            return connector.name, result
        except FuturesTimeoutError:
            logger.error(
                f"Connector {connector.name} assisted fallback ALSO exceeded timeout "
                f"of {self.CONNECTOR_TIMEOUT_SECONDS}s — giving up"
            )
        except ConnectorError as e:
            logger.error(f"Connector {connector.name} assisted fallback ALSO failed with ConnectorError: {e} — giving up")
        except Exception as e:
            logger.error(
                f"Connector {connector.name} assisted fallback failed with unexpected error: "
                f"{type(e).__name__}: {e} — giving up"
            )
        return connector.name, []

    def fetch_comparabile_paralel(self, subiect: Subiect, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Fetch din toți connectorii în paralel.

        Uses ThreadPoolExecutor to fetch from all connectors in parallel. Each
        connector gets its own timeout budget of CONNECTOR_TIMEOUT_SECONDS,
        enforced independently per connector (see _search_cu_timeout) — not a
        shared/pool-level timeout for the whole batch. If a connector fails or
        times out, an assisted fallback retries it once with relaxed search
        criteria before giving up (see _fetch_cu_fallback); the orchestrator
        always continues with the remaining connectors regardless of outcome.

        Args:
            subiect: Subiect object (currently used for logging)
            criterii: Search criteria to pass to each connector

        Returns:
            list[Comparabila]: Aggregated list of comparabile from all successful connectors
        """
        comparabile = []

        # Use ThreadPoolExecutor for parallel fetching. No pool-level timeout is
        # applied here: each submitted task already bounds its own runtime via
        # _fetch_cu_fallback → _search_cu_timeout, so as_completed simply waits
        # for each (self-bounded) task to finish rather than imposing an
        # additional, shared deadline across all connectors.
        with ThreadPoolExecutor(max_workers=len(self.connectors)) as executor:
            futures = {
                executor.submit(self._fetch_cu_fallback, connector, criterii): connector.name
                for connector in self.connectors
            }

            for future in as_completed(futures):
                connector_name = futures[future]
                try:
                    _, results = future.result()
                    comparabile.extend(results)
                except Exception as e:
                    logger.error(f"Unexpected error from connector {connector_name}: {type(e).__name__}: {e}")

        logger.info(f"fetch_comparabile_paralel aggregated {len(comparabile)} comparabile from all connectors")
        return comparabile

    def deduplicate_and_analyze(self, subiect: Subiect, comparabile: list[Comparabila],
                                imbogateste: bool = True, cache=None) -> Analiza:
        """
        Deduplicate comparabile and generate analysis.

        Delegates to the existing analizeaza function which handles:
        - Deduplication across portals
        - Filtering of outliers
        - Statistical analysis
        - Market context calculation
        - Price recommendations

        When `imbogateste` is True (default), comparabilele care supraviețuiesc
        filtrării (`filtreaza(subiect, dedup(...))`) sunt îmbogățite cu date de
        pe pagina lor de detaliu (Playwright secvențial, per-conector, cu cache
        pe disc) înainte de analiză, astfel încât ajustările de dotări să se
        aplice pe date reale, nu pe presupunerea "card gol = nu are".

        Args:
            subiect: Subject property being analyzed
            comparabile: List of comparable properties from all connectors
            imbogateste: Whether to fetch and parse detail pages for survivors
            cache: Optional CacheDetalii instance (defaults to a new one)

        Returns:
            Analiza: Complete analysis object with statistics, context, and recommendations
        """
        if imbogateste:
            vanzari = [c for c in comparabile if c.tip == "vanzare"]
            survivors = filtreaza(subiect, dedup(vanzari))
            fetchers = {
                c.name: c.fetch_detaliu_text
                for c in self.connectors
                if hasattr(c, "fetch_detaliu_text")
            }
            if cache is None:
                cache = CacheDetalii()
            n = imbogateste_detalii(survivors, fetchers, cache)
            logger.info(f"Imbogatite {n}/{len(survivors)} comparabile cu detalii de pe pagina de detaliu")

        # Extract unique sources from comparabile for reporting
        surse = sorted({c.sursa for c in comparabile})
        logger.info(f"deduplicate_and_analyze processing {len(comparabile)} comparabile from {len(surse)} sources")

        # Use the existing analizeaza function which handles dedup, filtering, and analysis
        analiza = analizeaza(subiect, comparabile, tinta_zile=90, surse=surse)

        logger.info(f"Analysis complete: {analiza.stat_ajustat.n} comparabile retained after filtering")
        return analiza
