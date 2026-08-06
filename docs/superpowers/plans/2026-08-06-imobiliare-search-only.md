# imobiliare.ro search-only Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** imobiliare.ro contribuie comparabile doar din pagina de căutare (1 încărcare prin Google Chrome real, headed), fără pagini de detaliu; excluderea subiectului se face pe metadata, fără fetch.

**Architecture:** Un modul nou `acp/connectors/real_chrome.py` încarcă o pagină prin Chrome real (`channel="chrome"`, headed, profil efemer) trecând de Cloudflare. `ImobiliareConnector._fetch_html` (folosit doar de search) delegă la el; metodele de detaliu se elimină, deci pipeline-ul sare imobiliare la îmbogățire. Pipeline-ul exclude subiectul imobiliare pe metadata (`fallback_metadata_subiect=True`), fără să-i descarce pozele.

**Tech Stack:** Python 3, Playwright async (`channel="chrome"`), Pydantic, pytest. Fără dependențe noi.

## Global Constraints

- **Fără dependențe Python noi.** Chrome real via `channel="chrome"` (Playwright deja instalat). NU se folosește patchright/Firefox/WebKit (instalate în timpul explorării — de dezinstalat, vezi Task 3).
- **imobiliare = search-only:** ZERO încărcări `/oferta/` (nici detaliu, nici poze). Doar 1 încărcare de search prin Chrome real.
- **Headed obligatoriu** (`headless=False`) — headless-ul e blocat de Cloudflare la orice engine (testat). Cerință de runtime: Google Chrome instalat; lipsă/eșec → `ConnectorError`, orchestratorul continuă.
- **Profil efemer** (`tempfile.mkdtemp` per încărcare, șters în `finally`).
- Ajustările pentru comparabilele imobiliare se fac pe **datele din card** (etaj/an/suprafață + stare/structură/încălzire/parcare din text); doar dotările din detaliu (mobilat/AC/balcon/boxă) nu se aplică (`detalii_complete=False`).
- Excludere subiect imobiliare = **metadata** (`fallback_metadata_subiect=True`). Fără url-match.
- olx/storia/romimo rămân neatinse. Suita rămâne verde.
- Suita completă se rulează cu `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -q` (WeasyPrint pe macOS).

---

## File Structure

- `acp/connectors/real_chrome.py` — **nou**: `chrome_disponibil()`, `_in_challenge()`, `fetch_html_async()`, `fetch_html()`.
- `acp/connectors/imobiliare.py` — **modificat**: `search` verifică Chrome; `_fetch_html` delegă la `real_chrome`; se scot `fetch_detaliu`/`fetch_detaliu_text` + importurile Playwright nefolosite.
- `acp/core/pipeline.py` — **modificat**: `_este_imobiliare` + mod de excludere subiect pentru imobiliare.
- Teste: `tests/test_real_chrome.py` (nou), `tests/test_imobiliare_connector.py` (modificat), `tests/test_detaliu_fetch.py` (modificat), `tests/test_pipeline_imobiliare_subiect.py` (nou).

---

### Task 1: Modul `acp/connectors/real_chrome.py`

**Files:**
- Create: `acp/connectors/real_chrome.py`
- Test: `tests/test_real_chrome.py`

**Interfaces:**
- Produces:
  - `chrome_disponibil() -> bool` (cache-uit per proces)
  - `_in_challenge(title: str) -> bool`
  - `async fetch_html_async(url, user_agent, timeout_ms=45000, scroll=6, challenge_sec=15) -> str`
  - `fetch_html(url, user_agent, ...) -> str` (wrapper sincron pentru scripturi)

- [ ] **Step 1: Write the failing test**

Create `tests/test_real_chrome.py`:

