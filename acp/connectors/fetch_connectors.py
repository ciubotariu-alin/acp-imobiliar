"""Conectori cu fetch simplu (HTTP + BeautifulSoup)."""
import re
import unicodedata

import httpx
from bs4 import BeautifulSoup

from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _norm(text: str) -> str:
    """Lowercase fără diacritice (pentru potrivire de zonă/titlu)."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")
    return t.lower()


def _primul_intreg(text: str) -> int | None:
    """Primul număr întreg dintr-un text (ex. '85 000 EUR' -> 85000, '1 328' -> 1328)."""
    m = re.search(r"\d[\d.\s]*\d|\d", text or "")
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(0))
    return int(digits) if digits else None


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
    """Connector pentru romimo.ro (SSR, fără anti-bot).

    romimo.ro nu are un URL de căutare care combină tip+camere+cartier. Paginile
    geografice ``/imobiliare/bucuresti/sector-N/`` sunt însă randate server-side, cu
    prețuri, și conțin cartierul în ``.article-location``. Bucureștiul are 6 sectoare,
    iar romimo nu limitează cererile (verificat: 12 pagini în 2.6s, toate 200), așa că
    parcurgem cele 6 sectoare și post-filtrăm cardurile după zonă/tip/camere/suprafață —
    fără mapare cartier→sector de întreținut. Suprafața nu apare direct pe card, dar se
    derivă din preț ÷ (EUR/m²).
    """

    SECTOARE = tuple(f"sector-{i}" for i in range(1, 7))

    def __init__(self):
        super().__init__(name="romimo.ro")
        self.base_url = "https://www.romimo.ro"

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Fetch cele 6 pagini de sector București + post-filtrare. Doar vânzare (v1).

        Un sector care eșuează (HTTP) e sărit, nu oprește restul. Deduplicare pe URL.
        """
        if criterii.tip != "vanzare":
            return []
        comparabile: list[Comparabila] = []
        vazute: set[str] = set()
        for sector in self.SECTOARE:
            try:
                response = httpx.get(
                    self._build_url(criterii, sector),
                    headers={"User-Agent": _UA},
                    timeout=self.timeout_seconds,
                    follow_redirects=True,
                )
                response.raise_for_status()
            except httpx.HTTPError:
                continue
            for comp in self._parse_html(response.text, criterii):
                if comp.url and comp.url not in vazute:
                    vazute.add(comp.url)
                    comparabile.append(comp)
        return comparabile

    def _build_url(self, criterii: CriteriiCautare, sector: str = "") -> str:
        """URL geografic București (opțional pe sector): /imobiliare/bucuresti[/sector-N]/."""
        base = f"{self.base_url}/imobiliare/bucuresti"
        return f"{base}/{sector}/" if sector else f"{base}/"

    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        """Parseaza cardurile ``div.article-item`` și post-filtrează.

        Păstrează doar: apartamente **de vânzare** (după href), din **zona** cerută
        (``.article-location``), cu **numărul de camere** din titlu egal cu criteriile
        și **suprafața** (preț ÷ EUR/m²) în intervalul cerut.
        """
        soup = BeautifulSoup(html, "html.parser")
        zona = _norm(criterii.zona)
        rezultat: list[Comparabila] = []
        for card in soup.select("div.article-item"):
            link = card.find("a", href=True)
            url = link["href"] if link else None
            if not url:
                continue
            if not url.startswith("http"):
                url = self.base_url + url
            if "de-vanzare" not in url:  # exclude închirieri
                continue

            loc_el = card.select_one(".article-location")
            loc = _norm(loc_el.get_text(" ", strip=True)) if loc_el else ""
            if zona and zona not in loc:
                continue

            titlu_el = card.select_one(".article-title")
            titlu = _norm(titlu_el.get_text(" ", strip=True)) if titlu_el else ""
            if "apartament" not in titlu:
                continue
            m = re.search(r"(\d)\s*camer", titlu)
            if not m or int(m.group(1)) != criterii.camere:
                continue

            price_el = card.select_one(".article-price")
            if price_el is None:
                continue
            new_price = price_el.select_one(".new-price")
            pret = _primul_intreg((new_price or price_el).get_text())
            if not pret:
                continue

            info_el = card.select_one(".article-short-info")
            ppm = None
            if info_el:
                mm = re.search(r"([\d.\s]+)\s*EUR/m", info_el.get_text())
                ppm = _primul_intreg(mm.group(1)) if mm else None
            if not ppm:
                continue
            supr = round(pret / ppm)
            if not (criterii.supr_min <= supr <= criterii.supr_max):
                continue

            rezultat.append(Comparabila(
                sursa=self.name, url=url, pret_eur=float(pret),
                supr_totala=float(supr), camere=criterii.camere, tip="vanzare",
            ))
        return rezultat


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
