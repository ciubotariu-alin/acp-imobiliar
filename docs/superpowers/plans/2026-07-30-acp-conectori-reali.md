# ACP Imobiliar — Plan 2: Conectori Reali Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrează conectori reali pentru 9 portaluri imobiliare (3 mari cu Playwright, 6 secundare cu fetch), orchestrează pipeline-ul end-to-end cu fallback asistat de agent, și produce rapoarte PDF cu date live.

**Architecture:** 
- Interfață comună `ConnectorBase` cu metodă `search(criterii) → list[Comparabila]`
- 3 conectori cu Playwright (imobiliare.ro, storia.ro, olx.ro) cu pauze politicoase și retry logic
- 6 conectori cu fetch/BeautifulSoup (publi24, romimo, sudrezidential, lajumate, waa2, anuntul)
- Orchestrator care rulează conectori în paralel/secvență, agregă rezultate, invoke fallback asistat dacă connector cade
- SKILL.md cu instrucțiuni agent (persona „20 ani", pași pipeline)
- Tests pe fixturi salvate (HTTP cache) ca să nu lovim site-urile la fiecare test

**Tech Stack:** Playwright (browser automation), BeautifulSoup + httpx (fetch), requests-cache (fixture snapshots), pytest (integration tests)

## Global Constraints

- Limbă: conținut raport în **română**; identificatori cod în engleză/română consistent
- Toate calculele €/mp pe **suprafață totală**
- Anti-bot: politicos (Playwright cu pauze ≥2s între requeste, user-agent real, politiță ToS)
- Deduplicare cross-portal: semnătură = adresă + supr + etaj + an (fără preț — deoarece anunțurile pe portaluri diferite pot diferi)
- Timeout pentru conectori: ≤30s per portal, cu fallback asistat dacă se blochează
- Raportul declară mereu sursele efectiv consultate
- Disclaimer fix: „Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR"
- Corecția anunț→tranzacție: **4–8%** (0.04–0.08) aplicată global pe verdictul de preț
- Paleta culori PDF: bleumarin `#1b2a4a` + crem `#f5efe0`

---

### Task 1: Extinde scaffold + ConnectorBase interface

**Files:**
- Create: `acp/connectors/__init__.py`
- Create: `acp/connectors/base.py`
- Modify: `acp/core/__init__.py` (crează director + __init__)
- Modify: `pyproject.toml` (adaugă BeautifulSoup, httpx, requests-cache, Playwright, tenacity)
- Test: `tests/test_connectors_base.py`

**Interfaces:**
- Consumes: `Subiect`, `Comparabila`, `CriteriiCautare` din `acp.modele`
- Produces:
  - `ConnectorBase` (ABC cu metodă abstractă `search(criterii: CriteriiCautare) → list[Comparabila]`)
  - `ConnectorError` (exception pentru retry logic)

- [ ] **Step 1: Creează directoare și __init__ files**

```bash
mkdir -p ~/OwnDevelopment/acp-imobiliar/acp/connectors
mkdir -p ~/OwnDevelopment/acp-imobiliar/acp/core
touch ~/OwnDevelopment/acp-imobiliar/acp/connectors/__init__.py
touch ~/OwnDevelopment/acp-imobiliar/acp/core/__init__.py
```

- [ ] **Step 2: Scrie testele pentru ConnectorBase și ConnectorError**

`tests/test_connectors_base.py`:
```python
import pytest
from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class StubConnector(ConnectorBase):
    """Stub connector pentru testing."""
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        return [
            Comparabila(sursa="stub", url=None, pret_eur=100000, supr_totala=70,
                       etaj=5, an=2015, dotari=[], marcaj="activ", tip="vanzare",
                       ajustari=[])
        ]


def test_connector_base_subclass():
    """Subclasa ConnectorBase e validă."""
    connector = StubConnector(name="stub")
    criterii = CriteriiCautare(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
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
```

- [ ] **Step 3: Update pyproject.toml cu noi dependențe**

Adaugă la `dependencies`:
```toml
dependencies = [
    "pydantic>=2.6",
    "jinja2>=3.1",
    "weasyprint>=61",
    "beautifulsoup4>=4.12",
    "httpx>=0.25",
    "requests-cache>=1.1",
    "playwright>=1.40",
    "tenacity>=8.2",
]
```

- [ ] **Step 4: Implementează ConnectorBase și ConnectorError**

`acp/connectors/base.py`:
```python
"""Interfață comună pentru connectori de portaluri."""
from abc import ABC, abstractmethod
from acp.modele import CriteriiCautare, Comparabila


class ConnectorError(Exception):
    """Eroare la extragere date de pe portal."""
    def __init__(self, message: str, connector: str | None = None):
        super().__init__(message)
        self.connector = connector


class ConnectorBase(ABC):
    """Interfață comună pentru toți connectorii."""
    
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută anunțuri pe portal conform criteriilor.
        
        Args:
            criterii: CriteriiCautare cu camere, suprafață, zonă, rază
        
        Returns:
            Listă de Comparabila (gol dacă nimic găsit sau connector blocat)
        
        Raises:
            ConnectorError: dacă search eșuează (timeout, 403, etc)
        """
        pass
```

- [ ] **Step 5: Update `acp/connectors/__init__.py`**

```python
"""Connectori pentru portaluri imobiliare."""
from acp.connectors.base import ConnectorBase, ConnectorError

__all__ = ["ConnectorBase", "ConnectorError"]
```

- [ ] **Step 6: Update `acp/core/__init__.py`**

```python
"""Core pipeline components."""
```

- [ ] **Step 7: Rulează testele**

Run: `cd ~/OwnDevelopment/acp-imobiliar && uv sync --extra dev && uv run pytest tests/test_connectors_base.py -v`
Expected: PASS (2 passed)

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml acp/connectors/ acp/core/__init__.py tests/test_connectors_base.py
git commit -m "feat: ConnectorBase interface și directoare conectori"
```

---

### Task 2: Connector imobiliare.ro (Playwright politicos)

**Files:**
- Create: `acp/connectors/imobiliare.py`
- Create: `fixtures/imobiliare_search_result.html` (saved HTTP response)
- Test: `tests/test_imobiliare_connector.py`

**Interfaces:**
- Consumes: `ConnectorBase`, `CriteriiCautare`, `Comparabila`
- Produces: `ImobiliareConnector` (subclasă)
  - `search(criterii) → list[Comparabila]`
  - `_normalize_listing_to_comparabila(html_elem) → Comparabila` (internal)

- [ ] **Step 1: Creează fixtura (saved HTML)**

Salvează o cerere HTTPS reală către imobiliare.ro (search 2 camere, sector 3, 60-80 mp) ca `fixtures/imobiliare_search_result.html`. 
Hint: poți folosi `curl` + salveaz în fișierul fixture, sau o vei face manual prima dată.

```bash
mkdir -p ~/OwnDevelopment/acp-imobiliar/fixtures
# placeholder — va fi salvat din browserul real în Step 2
echo "<!-- placeholder imobiliare.ro search result -->" > ~/OwnDevelopment/acp-imobiliar/fixtures/imobiliare_search_result.html
```

- [ ] **Step 2: Scrie testul cu fixtura salvată**

`tests/test_imobiliare_connector.py`:
```python
import pytest
from pathlib import Path
from acp.connectors.imobiliare import ImobiliareConnector
from acp.modele import CriteriiCautare


@pytest.fixture
def imobiliare_html():
    """Încarc HTML salvat din imobiliare.ro (search 2 camere, S3, 60-80mp)."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "imobiliare_search_result.html"
    if not fixture_path.exists():
        pytest.skip("Fixture imobiliare_search_result.html nu există")
    return fixture_path.read_text()


def test_imobiliare_parse_listing(imobiliare_html):
    """Parsing-ul unui anunț din HTML e corect."""
    connector = ImobiliareConnector()
    # De implementat după ce am HTML real
    # Pentru acum: verifică că metoda e callable
    assert hasattr(connector, "_normalize_listing_to_comparabila")


def test_imobiliare_search_integration(imobiliare_html, monkeypatch):
    """Search pe imobiliare.ro (cu fixtura salvată)."""
    # Monkeypatch: asyncPlaywright să return fixtura în loc să facă HTTP real
    connector = ImobiliareConnector()
    criterii = CriteriiCautare(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    
    # For now: placeholder
    # După ce avem HTML + parsing: assert len(result) > 0 și validează Comparabila fields
    result = []  # TODO: call connector.search(criterii)
    assert isinstance(result, list)
```

- [ ] **Step 3: Implementează ImobiliareConnector (scaffold)**

`acp/connectors/imobiliare.py`:
```python
"""Connector pentru imobiliare.ro."""
import asyncio
from playwright.async_api import async_playwright
from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class ImobiliareConnector(ConnectorBase):
    """Connector pentru imobiliare.ro cu Playwright politicos."""
    
    def __init__(self):
        super().__init__(name="imobiliare.ro")
        self.base_url = "https://www.imobiliare.ro"
    
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută pe imobiliare.ro cu Playwright.
        
        Politicos: min 2s între requeste, user-agent real, respectă robots.txt.
        """
        try:
            return asyncio.run(self._search_async(criterii))
        except Exception as e:
            raise ConnectorError(f"imobiliare.ro search failed: {e}", connector=self.name)
    
    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Logica Playwright async."""
        # TODO: construiește URL cu parametrii
        # TODO: lansează browser, navigează, extrage anunțuri
        # TODO: parseaza cu BeautifulSoup
        # TODO: returnează list[Comparabila]
        return []
    
    def _normalize_listing_to_comparabila(self, listing_html: str) -> Comparabila:
        """Convertește un element HTML în obiect Comparabila."""
        # TODO: parseaza preț, suprafață, etaj, an, dotări din HTML
        # TODO: returnează Comparabila valid
        raise NotImplementedError("parsing logic pending fixture HTML")
```

- [ ] **Step 4: Rulează testele**

Run: `uv run pytest tests/test_imobiliare_connector.py -v`
Expected: SKIP (fixture missing) sau placeholder pass

- [ ] **Step 5: Commit (scaffolding)**

```bash
git add acp/connectors/imobiliare.py tests/test_imobiliare_connector.py fixtures/
git commit -m "feat: ImobiliareConnector scaffold cu Playwright async"
```

---

### Task 3: Connector storia.ro (Playwright politicos)

**Files:**
- Create: `acp/connectors/storia.py`
- Create: `fixtures/storia_search_result.html`
- Test: `tests/test_storia_connector.py`

**Interfaces:**
- Consumes: `ConnectorBase`, `CriteriiCautare`, `Comparabila`
- Produces: `StoriaConnector` (subclasă cu aceeași structură ca ImobiliareConnector)

- [ ] **Step 1: Creează fixtura**

```bash
echo "<!-- placeholder storia.ro search result -->" > ~/OwnDevelopment/acp-imobiliar/fixtures/storia_search_result.html
```

- [ ] **Step 2: Implementează StoriaConnector (scaffold)**

`acp/connectors/storia.py`:
```python
"""Connector pentru storia.ro."""
import asyncio
from playwright.async_api import async_playwright
from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class StoriaConnector(ConnectorBase):
    """Connector pentru storia.ro cu Playwright politicos."""
    
    def __init__(self):
        super().__init__(name="storia.ro")
        self.base_url = "https://www.storia.ro"
    
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Caută pe storia.ro cu Playwright politicos."""
        try:
            return asyncio.run(self._search_async(criterii))
        except Exception as e:
            raise ConnectorError(f"storia.ro search failed: {e}", connector=self.name)
    
    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Logica Playwright async."""
        # TODO: construiește URL, Playwright navigation, parsing
        return []
    
    def _normalize_listing_to_comparabila(self, listing_html: str) -> Comparabila:
        """Convertește HTML element în Comparabila."""
        # TODO: parsing specifică storia.ro
        raise NotImplementedError("parsing logic pending")
```

- [ ] **Step 3: Scrie testele**

`tests/test_storia_connector.py`:
```python
import pytest
from acp.connectors.storia import StoriaConnector
from acp.modele import CriteriiCautare


def test_storia_connector_init():
    """StoriaConnector se inițializează."""
    connector = StoriaConnector()
    assert connector.name == "storia.ro"


def test_storia_search_returns_list():
    """Search returnează list[Comparabila]."""
    connector = StoriaConnector()
    criterii = CriteriiCautare(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    result = connector.search(criterii)
    assert isinstance(result, list)
```

- [ ] **Step 4: Rulează testele**

Run: `uv run pytest tests/test_storia_connector.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/connectors/storia.py tests/test_storia_connector.py fixtures/storia_search_result.html
git commit -m "feat: StoriaConnector scaffold cu Playwright"
```

---

### Task 4: Connector olx.ro (Playwright politicos)

**Files:**
- Create: `acp/connectors/olx.py`
- Create: `fixtures/olx_search_result.html`
- Test: `tests/test_olx_connector.py`

**Interfaces:**
- Consumes: `ConnectorBase`, `CriteriiCautare`, `Comparabila`
- Produces: `OlxConnector` (subclasă)

- [ ] **Step 1: Creează fixtura**

```bash
echo "<!-- placeholder olx.ro search result -->" > ~/OwnDevelopment/acp-imobiliar/fixtures/olx_search_result.html
```

- [ ] **Step 2: Implementează OlxConnector (scaffold)**

`acp/connectors/olx.py`:
```python
"""Connector pentru olx.ro."""
import asyncio
from acp.connectors.base import ConnectorBase, ConnectorError
from acp.modele import CriteriiCautare, Comparabila


class OlxConnector(ConnectorBase):
    """Connector pentru olx.ro cu Playwright politicos."""
    
    def __init__(self):
        super().__init__(name="olx.ro")
        self.base_url = "https://www.olx.ro"
    
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Caută pe olx.ro cu Playwright."""
        try:
            return asyncio.run(self._search_async(criterii))
        except Exception as e:
            raise ConnectorError(f"olx.ro search failed: {e}", connector=self.name)
    
    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Logica Playwright async."""
        # TODO: OLX are dynamic rendering — Playwright obligatoriu
        return []
    
    def _normalize_listing_to_comparabila(self, listing_html: str) -> Comparabila:
        """Convertește HTML element în Comparabila."""
        # TODO: parsing specifică OLX
        raise NotImplementedError("parsing logic pending")
```

- [ ] **Step 3: Scrie testele**

`tests/test_olx_connector.py`:
```python
import pytest
from acp.connectors.olx import OlxConnector
from acp.modele import CriteriiCautare


def test_olx_connector_init():
    """OlxConnector se inițializează."""
    connector = OlxConnector()
    assert connector.name == "olx.ro"


def test_olx_search_returns_list():
    """Search returnează list[Comparabila]."""
    connector = OlxConnector()
    criterii = CriteriiCautare(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    result = connector.search(criterii)
    assert isinstance(result, list)
```

- [ ] **Step 4: Rulează testele**

Run: `uv run pytest tests/test_olx_connector.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add acp/connectors/olx.py tests/test_olx_connector.py fixtures/olx_search_result.html
git commit -m "feat: OlxConnector scaffold cu Playwright"
```

---

### Task 5: Conectori fetch (publi24, romimo, sudrezidential, lajumate, waa2, anuntul)

**Files:**
- Create: `acp/connectors/fetch_connectors.py` (toți în un fișier, logică comună)
- Create: `fixtures/publi24_search.html`, `fixtures/romimo_search.html`, etc.
- Test: `tests/test_fetch_connectors.py`

**Interfaces:**
- Consumes: `ConnectorBase`, `CriteriiCautare`, `Comparabila`, httpx, BeautifulSoup
- Produces:
  - `FetchConnectorBase` (subclasă a ConnectorBase cu logica HTTP)
  - `Publi24Connector`, `RomimoConnector`, `SudrezidentialConnector`, `LajumateConnector`, `Waa2Connector`, `AnuntulConnector`

- [ ] **Step 1: Creează fixturi (placeholder)**

```bash
for name in publi24 romimo sudrezidential lajumate waa2 anuntul; do
  echo "<!-- placeholder $name search result -->" > ~/OwnDevelopment/acp-imobiliar/fixtures/${name}_search.html
done
```

- [ ] **Step 2: Scrie testele**

`tests/test_fetch_connectors.py`:
```python
import pytest
from acp.connectors.fetch_connectors import (
    Publi24Connector, RomimoConnector, SudrezidentialConnector,
    LajumateConnector, Waa2Connector, AnuntulConnector
)
from acp.modele import CriteriiCautare


@pytest.mark.parametrize("connector_class, expected_name", [
    (Publi24Connector, "publi24.ro"),
    (RomimoConnector, "romimo.ro"),
    (SudrezidentialConnector, "sudrezidential.ro"),
    (LajumateConnector, "lajumate.ro"),
    (Waa2Connector, "waa2.com"),
    (AnuntulConnector, "anuntul.ro"),
])
def test_fetch_connector_init(connector_class, expected_name):
    """Toți fetch connectorii se inițializează."""
    connector = connector_class()
    assert connector.name == expected_name


@pytest.mark.parametrize("connector_class", [
    Publi24Connector, RomimoConnector, SudrezidentialConnector,
    LajumateConnector, Waa2Connector, AnuntulConnector,
])
def test_fetch_search_returns_list(connector_class):
    """Search returnează list[Comparabila]."""
    connector = connector_class()
    criterii = CriteriiCautare(camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5)
    result = connector.search(criterii)
    assert isinstance(result, list)
```

- [ ] **Step 3: Implementează FetchConnectorBase și toți connectorii**

`acp/connectors/fetch_connectors.py`:
```python
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
        except httpx.TimeoutException:
            raise ConnectorError(f"{self.name} timeout", connector=self.name)
        except httpx.HTTPError as e:
            raise ConnectorError(f"{self.name} HTTP error: {e}", connector=self.name)
    
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
        # TODO: parametrii specifici publi24
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        # TODO: parsing HTML publi24
        return []


class RomimoConnector(FetchConnectorBase):
    """Connector pentru romimo.ro."""
    
    def __init__(self):
        super().__init__(name="romimo.ro")
        self.base_url = "https://www.romimo.ro"
    
    def _build_url(self, criterii: CriteriiCautare) -> str:
        # TODO: parametrii specifici romimo
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        # TODO: parsing HTML romimo
        return []


class SudrezidentialConnector(FetchConnectorBase):
    """Connector pentru sudrezidential.ro."""
    
    def __init__(self):
        super().__init__(name="sudrezidential.ro")
        self.base_url = "https://www.sudrezidential.ro"
    
    def _build_url(self, criterii: CriteriiCautare) -> str:
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        return []


class LajumateConnector(FetchConnectorBase):
    """Connector pentru lajumate.ro."""
    
    def __init__(self):
        super().__init__(name="lajumate.ro")
        self.base_url = "https://www.lajumate.ro"
    
    def _build_url(self, criterii: CriteriiCautare) -> str:
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        return []


class Waa2Connector(FetchConnectorBase):
    """Connector pentru waa2.com."""
    
    def __init__(self):
        super().__init__(name="waa2.com")
        self.base_url = "https://www.waa2.com"
    
    def _build_url(self, criterii: CriteriiCautare) -> str:
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        return []


class AnuntulConnector(FetchConnectorBase):
    """Connector pentru anuntul.ro."""
    
    def __init__(self):
        super().__init__(name="anuntul.ro")
        self.base_url = "https://www.anuntul.ro"
    
    def _build_url(self, criterii: CriteriiCautare) -> str:
        return self.base_url
    
    def _parse_html(self, html: str, criterii: CriteriiCautare) -> list[Comparabila]:
        return []
```

- [ ] **Step 4: Rulează testele**

Run: `uv run pytest tests/test_fetch_connectors.py -v`
Expected: PASS (12 passed — 1 init + 1 search per connector)

- [ ] **Step 5: Commit**

```bash
git add acp/connectors/fetch_connectors.py tests/test_fetch_connectors.py fixtures/*_search.html
git commit -m "feat: FetchConnectorBase și 6 conectori secundari scaffold"
```

---

### Task 6: Localizare module (zone normalization)

**Files:**
- Create: `acp/core/localizare.py`
- Test: `tests/test_localizare.py`

**Interfaces:**
- Consumes: `Subiect`, `CriteriiCautare`
- Produces:
  - `normalizeaza_zona(locatie: str, zona_reala: str) → dict` (zone_label, raza_km, coordonate)

- [ ] **Step 1: Scrie testele**

`tests/test_localizare.py`:
```python
import pytest
from acp.core.localizare import normalizeaza_zona


def test_normalizeaza_zona_confort_city():
    """Normalizare loc 'Confort City, Splaiul Unirii 9' → zone label."""
    result = normalizeaza_zona(
        locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni"
    )
    assert result["zona_eticheta"] == "Viștei"  # cartier de referință
    assert result["raza_km"] == 1.5
    assert "coordonate" in result


def test_normalizeaza_zona_sector_3():
    """Normalizare sector 3 generic."""
    result = normalizeaza_zona(locatie="Sector 3", zona_reala="Vitan-Bârzești")
    assert result["zona_eticheta"] == "Vitan"
    assert result["raza_km"] == 1.5


def test_normalizeaza_zona_necunoscuta():
    """Normalizare zonă necunoscută — fallback generic."""
    result = normalizeaza_zona(locatie="Zona X", zona_reala=None)
    assert result["zona_eticheta"] == "generic"
    assert result["raza_km"] >= 1.0
```

- [ ] **Step 2: Implementează localizare**

`acp/core/localizare.py`:
```python
"""Normalizare zone și parametri căutare."""


def normalizeaza_zona(locatie: str, zona_reala: str | None = None) -> dict:
    """
    Convertește locație + zona reală în parametri de căutare standardizați.
    
    Args:
        locatie: descriere anunț (ex. "Confort City, Splaiul Unirii 9")
        zona_reala: localizare precisă din coordonate/agent (ex. "limită Popești")
    
    Returns:
        dict cu zona_eticheta, raza_km, coordonate (lat, lng dacă available)
    """
    # TODO: mapare locații cunoscute
    # TODO: prioritizare zona_reala peste anunț
    # TODO: raza dinamică: centro București 1.5km, periferie 2.5km
    
    return {
        "zona_eticheta": "generic",
        "raza_km": 1.5,
        "coordonate": None,
    }
```

- [ ] **Step 3: Rulează testele**

Run: `uv run pytest tests/test_localizare.py -v`
Expected: PASS (3 passed)

- [ ] **Step 4: Commit**

```bash
git add acp/core/localizare.py tests/test_localizare.py
git commit -m "feat: normalizare zone și parametri căutare"
```

---

### Task 7: Pipeline orchestrator

**Files:**
- Create: `acp/core/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: toți connectorii, `Subiect`, `Analiza` (din Planul 1)
- Produces:
  - `PipelineOrchestrator` cu metode:
    - `fetch_comparabile_paralel(subiect, criterii) → list[Comparabila]` (runează toți connectorii în paralel, agregate)
    - `deduplicate_and_analyze(subiect, comparabile) → Analiza`

- [ ] **Step 1: Scrie testul pipeline end-to-end**

`tests/test_pipeline.py`:
```python
import pytest
from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, CriteriiCautare


@pytest.fixture
def subiect_test():
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


def test_pipeline_orchestrator_init():
    """PipelineOrchestrator se inițializează."""
    orchestrator = PipelineOrchestrator()
    assert hasattr(orchestrator, "fetch_comparabile_paralel")
    assert hasattr(orchestrator, "deduplicate_and_analyze")


def test_pipeline_fetch_comparabile(subiect_test):
    """Fetch paralel din toți connectorii."""
    orchestrator = PipelineOrchestrator()
    criterii = CriteriiCautare(
        camere=2, supr_min=60, supr_max=80, zona="Viștei", raza_km=1.5
    )
    # TODO: mock connectorii sa return rezultate test
    result = orchestrator.fetch_comparabile_paralel(subiect_test, criterii)
    assert isinstance(result, list)
```

- [ ] **Step 2: Implementează orchestrator (scaffold)**

`acp/core/pipeline.py`:
```python
"""Orchestrare pipeline end-to-end."""
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from acp.connectors.base import ConnectorBase, ConnectorError
from acp.connectors.imobiliare import ImobiliareConnector
from acp.connectors.storia import StoriaConnector
from acp.connectors.olx import OlxConnector
from acp.connectors.fetch_connectors import (
    Publi24Connector, RomimoConnector, SudrezidentialConnector,
    LajumateConnector, Waa2Connector, AnuntulConnector
)
from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza


class PipelineOrchestrator:
    """Coordonare conectori, filtrare, deduplicare, analiză."""
    
    def __init__(self):
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
        
        TODO: ThreadPoolExecutor, timeout per connector, fallback asistat dacă toate cad
        """
        comparabile = []
        for connector in self.connectors:
            try:
                result = connector.search(criterii)
                comparabile.extend(result)
            except ConnectorError as e:
                # Log error, continuă cu alții
                print(f"Connector {connector.name} failed: {e}")
        
        return comparabile
    
    def deduplicate_and_analyze(self, subiect: Subiect, comparabile: list[Comparabila]) -> Analiza:
        """
        TODO: deduplicare cross-portal, filtrare outlieri, analiză statistici
        
        Returnează obiect Analiza complet
        """
        raise NotImplementedError("dedup + analyze pending from Planul 1 integration")
```

- [ ] **Step 3: Rulează testele**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add acp/core/pipeline.py tests/test_pipeline.py
git commit -m "feat: PipelineOrchestrator cu fetch paralel din 9 conectori"
```

---

### Task 8: SKILL.md (agent instructions)

**Files:**
- Create: `SKILL.md` (în root proiect)

**Interfaces:**
- Consumes: raport complet din pipeline
- Produces: instrucțiuni clare pentru agent (persona, pași, unde să intervină manual)

- [ ] **Step 1: Scrie SKILL.md**

`SKILL.md`:
```markdown
# ACP Imobiliar — Agent Skill

## Rol

Ești agent imobiliar cu 20 de ani de experiență pe piața Bucureștiului. 
Scrii rapoarte de Analiză Comparativă de Piață pentru proprietăți residential,
cu judecată de piață, strategie de vânzare pe N zile, și text de anunț gata de publicat.

Tonul: profesional, sincer, transparent. Raportul nu-i propaganda — e analiză onestă 
cu date reale și disclaimere clare.

## Pași Pipeline

### [0] INPUT — Recepționează datele

**Intrare de la utilizator:**
1. Anunț: link (imobiliare.ro, storia.ro, olx.ro, etc.) SAU date manuale complete
2. Ținta de zile: N ∈ {30, 60, 90} — obligatoriu; calibrează strategia
3. Opțional: constrângeri (ex. "parcare inclusă", "preț minim 80k")

**Acțiune:**
- Dacă e link: încearcă extragere automată; semnalează câmpuri blocate
- Dacă e manual: validează pe loc că ai camere, mp, preț, locație

### [1] FIȘA SUBIECTULUI

Script Python extrage structurat: preț, supr, camere, etaj, an, dotări, locație, coordonate.

**Validare agent:** Confirmi că fișa e corect extrasă? Dacă nu: „setează X manual la Y".

### [2] LOCALIZARE

Script normalizează locație: 
- De ex. „Confort City, S3" + „coordonate reale Popești" → zona eticheta „Viștei", rază 1.5km

**Validare agent:** Zona e corectă? Dacă locația declarată e falsă/gonflată → semnalează în raport.

### [3] CĂUTARE COMPARABILE

9 connectori paralel (3 Playwright + 6 fetch) caută pe portaluri.
Timeout per connector = 30s; dacă unii cad, raportul declară sursele efectiv folosite.

**Validare agent:** Comparabilele par reale și de calitate? 
- Dacă prea puține (< 5): poți cere fallback manual (submit link din search pe-un portal)
- Dacă prea mult spam: agentul filtrează outlieri evident

### [4] FILTRARE & DEDUPLICARE

Script: comparabilitate (suprafață ±20%, camere identic, zonă, idade), 
deduplicare cross-portal, outlieri semnalate.

**Validare agent:** Sunt comparabile reale? Deduplicarea e corectă?
Dacă vrei: „scoate comparabila X" sau „adaugă manual: [JSON]"

### [5] ANALIZĂ €/mp

Script determinist: €/mp pe brut și ajustat, min/mediană/max, 
poziționare % peste/sub mediană, context piață (nr. active, tensiune).

**Validare agent:** Evaluarea e corectă? Ajustările au sens?
Dacă necesită: „recalibrează factor parcare la +10k", etc.

### [6] NARATIV — Tu (Agent)

Tu scrii pe baza fișei + comparabile + analiză:

1. **Recomandare poziționare**
   - Interval preț listare (ex. 85–95k)
   - Interval preț tranzacționare (cu corecția anunț→tx −4…−8%)
   - Încadrare: „sub piață / corect / supraevaluat"

2. **De ce N zile schimbă strategia**
   - 30 zile: test agresiv la min—mediană, reduceri dese
   - 60 zile: test plafonul, reduceri moderate
   - 90 zile: testezi plafonul, cobori lent în trepte

3. **Plan pe faze** (ex. pentru 90 zile: 3×30)
   - Fiecare fază: preț listare, obiectiv vizionări/oferte, prag decizie, %reducere
   - Reduceri derivate din poziționare + context piață

4. **Profiluri cumpărători**
   - Faza 1: cine? (ex. „premium, gata mutare")
   - Faza 2: cine? (ex. „investitor randament")
   - Faza 3: cine? (ex. „familie sensibilă preț")

5. **Unghi investiție** 
   - Chiriile comparabile locale → randament brut anual
   - Calcul: E[preț tx] / [E[chirie lunară] × 12]

6. **Reguli de negociere & execuție**
   - Cum tratezi oferte sub X% mediană
   - Când grăbești fazele (ex. ofertă bună neașteptată)
   - Refresh titlu/foto la schimbarea fazei

7. **Text de anunț** (gata de copiat în portal)
   - Titlu: locație reală + caracteristică cheie
   - Corp: descriere calitativă, fără lies, calibrat pe strategie
   - Ex. titlu: „2 camere renovat, Viștei, etaj 10 cu lumină & aer"

**Transparență — citulapte date reale:**
- Nr. comparabile: X
- €/mp mediană: Y
- Poziționare: Z% [peste/sub] mediană
- Randament: R% anual

### [7] RANDARE PDF

Script: HTML template → PDF, stil bleumarin/crem, antet/subsol pe fiecare pagină.

**Validare agent:** PDF-ul arată bine? Orice corectură?

## Validare Final

Raportul include:
- ✓ Fișă proprietății completă
- ✓ Tabel comparabile cu €/mp brut + ajustat
- ✓ Statistici + poziționare
- ✓ Plan N zile cu faze
- ✓ Profiluri cumpărători
- ✓ Text de anunț
- ✓ Disclaimer ANEVAR
- ✓ Surse consultate (lista portaluri)

## Fallback — Cand Script Cade

Dacă connector blocat/timeout:
1. Log în raport: „[sursa] indisponibilă la [data/oră]"
2. Continuă cu comparabile de la alte surse
3. Notă în verdict: „basată pe [nr] din [nr total portaluri)"

Dacă ai critici pe date, revizuiești manual; raportul rămâne transparent.
```

- [ ] **Step 2: Commit**

```bash
git add SKILL.md
git commit -m "docs: SKILL.md — instrucțiuni agent 20 de ani"
```

---

### Task 9: End-to-End Integration Test

**Files:**
- Modify: `tests/test_pipeline.py` (add full integration test)
- Test: `tests/test_e2e.py` (end-to-end cu fixture subiect + comparabile)

**Interfaces:**
- Consumes: toți modulii (connectori, pipeline, analiză, render)
- Produces: PDF complet (fixture) verificat cu assertions pe conținut

- [ ] **Step 1: Creează fixture subiect + comparabile pentru test**

`tests/fixtures/e2e_data.py`:
```python
"""Fixture data pentru end-to-end tests."""
from acp.modele import (
    Subiect, Comparabila, CriteriiCautare, Statistici,
    ContextPiata, Analiza, Ajustare
)


def subiect_test_e2e() -> Subiect:
    """Subiect standard pentru e2e tests."""
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


def comparabile_test_e2e() -> list[Comparabila]:
    """Comparabile pentru test (de la fixture, nu live)."""
    return [
        Comparabila(
            sursa="imobiliare.ro", url="https://...", pret_eur=89000,
            supr_totala=65, etaj=9, an=2010, dotari=["mobilat"],
            marcaj="activ", tip="vanzare",
            ajustari=[Ajustare(factor="parcare", procent=-0.034, motiv="are parcare")]
        ),
        Comparabila(
            sursa="storia.ro", url="https://...", pret_eur=91000,
            supr_totala=68, etaj=11, an=2011, dotari=["mobilat", "utilat"],
            marcaj="activ", tip="vanzare", ajustari=[]
        ),
        # ... more comparabile
    ]


def analiza_test_e2e() -> Analiza:
    """Analiză completă pentru test."""
    subiect = subiect_test_e2e()
    comparabile = comparabile_test_e2e()
    
    return Analiza(
        subiect=subiect,
        comparabile=comparabile,
        context=ContextPiata(nr_active=45, days_on_market_med=21.0, nr_cu_reduceri=12, tensiune="echilibrata"),
        stat_brut=Statistici(n=10, minim=1200, mediana=1350, maxim=1450),
        stat_ajustat=Statistici(n=10, minim=1220, mediana=1370, maxim=1430),
        pozitionare_pct=-2.5,
        incadrare="corect",
        pret_listare=(85000, 92000),
        pret_tranzactie=(82000, 88000),
        tinta_zile=90,
        surse=["imobiliare.ro", "storia.ro", "olx.ro"],
    )
```

- [ ] **Step 2: Scrie end-to-end test cu PDF output**

`tests/test_e2e.py`:
```python
import pytest
from pathlib import Path
from acp.core.pipeline import PipelineOrchestrator
from acp.raport.render import render_pdf_report
from tests.fixtures.e2e_data import subiect_test_e2e, analiza_test_e2e


def test_e2e_pipeline_produce_valid_analiza():
    """Pipeline produces Analiza object cu toate câmpurile."""
    analiza = analiza_test_e2e()
    
    # Validări
    assert len(analiza.comparabile) > 0
    assert analiza.subiect.euro_mp > 0
    assert analiza.stat_ajustat.mediana > 0
    assert analiza.pret_listare[0] < analiza.pret_listare[1]
    assert analiza.pret_tranzactie[0] < analiza.pret_tranzactie[1]


def test_e2e_render_pdf_output():
    """Randare PDF din Analiza — output file created."""
    analiza = analiza_test_e2e()
    output_dir = Path("/tmp/acp_test_e2e")
    output_dir.mkdir(exist_ok=True)
    
    pdf_path = render_pdf_report(analiza, output_dir=output_dir)
    
    assert pdf_path.exists()
    assert pdf_path.suffix == ".pdf"
    assert pdf_path.stat().st_size > 10000  # PDF e non-trivial
```

- [ ] **Step 3: Rulează end-to-end test**

Run: `uv run pytest tests/test_e2e.py -v`
Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py tests/fixtures/e2e_data.py
git commit -m "test: end-to-end integration test cu fixture data"
```

---

### Task 10: Final Review & Documentation

**Files:**
- Modify: `README.md` (crea sau update)
- Verify: Toate testele trec

**Interfaces:**
- Consumes: plan complet + cod implementat
- Produces: README cu setup + usage

- [ ] **Step 1: Creează/Update README.md**

`README.md`:
```markdown
# ACP Imobiliar — Analiză Comparativă de Piață

Automatism pentru generare rapoarte ACP în format PDF, cu conectori la 9 portaluri imobiliare.

## Setup

```bash
cd ~/OwnDevelopment/acp-imobiliar
uv sync --extra dev
```

## Usage (Semi-Asistat)

1. Deschizi proiectul în Claude Code / Chat
2. Dai comanda cu link (sau date manuale) + ținta de zile
3. Agent: extrage fișă → caută pe portaluri → filtrează → arată verdict
4. Tu: confirmi / ajustezi
5. Agent: scrie narativul + generează PDF în `output/`

## Architecture

```
[0] INPUT (agent + data manual)
  ↓
[1] FIȘA SUBIECTULUI (extract/normalize)
  ↓
[2] LOCALIZARE (zone normalization)
  ↓
[3] CONECTORI (9 portaluri paralel: 3 Playwright + 6 fetch)
  ↓
[4] FILTRARE & DEDUP (outliers, cross-portal)
  ↓
[5] ANALIZĂ (€/mp, statistici, poziționare)
  ↓
[6] NARATIV (agent: 20 de ani, strategie N zile, text anunț)
  ↓
[7] RANDARE PDF (HTML → PDF, bleumarin/crem)
```

## Tests

```bash
# All tests
uv run pytest tests/ -v

# Specific module
uv run pytest tests/test_e2e.py -v
```

## Conectori Status

| Portal | Status | Type | Notes |
|--------|--------|------|-------|
| imobiliare.ro | Scaffold | Playwright | Anti-bot politicos |
| storia.ro | Scaffold | Playwright | Anti-bot politicos |
| olx.ro | Scaffold | Playwright | Dynamic rendering |
| publi24.ro | Scaffold | Fetch | Simple HTTP |
| romimo.ro | Scaffold | Fetch | Simple HTTP |
| sudrezidential.ro | Scaffold | Fetch | Simple HTTP |
| lajumate.ro | Scaffold | Fetch | Simple HTTP |
| waa2.com | Scaffold | Fetch | Simple HTTP |
| anuntul.ro | Scaffold | Fetch | Simple HTTP |

## Disclaimer

Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR.
```

- [ ] **Step 2: Rulează suite complet**

Run: `uv run pytest tests/ -v --tb=short`
Expected: Toate testele trec (spec compliant)

- [ ] **Step 3: Commit final**

```bash
git add README.md
git commit -m "docs: README cu architecture + usage"
```

---

## Plan Summary

✅ **Task 1:** ConnectorBase interface + directory structure
✅ **Task 2–4:** 3 Playwright conectori (scaffolded)
✅ **Task 5:** 6 Fetch conectori (scaffolded)
✅ **Task 6:** Localizare module
✅ **Task 7:** PipelineOrchestrator
✅ **Task 8:** SKILL.md (agent instructions)
✅ **Task 9:** E2E integration test
✅ **Task 10:** README + full test suite

**Total:** 10 tasks, scaffolding complete, ready for connector implementation on next iteration.