```python
from acp.connectors import real_chrome


def test_in_challenge_detecteaza_pagina_de_moment():
    assert real_chrome._in_challenge("Doar un moment...") is True
    assert real_chrome._in_challenge("Just a moment...") is True


def test_in_challenge_fals_pe_pagina_reala():
    assert real_chrome._in_challenge("Vânzare apartamente 2 camere Colentina") is False
    assert real_chrome._in_challenge("") is False
    assert real_chrome._in_challenge(None) is False


def test_chrome_disponibil_intoarce_bool():
    # nu lansa browser în test: doar verifică contractul de tip (rezultat cache-uit)
    real_chrome._disponibil_cache = True
    assert real_chrome.chrome_disponibil() is True
    real_chrome._disponibil_cache = False
    assert real_chrome.chrome_disponibil() is False
    real_chrome._disponibil_cache = None  # reset pentru alte teste
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_real_chrome.py -v`
Expected: FAIL (`ModuleNotFoundError: acp.connectors.real_chrome`).

- [ ] **Step 3: Implement `acp/connectors/real_chrome.py`**

```python
"""Fetch prin Google Chrome REAL (channel='chrome', headed) — trece Cloudflare pe imobiliare.ro.

imobiliare.ro pune un Cloudflare managed challenge pe search/oferta pe care NICIUN browser
headless nu-l trece (testat exhaustiv: Chromium/Chrome/Firefox/WebKit/patchright — toate
primesc soft-block sau rămân în challenge). Doar Chrome real VIZIBIL (headed) ajunge la
conținut. Profil EFEMER (temp dir per apel) evită flag-uirea profilului; la 1 încărcare/
analiză reputația rămâne curată.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile

from playwright.async_api import async_playwright

_CHALLENGE_MARKER = "moment"  # titlul paginii de challenge: "Doar un moment..." / "Just a moment..."
_disponibil_cache: bool | None = None


def _in_challenge(title: str | None) -> bool:
    """True dacă titlul paginii e încă pagina de challenge Cloudflare."""
    return _CHALLENGE_MARKER in (title or "").lower()


def chrome_disponibil() -> bool:
    """True dacă Google Chrome (channel='chrome') poate fi lansat. Cache-uit per proces."""
    global _disponibil_cache
    if _disponibil_cache is None:
        async def _probe():
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=True)
                await browser.close()
        try:
            asyncio.run(_probe())
            _disponibil_cache = True
        except Exception:
            _disponibil_cache = False
    return _disponibil_cache


async def fetch_html_async(url: str, user_agent: str, timeout_ms: int = 45000,
                           scroll: int = 6, challenge_sec: int = 15) -> str:
    """Deschide `url` cu Chrome real (headed, profil efemer), trece challenge-ul și
    întoarce HTML-ul. Ridică RuntimeError dacă challenge-ul nu se rezolvă în `challenge_sec`."""
    profil = tempfile.mkdtemp(prefix="acp_chrome_")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            profil,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1366, "height": 900},
            locale="ro-RO",
            user_agent=user_agent,
        )
        try:
            page = await ctx.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            trecut = False
            for _ in range(challenge_sec):
                await page.wait_for_timeout(1000)
                if not _in_challenge(await page.title()):
                    trecut = True
                    break
            if not trecut:
                raise RuntimeError("Cloudflare challenge nerezolvat (profil/IP flag-uit)")
            await page.wait_for_timeout(3000)
            for _ in range(scroll):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(600)
            return await page.content()
        finally:
            await ctx.close()
            shutil.rmtree(profil, ignore_errors=True)


def fetch_html(url: str, user_agent: str, timeout_ms: int = 45000,
               scroll: int = 6, challenge_sec: int = 15) -> str:
    """Wrapper sincron (pentru scripturi ad-hoc). În connector se folosește fetch_html_async."""
    return asyncio.run(fetch_html_async(url, user_agent, timeout_ms, scroll, challenge_sec))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_real_chrome.py -v`
Expected: PASS (3 passed).

Notă: `fetch_html_async`/`chrome_disponibil` (partea de browser) se validează live (Task 3, secțiunea Live), nu în unit — cer Chrome real + navigare.

- [ ] **Step 5: Commit**

```bash
git add acp/connectors/real_chrome.py tests/test_real_chrome.py
git commit -m "feat(real_chrome): fetch prin Chrome real headed (trece Cloudflare)"
```

---

