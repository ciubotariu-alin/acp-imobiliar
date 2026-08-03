"""Conectori cu fetch simplu (HTTP + BeautifulSoup)."""
import httpx
from bs4 import BeautifulSoup

from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class FetchConnectorBase(ConnectorBase):
    """Bază pentru conectori care folosesc HTTP + HTML parsing."""

    base_url: str = ""  # suprascris de subclase
    timeout_seconds: int = 30

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Fetch + parse HTML."""
        try:
            url = self._build_url(criterii)
            response = httpx.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            return self._parse_html(response.text, criterii)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"{self.name} timeout", connector=self.name) from e
        except httpx.HTTPError as e:
            raise ConnectorError(f"{self.name} HTTP error: {e}", connector=self.name) from e

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL cu parametrii. Suprascris de subclase."""
        raise NotImplementedError()

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML și returnează list[Comparabila]. Suprascris de subclase."""
        raise NotImplementedError()


class Publi24Connector(FetchConnectorBase):
    """Connector pentru publi24.ro."""

    def __init__(self):
        super().__init__(name="publi24.ro")
        self.base_url = "https://www.publi24.ro"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru publi24."""
        # TODO: implementa parametrii specifici publi24
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din publi24 și returnează lista de comparabile."""
        # TODO: implementa parsing HTML publi24, aplicand filtrare camere
        return []


class RomimoConnector(FetchConnectorBase):
    """Connector pentru romimo.ro."""

    def __init__(self):
        super().__init__(name="romimo.ro")
        self.base_url = "https://www.romimo.ro"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru romimo."""
        # TODO: implementa parametrii specifici romimo
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din romimo și returnează lista de comparabile."""
        # TODO: implementa parsing HTML romimo, aplicand filtrare camere
        return []


class SudrezidentialConnector(FetchConnectorBase):
    """Connector pentru sudrezidential.ro."""

    def __init__(self):
        super().__init__(name="sudrezidential.ro")
        self.base_url = "https://www.sudrezidential.ro"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru sudrezidential."""
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din sudrezidential și returnează lista de comparabile."""
        # TODO: implementa parsing HTML sudrezidential, aplicand filtrare camere
        return []


class LajumateConnector(FetchConnectorBase):
    """Connector pentru lajumate.ro."""

    def __init__(self):
        super().__init__(name="lajumate.ro")
        self.base_url = "https://www.lajumate.ro"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru lajumate."""
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din lajumate și returnează lista de comparabile."""
        # TODO: implementa parsing HTML lajumate, aplicand filtrare camere
        return []


class Waa2Connector(FetchConnectorBase):
    """Connector pentru waa2.com."""

    def __init__(self):
        super().__init__(name="waa2.com")
        self.base_url = "https://www.waa2.com"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru waa2."""
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din waa2 și returnează lista de comparabile."""
        # TODO: implementa parsing HTML waa2, aplicand filtrare camere
        return []


class AnuntulConnector(FetchConnectorBase):
    """Connector pentru anuntul.ro."""

    def __init__(self):
        super().__init__(name="anuntul.ro")
        self.base_url = "https://www.anuntul.ro"

    def _build_url(self, criterii: CriteriiCautare) -> str:
        """Construiește URL de căutare pentru anuntul."""
        return self.base_url

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza HTML din anuntul și returnează lista de comparabile."""
        # TODO: implementa parsing HTML anuntul, aplicand filtrare camere
        return []