### Task 2: `ImobiliareConnector` — search prin Chrome real, fără detaliu

**Files:**
- Modify: `acp/connectors/imobiliare.py` (`search` la 69-95, `_fetch_html` la 131-162, metode detaliu 311-317, importuri 25-26)
- Modify: `tests/test_imobiliare_connector.py` (scoate testele de status-branching 343-457; păstrează testele de retry)
- Modify: `tests/test_detaliu_fetch.py` (testul de delegare imobiliare → olx)

**Interfaces:**
- Consumes: `acp.connectors.real_chrome.{chrome_disponibil, fetch_html_async}` (Task 1).
- Produces: `ImobiliareConnector.search` folosește Chrome real; NU mai expune `fetch_detaliu`/`fetch_detaliu_text`.

- [ ] **Step 1: Update the failing tests (connector)**

In `tests/test_imobiliare_connector.py`:

**(a)** ȘTERGE testele de status-branching și helperii lor Playwright falși — de la `class _FakeResponse:` (linia ~343) până la finalul lui `test_fetch_html_status_200_întoarce_conținutul_paginii` (linia ~457), inclusiv `_fake_async_playwright` și cele 3 teste `test_fetch_html_403…`, `test_fetch_html_5xx…`, `test_fetch_html_status_200…`. (Calea veche bundle-Chromium cu branching pe status dispare — `_fetch_html` delegă acum la real_chrome.)

**(b)** PĂSTREAZĂ testele de retry (`test_fetch_html_with_retry_reincearcă…`, `test_fetch_html_with_retry_ridică_connector_error…`) — ele mock-uiesc `_fetch_html` și testează wrapper-ul tenacity, independent de corpul real.

**(c)** ADAUGĂ, la finalul fișierului, două teste noi pentru calea Chrome real:

```python
def test_search_ridica_connector_error_daca_chrome_indisponibil(monkeypatch):
    """Fără Google Chrome real, search ridică ConnectorError (orchestratorul continuă)."""
    from acp.connectors import real_chrome
    monkeypatch.setattr(real_chrome, "chrome_disponibil", lambda: False)
    connector = ImobiliareConnector(min_delay_seconds=0)
    crit = CriteriiCautare(camere=2, supr_min=40, supr_max=80, zona="colentina")
    with pytest.raises(ConnectorError):
        connector.search(crit)


def test_fetch_html_mapeaza_esecul_real_chrome_la_connector_error(monkeypatch):
    """Dacă real_chrome eșuează (challenge nerezolvat), _fetch_html ridică ConnectorError."""
    from acp.connectors import real_chrome

    async def _boom(url, user_agent, **kw):
        raise RuntimeError("Cloudflare challenge nerezolvat")
    monkeypatch.setattr(real_chrome, "fetch_html_async", _boom)
    connector = ImobiliareConnector(min_delay_seconds=0)
    with pytest.raises(ConnectorError):
        asyncio.run(connector._fetch_html("https://www.imobiliare.ro/x"))
```

(`CriteriiCautare` e deja importat în fișier; dacă nu, adaugă `from acp.modele import CriteriiCautare`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_imobiliare_connector.py -v`
Expected: FAIL — noile teste eșuează (`_fetch_html` încă folosește Chromium bundle; `real_chrome` neatins).

- [ ] **Step 3: Rewrite `_fetch_html` + `search` guard în `acp/connectors/imobiliare.py`**

Înlocuiește metoda `_fetch_html` (liniile 131-162) cu:

```python
    async def _fetch_html(self, url: str) -> str:
        """Încarcă pagina prin Google Chrome REAL (headed) — singurul care trece Cloudflare.

        Chromium bundle (headless SAU headed) primește soft-block pe imobiliare.ro; doar
        Chrome real vizibil ajunge la anunțuri. Profil efemer (în real_chrome), 1 încărcare.
        """
        from acp.connectors import real_chrome
        await self._respect_rate_limit()
        try:
            return await real_chrome.fetch_html_async(url, USER_AGENT)
        except Exception as e:
            raise ConnectorError(
                f"imobiliare.ro Chrome real: {e}", connector=self.name
            ) from e
        finally:
            self._last_request_monotonic = time.monotonic()
```

În `search` (liniile 81-95), adaugă verificarea de disponibilitate Chrome la început, înaintea `try`:

```python
    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """..."""
        from acp.connectors import real_chrome
        if not real_chrome.chrome_disponibil():
            raise ConnectorError(
                "imobiliare.ro: Google Chrome real indisponibil (channel='chrome')",
                connector=self.name,
            )
        try:
            return asyncio.run(
                asyncio.wait_for(self._search_async(criterii), timeout=SEARCH_TIMEOUT_SECONDS)
            )
        except ConnectorError:
            raise
        except asyncio.TimeoutError as e:
            raise ConnectorError(
                f"imobiliare.ro search a depășit timeout-ul de {SEARCH_TIMEOUT_SECONDS}s",
                connector=self.name,
            ) from e
        except Exception as e:
            raise ConnectorError(f"imobiliare.ro search failed: {e}", connector=self.name) from e
```

(Doar linia cu `from acp.connectors import real_chrome` + blocul `if not real_chrome.chrome_disponibil(): raise ...` sunt noi; restul lui `search` rămâne identic. Păstrează docstring-ul existent.)

- [ ] **Step 4: Remove detail methods + unused imports**

Șterge metodele `fetch_detaliu` și `fetch_detaliu_text` de pe `ImobiliareConnector` (liniile 311-317). Șterge importurile Playwright acum nefolosite (liniile 25-26):

```python
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
```

(Verifică: `async_playwright`/`PlaywrightTimeoutError` nu mai apar nicăieri în `imobiliare.py`. `tenacity`, `asyncio`, `re`, `time`, `unicodedata`, `bs4` rămân.)

- [ ] **Step 5: Update the delegation test in `tests/test_detaliu_fetch.py`**

Testul `test_connector_deleaga_fetch_detaliu_cu_user_agent_propriu` folosește `ImobiliareConnector` (care nu mai are `fetch_detaliu`). Schimbă-l pe `OlxConnector` (care păstrează delegarea la `detaliu_fetch.fetch_detaliu`):

```python
def test_connector_deleaga_fetch_detaliu_cu_user_agent_propriu(monkeypatch):
    from acp.connectors.olx import OlxConnector, USER_AGENT
    apeluri = {}

    def _fake_fetch(url, user_agent, timeout_ms=30000, retries=1):
        apeluri["url"] = url
        apeluri["ua"] = user_agent
        return "ok", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "fetch_detaliu", _fake_fetch)
    conn = OlxConnector()
    text, poze = conn.fetch_detaliu("https://olx.ro/y")
    assert text == "ok"
    assert poze == ["https://cdn.x.ro/foto-1.jpg"]
    assert apeluri["url"] == "https://olx.ro/y"
    assert apeluri["ua"] == USER_AGENT
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_imobiliare_connector.py tests/test_detaliu_fetch.py -v`
Expected: PASS (testele de retry + cele 2 noi trec; delegarea olx trece).

- [ ] **Step 7: Run full suite (regression)**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add acp/connectors/imobiliare.py tests/test_imobiliare_connector.py tests/test_detaliu_fetch.py
git commit -m "feat(imobiliare): search prin Chrome real, fara pagini de detaliu"
```

---

### Task 3: Pipeline — excludere subiect imobiliare pe metadata

**Files:**
- Modify: `acp/core/pipeline.py` (blocul `dedup_poze`, liniile 244-265)
- Test: `tests/test_pipeline_imobiliare_subiect.py` (nou)

**Interfaces:**
- Consumes: `confirma_si_dedup(..., fallback_metadata_subiect=...)` (existent, neschimbat).
- Produces: `deduplicate_and_analyze` NU descarcă pozele subiectului când subiectul e pe imobiliare; setează `fallback_metadata=True` → subiect+geamăn excluși pe metadata.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_imobiliare_subiect.py`:

```python
from acp.core.pipeline import PipelineOrchestrator, _este_imobiliare
from acp.modele import Subiect, Comparabila


def test_este_imobiliare():
    assert _este_imobiliare("https://www.imobiliare.ro/oferta/x-123") is True
    assert _este_imobiliare("https://www.olx.ro/d/oferta/y.html") is False
    assert _este_imobiliare(None) is False


def _comp(sursa, url, pret, supr, etaj=2, camere=2):
    return Comparabila(sursa=sursa, url=url, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, camere=camere, tip="vanzare", an=1980)


def test_subiect_imobiliare_exclus_pe_metadata_fara_fetch_poze(monkeypatch):
    """Subiect pe imobiliare: NU se descarcă poze subiect; subiect+geamăn excluși pe metadata."""
    orch = PipelineOrchestrator()
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://www.imobiliare.ro/oferta/x-275238880")
    propriu = _comp("imobiliare.ro", "https://www.imobiliare.ro/oferta/x-275238880", 108000, 59)
    geaman = _comp("imobiliare.ro", "https://www.imobiliare.ro/oferta/y-275736626", 108000, 60)
    normal = _comp("olx.ro", "https://www.olx.ro/d/oferta/z.html", 95000, 58, etaj=7)
    comparabile = [propriu, geaman, normal]

    # dacă s-ar încerca fetch poze subiect, testul ar pica (nu trebuie apelat)
    def _boom(url, ua):
        raise AssertionError("nu trebuie descărcate poze pentru subiect imobiliare")
    monkeypatch.setattr("acp.connectors.detaliu_fetch.fetch_detaliu", _boom)
    # fetch_poze pentru comparabile (olx) nu are candidați aici → nu se apelează pe imobiliare
    monkeypatch.setattr("acp.core.pipeline.construieste_fetch_poze",
                        lambda ua, cache=None, **kw: (lambda c: []))

    analiza = orch.deduplicate_and_analyze(subiect, comparabile, imbogateste=False, dedup_poze=True)

    urls = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://www.imobiliare.ro/oferta/x-275238880" not in urls  # propriul anunț exclus
    assert "https://www.imobiliare.ro/oferta/y-275736626" not in urls  # geamănul exclus (metadata)
    assert "https://www.olx.ro/d/oferta/z.html" in urls                # normalul rămâne
```

- [ ] **Step 2: Run test to verify it fails**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_pipeline_imobiliare_subiect.py -v`
Expected: FAIL (`_este_imobiliare` nu există; iar codul actual ar încerca `fetch_detaliu` pe subiect imobiliare → AssertionError).

- [ ] **Step 3: Add `_este_imobiliare` + update the dedup_poze block in `acp/core/pipeline.py`**

Adaugă helperul la nivel de modul (după importuri, înaintea clasei `PipelineOrchestrator`):

```python
def _este_imobiliare(url: str | None) -> bool:
    """True dacă URL-ul e un anunț imobiliare.ro (sursă search-only, fără poze)."""
    return bool(url) and "imobiliare.ro" in url
```

Înlocuiește începutul blocului `if dedup_poze:` (liniile 244-254) — de la `subiect_hashes: list[int] = []` până înainte de `fetch_poze = construieste_fetch_poze(...)` — cu:

```python
        if dedup_poze:
            subiect_hashes: list[int] = []
            if subiect.url and _este_imobiliare(subiect.url):
                # Subiect search-only (imobiliare): NU descărcăm poze; excludere pe metadata.
                fallback_metadata = True
            elif subiect.url:
                _, poze_subiect = detaliu_fetch.fetch_detaliu(subiect.url, UA_DETALIU)
                subiect_hashes = hashuri_din_urls(poze_subiect, UA_DETALIU)
                # url dat dar fetch eșuat → NU excludem agresiv pe metadata (fix existent)
                fallback_metadata = bool(subiect_hashes)
                if not subiect_hashes:
                    logger.warning(
                        "Subiect are url dar fetch-ul pozelor a esuat — sar excluderea "
                        "subiectului (fara fallback pe metadata)"
                    )
            else:
                fallback_metadata = True  # date manuale, fără url
            fetch_poze = construieste_fetch_poze(UA_DETALIU, cache=CacheHashuri())
```

Notă: restul blocului (`confirma_si_dedup(..., fallback_metadata_subiect=fallback_metadata)`, eliminarea prin `id()`, log-ul) rămâne neschimbat (liniile 256-265). Verifică: `fallback_metadata` se definește pe toate ramurile.

Corecție de logică inclusă: pentru subiect non-imobiliare cu fetch reușit, `fallback_metadata = bool(subiect_hashes)` (True dacă avem hash-uri) — dar când avem hash-uri, calea pe poze le folosește oricum și fallback-ul nu se atinge; când fetch eșuează (`subiect_hashes` gol), `fallback_metadata=False` păstrează comportamentul fix-ului anterior (nu excludem agresiv). Echivalent funcțional cu `subiect.url is None` de dinainte pentru cazurile non-imobiliare, dar explicit.

- [ ] **Step 4: Run test to verify it passes**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest tests/test_pipeline_imobiliare_subiect.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Run full suite (regression)**

Run: `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run pytest -q`
Expected: PASS. (Verifică în special `tests/test_pipeline_dedup_poze.py` — subiect olx cu poze rămâne funcțional.)

- [ ] **Step 6: Curăță dependențele de explorare**

patchright/Firefox/WebKit au fost instalate în timpul investigației și NU sunt folosite de E. Dezinstalează-le pentru un mediu curat:

```bash
uv pip uninstall patchright
```

(Firefox/WebKit sunt browsere Playwright în cache — opționale de șters; nu afectează repo-ul. Chrome real folosește `channel="chrome"`, browserul de sistem, nu unul din cache.)

- [ ] **Step 7: Commit**

```bash
git add acp/core/pipeline.py tests/test_pipeline_imobiliare_subiect.py
git commit -m "feat(pipeline): excludere subiect imobiliare pe metadata (fara fetch poze)"
```

---

## Live (manual, după implementare — pe IP proaspăt)

Nu e un pas automat de test (cere Chrome real + IP necompromis). De rulat manual pentru validare end-to-end:

```
ACP: analiză Colentina 2-camere, subiect 275238880.
Așteptat: fereastră Chrome ~câteva secunde → imobiliare ~26 comps din 1 încărcare;
subiect (275238880) + geamăn (275736626) excluși pe metadata; zero încărcări /oferta/;
olx/storia/romimo contribuie normal.
```

---

## Self-Review

**Spec coverage:**
- Componenta 1 (real_chrome.py) → Task 1. ✅
- Componenta 2 (imobiliare search Chrome real + fără detaliu) → Task 2. ✅
- Componenta 3 (pipeline excludere subiect pe metadata) → Task 3. ✅
- „Fără url-match" → Task 3 folosește doar `fallback_metadata_subiect` (motorul neschimbat). ✅
- Ajustări pe date de card → nemodificate (comparabilele imobiliare rămân `detalii_complete=False`, numericele + card-text se aplică; îmbogățirea le sare). ✅
- Degradare grațioasă (fără Chrome → ConnectorError) → Task 2 Step 3 + test. ✅
- Curățare patchright/FF/WebKit → Task 3 Step 6. ✅

**Placeholder scan:** fără TBD/TODO; tot codul e complet.

**Type consistency:** `fetch_html_async(url, user_agent, ...) -> str` folosit de `_fetch_html`; `chrome_disponibil() -> bool` folosit de `search` + test; `_este_imobiliare(url) -> bool` folosit în pipeline + test; `confirma_si_dedup(..., fallback_metadata_subiect: bool)` neschimbat, apelat cu `fallback_metadata`. Consistent.

**Deviație conștientă față de spec:** spec-ul (Componenta 2) arăta `_fetch_html` cu `asyncio.to_thread` + `chrome_disponibil()` în `_fetch_html`. Planul rafinează: `fetch_html_async` (așteptat direct în bucla search-ului, fără thread — evită firele necancelabile) și mută `chrome_disponibil()` în `search()` (o singură probă/căutare, cache-uită). Echivalent ca efect, mai curat.
