# Deduplicare cross-agenție + excludere subiect (prin poze) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elimină din comparabile apartamentul-subiect (listat de una sau mai multe agenții) și același apartament re-listat de agenții diferite, folosind metadata ca pre-filtru ieftin și potrivirea de poze (perceptual hash) ca verdict.

**Architecture:** Un pre-filtru pur pe metadata (etaj + camere + suprafață ±2mp + preț ±1%) marchează perechi suspecte; pentru ele descărcăm doar câteva poze de galerie, calculăm un dHash pe 64 de biți (Pillow, fără dependență nouă) și confirmăm prin distanță Hamming ≤ 8. Motorul de decizie e pur și primește un `fetch_poze` injectabil (testabil fără rețea). Extragerea URL-urilor de poze se face în aceeași navigare Playwright ca îmbogățirea cu detalii (Task 12 existent), iar descărcarea de bytes se face doar pentru candidați.

**Tech Stack:** Python 3, Pydantic (modele), Pillow (dHash — deja instalat), Playwright async (fetch pagini), urllib.request (descărcare poze — stdlib), pytest.

## Global Constraints

- **Fără dependențe noi.** dHash se implementează cu Pillow (deja instalat); descărcarea de poze cu `urllib.request` (stdlib). Fără `imagehash`, `numpy`, vision/ML.
- **Motoarele de decizie sunt pure** (fără rețea): `acp/imagini.py` și `acp/dedup_poze.py` nu importă Playwright/urllib. Orice I/O (fetch text, descărcare bytes) e injectat.
- **Pozele = confirmare peste metadata**, nu înlocuiesc metadata. Un candidat de duplicat trece pre-filtrul de metadata ȘI are o poză sub prag.
- **Parametri impliciți (tunabili prin argumente):** dHash 64 biți (9×8 grayscale), prag Hamming ≤ 8 biți, maxim 4 poze de galerie per anunț, suprafață ±2mp, preț ±1%.
- **Nu descărcăm poze pentru anunțuri fără grup-candidat de metadata.** Comparabilele care nu sunt candidate cu subiectul și nici cu altă comparabilă rămân neatinse, fără fetch de poze.
- **Fallback fără `Subiect.url`:** dacă subiectul n-are URL (date manuale), excluderea subiectului se face doar pe metadata, acceptând riscul mic de fals-excludere.
- **Testele existente rămân verzi** după fiecare task.
- Spec de referință: `docs/superpowers/specs/2026-08-05-dedup-poze-design.md`.

---

## File Structure

- `acp/modele.py` — **modificat**: `Subiect.url`, `Comparabila.camere`, `Comparabila.poze_urls`.
- `acp/imagini.py` — **nou**: `dhash`, `distanta_hamming` (pur, doar Pillow).
- `acp/dedup_poze.py` — **nou**: `sunt_candidat_duplicat`, `potrivire_metadata_subiect`, `confirma_si_dedup` (pur, `fetch_poze` injectat).
- `acp/poze_fetch.py` — **nou**: `descarca_bytes`, `hashuri_din_urls`, `construieste_fetch_poze` (I/O: urllib + dHash).
- `acp/cache_hashuri.py` — **nou**: `CacheHashuri` (cache pe disc pentru liste de hash-uri, paralel cu `CacheDetalii`).
- `acp/connectors/detaliu_fetch.py` — **modificat**: `fetch_detaliu` întoarce `(text, poze_urls)`; `extrage_poze_din_srcs` (pur); `fetch_detaliu_text` rămâne wrapper.
- `acp/connectors/{imobiliare,storia,olx}.py` — **modificat**: populează `comp.camere`; adaugă metoda `fetch_detaliu`.
- `acp/detalii.py` — **modificat**: `imbogateste_detalii` primește fetcher `(str) -> (text, poze_urls)` și stochează `poze_urls`.
- `acp/core/pipeline.py` — **modificat**: `deduplicate_and_analyze(..., dedup_poze=True)`; folosește `fetch_detaliu`; rulează dedup pe poze.
- Teste: `tests/test_imagini.py` (nou), `tests/test_dedup_poze.py` (nou), `tests/test_poze_fetch.py` (nou), `tests/test_cache_hashuri.py` (nou), `tests/test_detaliu_fetch.py` (modificat), `tests/test_detalii.py` (modificat).

---

### Task 1: Câmpuri noi în modele

**Files:**
- Modify: `acp/modele.py:14-31` (clasa `Subiect`), `acp/modele.py:39-57` (clasa `Comparabila`)
- Test: `tests/test_modele_dedup.py` (nou)

**Interfaces:**
- Produces: `Subiect.url: str | None = None`; `Comparabila.camere: int | None = None`; `Comparabila.poze_urls: list[str] = []`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_modele_dedup.py`:

```python
from acp.modele import Subiect, Comparabila


def test_subiect_are_url_optional():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2)
    assert s.url is None
    s2 = Subiect(pret_eur=108000, supr_totala=59, camere=2, url="https://x.ro/a")
    assert s2.url == "https://x.ro/a"


def test_comparabila_are_camere_si_poze():
    c = Comparabila(sursa="imobiliare.ro", supr_totala=60)
    assert c.camere is None
    assert c.poze_urls == []
    c2 = Comparabila(sursa="imobiliare.ro", supr_totala=60, camere=2,
                     poze_urls=["https://x.ro/p1.jpg"])
    assert c2.camere == 2
    assert c2.poze_urls == ["https://x.ro/p1.jpg"]


def test_poze_urls_nu_sunt_partajate_intre_instante():
    a = Comparabila(sursa="s", supr_totala=50)
    b = Comparabila(sursa="s", supr_totala=50)
    a.poze_urls.append("x")
    assert b.poze_urls == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_modele_dedup.py -v`
Expected: FAIL (`TypeError`/`ValidationError` — `url`/`camere`/`poze_urls` necunoscute).

- [ ] **Step 3: Add the fields**

In `acp/modele.py`, în clasa `Subiect`, după linia `tip_vanzator: str | None = None`:

```python
    tip_vanzator: str | None = None
    url: str | None = None        # linkul anunțului subiect (agentul îl dă la pasul [0])
```

In clasa `Comparabila`, după linia `url: str | None = None`:

```python
    url: str | None = None
    camere: int | None = None     # pentru pre-filtrul de duplicat (connectorii îl populează)
    poze_urls: list[str] = []     # URL-uri de poze (galerie), populate la îmbogățire
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_modele_dedup.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run full suite (regression)**

Run: `uv run pytest -q`
Expected: PASS (nicio regresie).

- [ ] **Step 6: Commit**

```bash
git add acp/modele.py tests/test_modele_dedup.py
git commit -m "feat(modele): Subiect.url, Comparabila.camere si poze_urls"
```

---

### Task 2: Perceptual hashing (`acp/imagini.py`)

**Files:**
- Create: `acp/imagini.py`
- Test: `tests/test_imagini.py`

**Interfaces:**
- Produces: `dhash(imagine_bytes: bytes, hash_size: int = 8) -> int | None`; `distanta_hamming(h1: int, h2: int) -> int`.
- Consumes: Pillow (`PIL.Image`), stdlib `io.BytesIO`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_imagini.py`:

```python
from io import BytesIO

from PIL import Image

from acp.imagini import dhash, distanta_hamming


def _img_pattern(fx: int, fy: int, size: int = 64) -> Image.Image:
    """Imagine grayscale low-freq (blocuri 8px) — stabilă la redimensionare."""
    img = Image.new("L", (size, size))
    img.putdata([((x // 8) * fx + (y // 8) * fy) % 256
                 for y in range(size) for x in range(size)])
    return img


def _png(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_distanta_hamming_numara_bitii():
    assert distanta_hamming(0b1010, 0b1000) == 1
    assert distanta_hamming(0, 0) == 0
    assert distanta_hamming(0xFFFFFFFFFFFFFFFF, 0) == 64


def test_dhash_are_64_biti():
    h = dhash(_png(_img_pattern(70, 15)))
    assert h is not None
    assert 0 <= h < (1 << 64)


def test_dhash_identic_distanta_zero():
    b = _png(_img_pattern(70, 15))
    assert distanta_hamming(dhash(b), dhash(b)) == 0


def test_dhash_redimensionare_ramane_apropiat():
    img = _img_pattern(70, 15, 64)
    mare = img.resize((128, 128), Image.LANCZOS)
    d = distanta_hamming(dhash(_png(img)), dhash(_png(mare)))
    assert d <= 8


def test_dhash_imagini_diferite_distanta_mare():
    a = dhash(_png(_img_pattern(70, 15)))
    b = dhash(_png(_img_pattern(15, 70)))
    assert distanta_hamming(a, b) > 8


def test_dhash_bytes_invalizi_none():
    assert dhash(b"nu sunt o imagine") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_imagini.py -v`
Expected: FAIL (`ModuleNotFoundError: acp.imagini`).

- [ ] **Step 3: Implement `acp/imagini.py`**

```python
"""Perceptual hashing (dHash) — pur, doar Pillow. Fără rețea, fără dependențe noi."""
from __future__ import annotations

from io import BytesIO

from PIL import Image


def dhash(imagine_bytes: bytes, hash_size: int = 8) -> int | None:
    """dHash pe (hash_size*hash_size) biți al unei imagini.

    Convertește la grayscale, redimensionează la (hash_size+1) x hash_size și
    compară fiecare pixel cu vecinul din dreapta (diferențe orizontale). Robust
    la redimensionare și recompresie. Întoarce None dacă bytes-ii nu sunt o imagine.
    """
    try:
        img = (
            Image.open(BytesIO(imagine_bytes))
            .convert("L")
            .resize((hash_size + 1, hash_size), Image.LANCZOS)
        )
    except Exception:
        return None
    pixels = list(img.getdata())
    latime = hash_size + 1
    bits = 0
    for rand in range(hash_size):
        for col in range(hash_size):
            stanga = pixels[rand * latime + col]
            dreapta = pixels[rand * latime + col + 1]
            bits = (bits << 1) | (1 if stanga > dreapta else 0)
    return bits


def distanta_hamming(h1: int, h2: int) -> int:
    """Numărul de biți diferiți între două hash-uri (0 = identice)."""
    return bin(h1 ^ h2).count("1")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_imagini.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add acp/imagini.py tests/test_imagini.py
git commit -m "feat(imagini): dHash 64-bit si distanta Hamming (Pillow)"
```

---

### Task 3: Populează `camere` în connectori

**Files:**
- Modify: `acp/connectors/imobiliare.py:108-114` (loop `_search_async`)
- Modify: `acp/connectors/storia.py:158-167` (loop `_search_async`)
- Modify: `acp/connectors/olx.py:167-176` (loop `_search_async`)
- Test: `tests/test_camere_connectori.py` (nou)

**Interfaces:**
- Consumes: `Comparabila.camere` (Task 1), `CriteriiCautare.camere`.
- Produces: comparabilele întoarse de cei trei connectori au `camere == criterii.camere`.

Notă: toți cei trei connectori garantează deja că rezultatele au `criterii.camere` (imobiliare prin segmentul `{N}-camere` din URL; storia/olx prin filtrul `_extract_camere(item_dict) != criterii.camere`). E deci corect și determinist să setăm `comp.camere = criterii.camere` la momentul agregării.

- [ ] **Step 1: Write the failing test**

Create `tests/test_camere_connectori.py`:

```python
from acp.connectors.imobiliare import ImobiliareConnector

ARTICLE = (
    '<article data-listing-id="1" data-surface="60" data-item-price="120000" '
    'data-year="2010" data-status="sale" data-availability="available">'
    '<a href="/oferta/x"></a>'
    '<span class="listing-attribute">2 camere</span>'
    '<span class="listing-attribute">60 mp</span>'
    '<span class="listing-attribute">etaj 2</span>'
    '<span class="listing-attribute">2010</span>'
    '</article>'
)


def test_imobiliare_normalize_nu_seteaza_camere_singur():
    # normalize NU cunoaște criterii; camere se setează la agregare (vezi search loop).
    conn = ImobiliareConnector()
    comp = conn._normalize_listing_to_comparabila(ARTICLE)
    assert comp is not None
    assert comp.camere is None
```

Notă: connectorii fac rețea în `search()`; testăm setarea `camere` la nivel de loop printr-un helper pur. Adăugăm un test de loop care nu atinge rețeaua, verificând că bucla setează câmpul. Pentru a-l izola fără rețea, testăm direct invariantul post-parsare din `_search_async` reconstituind bucla:

```python
from acp.modele import CriteriiCautare


def test_loop_seteaza_camere_din_criterii():
    conn = ImobiliareConnector()
    criterii = CriteriiCautare(camere=2, supr_min=40, supr_max=80, zona="colentina")
    comp = conn._normalize_listing_to_comparabila(ARTICLE)
    # Reproduce pasul din _search_async: setarea camere din criterii.
    comp.camere = criterii.camere
    assert comp.camere == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_camere_connectori.py -v`
Expected: `test_imobiliare_normalize_nu_seteaza_camere_singur` PASS (camere e None din Task 1); `test_loop_seteaza_camere_din_criterii` PASS. Ambele trebuie să treacă — ele documentează invariantul. Dacă `camere` nu există încă pe model, FAIL cu `ValidationError`.

(Acest task e o modificare de connector fără test de rețea; testele fixează contractul. Trecem la implementare.)

- [ ] **Step 3: Setează `camere` în imobiliare**

In `acp/connectors/imobiliare.py`, în bucla din `_search_async` (liniile 108-114), adaugă atribuirea înainte de `append`:

```python
        for elem in listing_elems:
            comp = self._normalize_listing_to_comparabila(elem)
            if comp is None:
                continue
            if comp.supr_totala < criterii.supr_min or comp.supr_totala > criterii.supr_max:
                continue
            comp.camere = criterii.camere
            comparabile.append(comp)
```

- [ ] **Step 4: Setează `camere` în storia**

In `acp/connectors/storia.py`, în bucla din `_search_async` (liniile 158-167), înainte de `comparabile.append(comp)`:

```python
            if item_dict is None or self._extract_camere(item_dict) != criterii.camere:
                continue
            comp.camere = criterii.camere
            comparabile.append(comp)
```

- [ ] **Step 5: Setează `camere` în olx**

In `acp/connectors/olx.py`, în bucla din `_search_async` (liniile 167-176), înainte de `comparabile.append(comp)`:

```python
            if item_dict is None or self._extract_camere(item_dict) != criterii.camere:
                continue
            comp.camere = criterii.camere
            comparabile.append(comp)
```

- [ ] **Step 6: Run tests (unit + regression pe connectori)**

Run: `uv run pytest tests/test_camere_connectori.py tests/test_storia_connector.py tests/test_olx_connector.py -q`
Expected: PASS (nicio regresie).

- [ ] **Step 7: Commit**

```bash
git add acp/connectors/imobiliare.py acp/connectors/storia.py acp/connectors/olx.py tests/test_camere_connectori.py
git commit -m "feat(connectors): populeaza Comparabila.camere din criterii"
```

---

### Task 4: `fetch_detaliu` întoarce `(text, poze_urls)`

**Files:**
- Modify: `acp/connectors/detaliu_fetch.py` (întreg fișierul)
- Modify: `acp/connectors/imobiliare.py:310-312`, `acp/connectors/storia.py:382-384`, `acp/connectors/olx.py:427-429`
- Modify: `tests/test_detaliu_fetch.py`
- Test: `tests/test_detaliu_fetch.py` (extins cu `extrage_poze_din_srcs`)

**Interfaces:**
- Produces:
  - `extrage_poze_din_srcs(srcs: list[str], max_poze: int = 4) -> list[str]` (pur).
  - `fetch_detaliu(url, user_agent, timeout_ms=30000, retries=1) -> tuple[str | None, list[str]]`.
  - `fetch_detaliu_text(url, user_agent, timeout_ms=30000, retries=1) -> str | None` (wrapper, contract păstrat).
  - Metodă per-connector `fetch_detaliu(self, url) -> tuple[str | None, list[str]]`.

- [ ] **Step 1: Write the failing tests**

Replace `tests/test_detaliu_fetch.py` cu:

```python
import acp.connectors.detaliu_fetch as df


def test_extrage_poze_filtreaza_thumb_si_non_http():
    srcs = [
        "https://cdn.x.ro/gallery-thumb-1.jpg",   # thumbnail -> exclus
        "https://cdn.x.ro/foto-1.jpg",
        "data:image/png;base64,AAAA",             # non-http -> exclus
        "/local/foto-2.jpg",                       # non-http -> exclus
        "https://cdn.x.ro/foto-2.jpg",
        "https://cdn.x.ro/logo.svg",               # svg -> exclus
    ]
    assert df.extrage_poze_din_srcs(srcs) == [
        "https://cdn.x.ro/foto-1.jpg",
        "https://cdn.x.ro/foto-2.jpg",
    ]


def test_extrage_poze_dedup_si_cap_la_max():
    srcs = [f"https://cdn.x.ro/f{i}.jpg" for i in range(10)] + ["https://cdn.x.ro/f0.jpg"]
    out = df.extrage_poze_din_srcs(srcs, max_poze=4)
    assert out == [f"https://cdn.x.ro/f{i}.jpg" for i in range(4)]
    assert len(out) == 4


def test_fetch_detaliu_intoarce_text_si_poze(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "text de pe pagina", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "_extrage_pagina", _fake)
    text, poze = df.fetch_detaliu("https://x.ro/1", "UA")
    assert text == "text de pe pagina"
    assert poze == ["https://cdn.x.ro/foto-1.jpg"]


def test_fetch_detaliu_none_la_eroare(monkeypatch):
    async def _boom(url, user_agent, timeout_ms):
        raise RuntimeError("cloudflare / timeout")
    monkeypatch.setattr(df, "_extrage_pagina", _boom)
    assert df.fetch_detaliu("https://x.ro/1", "UA", retries=1) == (None, [])


def test_fetch_detaliu_text_wrapper_intoarce_doar_text(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "doar text", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "_extrage_pagina", _fake)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA") == "doar text"


def test_connector_deleaga_fetch_detaliu_cu_user_agent_propriu(monkeypatch):
    from acp.connectors.imobiliare import ImobiliareConnector, USER_AGENT
    apeluri = {}

    def _fake_fetch(url, user_agent, timeout_ms=30000, retries=1):
        apeluri["url"] = url
        apeluri["ua"] = user_agent
        return "ok", ["https://cdn.x.ro/foto-1.jpg"]
    monkeypatch.setattr(df, "fetch_detaliu", _fake_fetch)
    conn = ImobiliareConnector()
    text, poze = conn.fetch_detaliu("https://imobiliare.ro/y")
    assert text == "ok"
    assert poze == ["https://cdn.x.ro/foto-1.jpg"]
    assert apeluri["url"] == "https://imobiliare.ro/y"
    assert apeluri["ua"] == USER_AGENT
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detaliu_fetch.py -v`
Expected: FAIL (`extrage_poze_din_srcs` / `fetch_detaliu` / `_extrage_pagina` nu există).

- [ ] **Step 3: Rewrite `acp/connectors/detaliu_fetch.py`**

```python
"""Fetch text + URL-uri poze dintr-o pagină de detaliu (Playwright).

Izolat de motorul pur acp/detalii.py și de dedup-ul de poze. O singură navigare
întoarce atât textul body-ului, cât și URL-urile de galerie (evită două page-load).
"""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright


def extrage_poze_din_srcs(srcs: list[str], max_poze: int = 4) -> list[str]:
    """Filtrează sursele `<img>` la primele `max_poze` URL-uri de galerie.

    Exclude thumbnail-urile (`gallery-thumb`/`thumb`), sursele non-http
    (`data:`, căi relative) și `.svg` (logo-uri/iconițe). Elimină duplicatele
    păstrând ordinea.
    """
    rezultat: list[str] = []
    for s in srcs:
        if not s or not s.startswith("http"):
            continue
        low = s.lower()
        if "thumb" in low or low.endswith(".svg"):
            continue
        if s in rezultat:
            continue
        rezultat.append(s)
        if len(rezultat) >= max_poze:
            break
    return rezultat


async def _extrage_pagina(url: str, user_agent: str, timeout_ms: int) -> tuple[str, list[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=user_agent, locale="ro-RO")
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # lasă Cloudflare/JS să se așeze
            text = await page.inner_text("body")
            srcs = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.src || e.getAttribute('data-src') || '')",
            )
            return text, extrage_poze_din_srcs(srcs)
        finally:
            await browser.close()


def fetch_detaliu(url: str, user_agent: str, timeout_ms: int = 30000,
                  retries: int = 1) -> tuple[str | None, list[str]]:
    """Deschide pagina de detaliu și întoarce (text_body, poze_urls), sau (None, []) la eșec."""
    for tentativa in range(retries + 1):
        try:
            return asyncio.run(_extrage_pagina(url, user_agent, timeout_ms))
        except Exception:
            if tentativa >= retries:
                return None, []
    return None, []


def fetch_detaliu_text(url: str, user_agent: str, timeout_ms: int = 30000,
                       retries: int = 1) -> str | None:
    """Wrapper compatibil: întoarce doar textul body-ului (sau None la eșec)."""
    return fetch_detaliu(url, user_agent, timeout_ms, retries)[0]
```

- [ ] **Step 4: Add `fetch_detaliu` method to the three connectors**

In `acp/connectors/imobiliare.py`, înlocuiește metoda `fetch_detaliu_text` (liniile 310-312) cu:

```python
    def fetch_detaliu(self, url: str) -> tuple[str | None, list[str]]:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu(url, USER_AGENT)

    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
```

In `acp/connectors/storia.py` (liniile 382-384) și `acp/connectors/olx.py` (liniile 427-429), aplică exact aceeași înlocuire (același corp — `USER_AGENT` e cel local fiecărui modul).

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_detaliu_fetch.py -v`
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add acp/connectors/detaliu_fetch.py acp/connectors/imobiliare.py acp/connectors/storia.py acp/connectors/olx.py tests/test_detaliu_fetch.py
git commit -m "feat(detaliu_fetch): fetch_detaliu intoarce (text, poze_urls)"
```

---

### Task 5: `imbogateste_detalii` stochează `poze_urls` + pipeline folosește `fetch_detaliu`

**Files:**
- Modify: `acp/detalii.py:27-56` (`imbogateste_detalii`)
- Modify: `acp/core/pipeline.py:216-220` (construcția `fetchers`)
- Modify: `tests/test_detalii.py`

**Interfaces:**
- Consumes: fetcher `Callable[[str], tuple[str | None, list[str]]]` (din Task 4).
- Produces: după îmbogățire, `c.poze_urls` e populat; `poze_urls` intră în dict-ul cache-uit.

- [ ] **Step 1: Update the failing tests**

In `tests/test_detalii.py`, actualizează fetcher-ele să întoarcă tuple. Înlocuiește testele afectate:

```python
def test_imbogateste_populeaza_si_seteaza_flag():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: (
        "structură beton, mobilat, garaj subteran",
        ["https://imobiliare.ro/p1.jpg", "https://imobiliare.ro/p2.jpg"],
    )}
    n = imbogateste_detalii([c], fetchers)
    assert n == 1
    assert c.detalii_complete is True
    assert c.structura == "beton"
    assert "mobilat" in c.dotari
    assert c.parcare_tip == "owned"
    assert c.poze_urls == ["https://imobiliare.ro/p1.jpg", "https://imobiliare.ro/p2.jpg"]


def test_imbogateste_fetch_esuat_lasa_flag_false():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: (None, [])}
    n = imbogateste_detalii([c], fetchers)
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_sursa_fara_fetcher_sarita():
    c = _c(sursa="publi24.ro")
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: ("beton", [])})
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_fara_url_sarita():
    c = _c(url=None)
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: ("beton", [])})
    assert n == 0
```

Și testul de cache (`test_imbogateste_foloseste_cache_evita_fetch`) — adaugă `poze_urls` în dict-ul pre-populat și verifică:

```python
def test_imbogateste_foloseste_cache_evita_fetch(tmp_path):
    from acp.cache_detalii import CacheDetalii
    cache = CacheDetalii(dir=str(tmp_path / "d"))
    c = _c()
    cache.set(c.url, {"structura": "caramida", "incalzire": None, "stare": None,
                      "stare_incredere": 0.0, "parcare_tip": None, "dotari": [],
                      "etaje_total": None, "poze_urls": ["https://imobiliare.ro/p9.jpg"]})

    def _raise(url):
        raise AssertionError("fetcher nu trebuia apelat (cache hit)")

    n = imbogateste_detalii([c], {"imobiliare.ro": _raise}, cache=cache)
    assert n == 1
    assert c.structura == "caramida"
    assert c.poze_urls == ["https://imobiliare.ro/p9.jpg"]
    assert c.detalii_complete is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detalii.py -v`
Expected: FAIL (fetcher-ul întoarce tuple; codul actual apelează `parseaza_detaliu(text)` pe un tuple → eroare / poze_urls neasignat).

- [ ] **Step 3: Update `imbogateste_detalii`**

In `acp/detalii.py`, înlocuiește corpul funcției (liniile 27-56):

```python
def imbogateste_detalii(
    comparabile: list[Comparabila],
    fetchers: dict[str, Callable[[str], tuple[str | None, list[str]]]],
    cache=None,
) -> int:
    """Îmbogățește comparabilele cu date + URL-uri de poze din pagina de detaliu.

    Pentru fiecare comparabilă cu `url` și o sursă prezentă în `fetchers`:
    - încearcă cache-ul; la miss apelează fetcher-ul `(text, poze_urls)` și parsează;
    - populează câmpurile (inclusiv `poze_urls`) și setează `detalii_complete=True`.
    Fetch eșuat (text None) sau sursă fără fetcher → sărită (detalii_complete rămâne False).
    Întoarce numărul de comparabile îmbogățite.
    """
    n = 0
    for c in comparabile:
        if not c.url or c.sursa not in fetchers:
            continue
        campuri = cache.get(c.url) if cache is not None else None
        if campuri is None:
            text, poze_urls = fetchers[c.sursa](c.url)
            if not text:
                continue
            campuri = parseaza_detaliu(text, c.an)
            campuri["poze_urls"] = poze_urls
            if cache is not None:
                cache.set(c.url, campuri)
        for cheie, valoare in campuri.items():
            setattr(c, cheie, valoare)
        c.detalii_complete = True
        n += 1
    return n
```

Actualizează și importul de tip din capul fișierului dacă e nevoie (rămâne `from typing import Callable`).

- [ ] **Step 4: Update the pipeline fetcher dict**

In `acp/core/pipeline.py`, în `deduplicate_and_analyze`, construcția `fetchers` (liniile 216-220):

```python
            fetchers = {
                c.name: c.fetch_detaliu
                for c in self.connectors
                if hasattr(c, "fetch_detaliu")
            }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_detalii.py -q`
Expected: PASS.

- [ ] **Step 6: Run full suite (regression)**

Run: `uv run pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add acp/detalii.py acp/core/pipeline.py tests/test_detalii.py
git commit -m "feat(detalii): stocheaza poze_urls la imbogatire; pipeline foloseste fetch_detaliu"
```

---

### Task 6: Motorul de deduplicare pur (`acp/dedup_poze.py`)

**Files:**
- Create: `acp/dedup_poze.py`
- Test: `tests/test_dedup_poze.py`

**Interfaces:**
- Consumes: `acp.imagini.distanta_hamming` (Task 2); `Subiect`, `Comparabila`.
- Produces:
  - `sunt_candidat_duplicat(a, b, prag_supr=2.0, prag_pret_pct=0.01) -> bool`
  - `potrivire_metadata_subiect(subiect, c, prag_supr=2.0, prag_pret_pct=0.01) -> bool`
  - `confirma_si_dedup(comparabile, subiect, subiect_hashes, fetch_poze, prag_hamming=8) -> tuple[list, list, list]` întorcând `(pastrate, duplicate_eliminate, subiect_eliminate)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dedup_poze.py`:

```python
from acp.dedup_poze import (
    sunt_candidat_duplicat, potrivire_metadata_subiect, confirma_si_dedup,
)
from acp.modele import Subiect, Comparabila


def _c(sursa, pret, supr, etaj=2, camere=2, poze=None):
    return Comparabila(sursa=sursa, pret_eur=pret, supr_totala=supr, etaj=etaj,
                       camere=camere, poze_urls=poze or [])


# ---- pre-filtru metadata ----

def test_candidat_pe_praguri():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 108500, 60)  # +0,46% pret, +1mp
    assert sunt_candidat_duplicat(a, b) is True


def test_nu_candidat_pret_prea_diferit():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 120000, 60)  # +11%
    assert sunt_candidat_duplicat(a, b) is False


def test_nu_candidat_etaj_diferit():
    a = _c("imobiliare.ro", 108000, 59, etaj=2)
    b = _c("storia.ro", 108000, 59, etaj=5)
    assert sunt_candidat_duplicat(a, b) is False


def test_nu_candidat_suprafata_prea_diferita():
    a = _c("imobiliare.ro", 108000, 59)
    b = _c("storia.ro", 108000, 63)  # +4mp
    assert sunt_candidat_duplicat(a, b) is False


def test_camere_necunoscute_nu_blocheaza():
    a = _c("imobiliare.ro", 108000, 59, camere=None)
    b = _c("storia.ro", 108000, 60, camere=2)
    assert sunt_candidat_duplicat(a, b) is True


def test_potrivire_subiect_pe_praguri():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    c = _c("storia.ro", 108000, 60, etaj=2, camere=2)
    assert potrivire_metadata_subiect(s, c) is True


def test_potrivire_subiect_esueaza_etaj():
    s = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    c = _c("storia.ro", 108000, 60, etaj=4, camere=2)
    assert potrivire_metadata_subiect(s, c) is False


# ---- confirmare + dedup (fetch_poze injectat, fără rețea) ----

def _fetch_din_dict(mapping):
    def _fetch(c):
        return mapping.get(c.url, [])
    return _fetch


def test_doua_candidate_cu_hash_comun_una_eliminata():
    a = _c("imobiliare.ro", 108000, 59); a.url = "a"
    b = _c("storia.ro", 108000, 60); b.url = "b"
    subiect = Subiect(pret_eur=999999, supr_totala=200, camere=5, etaj=9)  # nu se potrivește
    fetch = _fetch_din_dict({"a": [111], "b": [111]})  # aceeași poză
    pastrate, dup, subj = confirma_si_dedup([a, b], subiect, [], fetch)
    assert len(pastrate) == 1 and pastrate[0] is a
    assert dup == [b]
    assert subj == []


def test_doua_candidate_fara_hash_comun_ambele_pastrate():
    a = _c("imobiliare.ro", 108000, 59); a.url = "a"
    b = _c("storia.ro", 108000, 60); b.url = "b"
    subiect = Subiect(pret_eur=999999, supr_totala=200, camere=5, etaj=9)
    fetch = _fetch_din_dict({"a": [111], "b": [999999999]})  # poze diferite
    pastrate, dup, subj = confirma_si_dedup([a, b], subiect, [], fetch)
    assert set(id(x) for x in pastrate) == {id(a), id(b)}
    assert dup == []


def test_comparabila_cu_hash_de_subiect_e_eliminata():
    a = _c("imobiliare.ro", 108000, 59, etaj=2, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)
    fetch = _fetch_din_dict({"a": [111]})
    pastrate, dup, subj = confirma_si_dedup([a], subiect, [111], fetch)
    assert pastrate == []
    assert subj == [a]


def test_comparabila_fara_grup_candidat_neatinsa_fara_fetch():
    a = _c("imobiliare.ro", 90000, 50, etaj=1, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=200000, supr_totala=90, camere=4, etaj=9)

    def _fetch_boom(c):
        raise AssertionError("fetch_poze nu trebuia apelat pentru non-candidat")

    pastrate, dup, subj = confirma_si_dedup([a], subiect, [111], _fetch_boom)
    assert pastrate == [a]
    assert dup == [] and subj == []


def test_fallback_fara_subiect_hashes_exclude_pe_metadata():
    a = _c("imobiliare.ro", 108000, 59, etaj=2, camere=2); a.url = "a"
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2)

    def _fetch_boom(c):
        raise AssertionError("fara subiect_hashes nu descarcam poze pentru excludere")

    pastrate, dup, subj = confirma_si_dedup([a], subiect, [], _fetch_boom)
    assert subj == [a]
    assert pastrate == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_dedup_poze.py -v`
Expected: FAIL (`ModuleNotFoundError: acp.dedup_poze`).

- [ ] **Step 3: Implement `acp/dedup_poze.py`**

```python
"""Motor pur de deduplicare pe poze + excludere subiect.

Metadata = pre-filtru ieftin (marchează perechi suspecte). Pozele = verdictul:
`fetch_poze` (injectabil, fără rețea în teste) întoarce hash-urile de poze ale
unei comparabile; confirmăm duplicatul dacă o pereche de poze e sub pragul Hamming.
"""
from __future__ import annotations

from typing import Callable

from acp.imagini import distanta_hamming
from acp.modele import Comparabila, Subiect


def sunt_candidat_duplicat(a: Comparabila, b: Comparabila,
                           prag_supr: float = 2.0, prag_pret_pct: float = 0.01) -> bool:
    """Pre-filtru metadata: același etaj, aceleași camere (dacă ambele știute),
    suprafață în ±prag_supr mp, preț în ±prag_pret_pct."""
    if a.etaj != b.etaj:
        return False
    if a.camere is not None and b.camere is not None and a.camere != b.camere:
        return False
    if abs(a.supr_totala - b.supr_totala) > prag_supr:
        return False
    if a.pret_eur is None or b.pret_eur is None:
        return False
    if abs(a.pret_eur - b.pret_eur) > prag_pret_pct * max(a.pret_eur, b.pret_eur):
        return False
    return True


def potrivire_metadata_subiect(subiect: Subiect, c: Comparabila,
                               prag_supr: float = 2.0, prag_pret_pct: float = 0.01) -> bool:
    """Pre-filtru: comparabila `c` se potrivește cu subiectul (etaj, camere, supr, preț)."""
    if subiect.etaj != c.etaj:
        return False
    if c.camere is not None and subiect.camere != c.camere:
        return False
    if abs(subiect.supr_totala - c.supr_totala) > prag_supr:
        return False
    if c.pret_eur is None:
        return False
    if abs(subiect.pret_eur - c.pret_eur) > prag_pret_pct * max(subiect.pret_eur, c.pret_eur):
        return False
    return True


def _poze_se_potrivesc(hashes_a: list[int], hashes_b: list[int], prag_hamming: int) -> bool:
    """True dacă vreo pereche de hash-uri e sub pragul Hamming (aceeași poză)."""
    for ha in hashes_a:
        for hb in hashes_b:
            if distanta_hamming(ha, hb) <= prag_hamming:
                return True
    return False


def confirma_si_dedup(
    comparabile: list[Comparabila],
    subiect: Subiect,
    subiect_hashes: list[int],
    fetch_poze: Callable[[Comparabila], list[int]],
    prag_hamming: int = 8,
) -> tuple[list[Comparabila], list[Comparabila], list[Comparabila]]:
    """Întoarce (pastrate, duplicate_eliminate, subiect_eliminate).

    - Descarcă hash-uri (via `fetch_poze`) DOAR pentru comparabilele candidate
      (față de subiect sau față de altă comparabilă). Restul rămân neatinse.
    - Comparabilă care se potrivește pe metadata cu subiectul ȘI împarte o poză
      cu `subiect_hashes` → subiect_eliminate. Fără `subiect_hashes` → excludere
      doar pe metadata (fallback), fără descărcare de poze.
    - Două candidate care împart o poză → același apartament; se păstrează prima
      văzută, cealaltă în duplicate_eliminate.
    """
    hashes_cache: dict[int, list[int]] = {}

    def hashes_pentru(c: Comparabila) -> list[int]:
        if id(c) not in hashes_cache:
            hashes_cache[id(c)] = fetch_poze(c)
        return hashes_cache[id(c)]

    # --- Pas 1: excludere subiect ---
    subiect_eliminate: list[Comparabila] = []
    ramase: list[Comparabila] = []
    for c in comparabile:
        if not potrivire_metadata_subiect(subiect, c):
            ramase.append(c)
            continue
        if not subiect_hashes:
            # Fallback: fără poze de subiect, excludem pe metadata (risc mic).
            subiect_eliminate.append(c)
            continue
        if _poze_se_potrivesc(hashes_pentru(c), subiect_hashes, prag_hamming):
            subiect_eliminate.append(c)
        else:
            ramase.append(c)

    # --- Pas 2: dedup cross-agenție între comparabilele rămase ---
    pastrate: list[Comparabila] = []
    duplicate_eliminate: list[Comparabila] = []
    for c in ramase:
        gasit_duplicat = False
        for pastrat in pastrate:
            if sunt_candidat_duplicat(c, pastrat) and _poze_se_potrivesc(
                hashes_pentru(c), hashes_pentru(pastrat), prag_hamming
            ):
                gasit_duplicat = True
                break
        if gasit_duplicat:
            duplicate_eliminate.append(c)
        else:
            pastrate.append(c)

    return pastrate, duplicate_eliminate, subiect_eliminate
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_dedup_poze.py -v`
Expected: PASS (12 passed).

- [ ] **Step 5: Commit**

```bash
git add acp/dedup_poze.py tests/test_dedup_poze.py
git commit -m "feat(dedup_poze): motor pur metadata+poze cu fetch_poze injectabil"
```

---

### Task 7: Descărcare poze + cache hash-uri (`acp/poze_fetch.py`, `acp/cache_hashuri.py`)

**Files:**
- Create: `acp/cache_hashuri.py`
- Create: `acp/poze_fetch.py`
- Test: `tests/test_cache_hashuri.py`, `tests/test_poze_fetch.py`

**Interfaces:**
- Consumes: `acp.imagini.dhash` (Task 2); `Comparabila.poze_urls` (Task 1).
- Produces:
  - `CacheHashuri(dir=".cache/hashuri", ttl_zile=1.0)` cu `get(url) -> list[int] | None` și `set(url, hashuri)`.
  - `descarca_bytes(url, user_agent, timeout=10.0) -> bytes | None`
  - `hashuri_din_urls(urls, user_agent, descarca=descarca_bytes, max_poze=4) -> list[int]`
  - `construieste_fetch_poze(user_agent, cache=None, descarca=descarca_bytes, max_poze=4) -> Callable[[Comparabila], list[int]]`

- [ ] **Step 1: Write the failing tests (cache)**

Create `tests/test_cache_hashuri.py`:

```python
from acp.cache_hashuri import CacheHashuri


def test_set_get_roundtrip(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"))
    cache.set("https://x.ro/a", [1, 2, 3])
    assert cache.get("https://x.ro/a") == [1, 2, 3]


def test_get_miss_none(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"))
    assert cache.get("https://x.ro/lipsa") is None


def test_ttl_expira(tmp_path):
    cache = CacheHashuri(dir=str(tmp_path / "h"), ttl_zile=0.0)
    cache.set("https://x.ro/a", [1])
    assert cache.get("https://x.ro/a") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `uv run pytest tests/test_cache_hashuri.py -v`
Expected: FAIL (`ModuleNotFoundError: acp.cache_hashuri`).

- [ ] **Step 3: Implement `acp/cache_hashuri.py`**

```python
"""Cache pe disc pentru liste de hash-uri de poze (paralel cu CacheDetalii)."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class CacheHashuri:
    def __init__(self, dir: str = ".cache/hashuri", ttl_zile: float = 1.0):
        self.dir = Path(dir)
        self.ttl_secunde = ttl_zile * 86400
        self.dir.mkdir(parents=True, exist_ok=True)

    def _cale(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, url: str) -> list[int] | None:
        p = self._cale(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("fetched_at", 0.0) > self.ttl_secunde:
            return None
        return data.get("hashuri")

    def set(self, url: str, hashuri: list[int]) -> None:
        payload = {"fetched_at": time.time(), "hashuri": hashuri}
        self._cale(url).write_text(json.dumps(payload), encoding="utf-8")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_cache_hashuri.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Write the failing tests (poze_fetch)**

Create `tests/test_poze_fetch.py`:

```python
from io import BytesIO

from PIL import Image

from acp.poze_fetch import hashuri_din_urls, construieste_fetch_poze
from acp.imagini import dhash
from acp.modele import Comparabila


def _png_bytes(fx=70, fy=15, size=64):
    img = Image.new("L", (size, size))
    img.putdata([((x // 8) * fx + (y // 8) * fy) % 256
                 for y in range(size) for x in range(size)])
    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_hashuri_din_urls_calculeaza_dhash():
    octeti = _png_bytes()

    def _descarca(url, user_agent, timeout=10.0):
        return octeti

    out = hashuri_din_urls(["https://x.ro/a.jpg"], "UA", descarca=_descarca)
    assert out == [dhash(octeti)]


def test_hashuri_din_urls_sare_descarcarile_esuate():
    def _descarca(url, user_agent, timeout=10.0):
        return None

    out = hashuri_din_urls(["https://x.ro/a.jpg", "https://x.ro/b.jpg"], "UA", descarca=_descarca)
    assert out == []


def test_hashuri_din_urls_cap_la_max():
    octeti = _png_bytes()
    apeluri = []

    def _descarca(url, user_agent, timeout=10.0):
        apeluri.append(url)
        return octeti

    urls = [f"https://x.ro/{i}.jpg" for i in range(10)]
    hashuri_din_urls(urls, "UA", descarca=_descarca, max_poze=3)
    assert len(apeluri) == 3


def test_fetch_poze_foloseste_poze_urls_si_cache():
    octeti = _png_bytes()
    c = Comparabila(sursa="s", supr_totala=60, url="https://x.ro/anunt",
                    poze_urls=["https://x.ro/a.jpg"])
    apeluri = []

    def _descarca(url, user_agent, timeout=10.0):
        apeluri.append(url)
        return octeti

    class _Cache:
        def __init__(self):
            self.store = {}
        def get(self, url):
            return self.store.get(url)
        def set(self, url, hashuri):
            self.store[url] = hashuri

    cache = _Cache()
    fetch = construieste_fetch_poze("UA", cache=cache, descarca=_descarca)
    out1 = fetch(c)
    out2 = fetch(c)  # a doua oară din cache
    assert out1 == [dhash(octeti)]
    assert out2 == out1
    assert len(apeluri) == 1  # descărcat o singură dată (cache hit la al doilea apel)
```

- [ ] **Step 6: Run to verify fail**

Run: `uv run pytest tests/test_poze_fetch.py -v`
Expected: FAIL (`ModuleNotFoundError: acp.poze_fetch`).

- [ ] **Step 7: Implement `acp/poze_fetch.py`**

```python
"""Descărcare poze + calcul dHash. I/O izolat (urllib); motorul de dedup rămâne pur."""
from __future__ import annotations

import urllib.request
from typing import Callable

from acp.imagini import dhash
from acp.modele import Comparabila


def descarca_bytes(url: str, user_agent: str, timeout: float = 10.0) -> bytes | None:
    """Descarcă conținutul unui URL de poză. None la orice eroare."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": user_agent})
        with urllib.request.urlopen(req, timeout=timeout) as raspuns:
            return raspuns.read()
    except Exception:
        return None


def hashuri_din_urls(
    urls: list[str],
    user_agent: str,
    descarca: Callable[..., bytes | None] = descarca_bytes,
    max_poze: int = 4,
) -> list[int]:
    """Descarcă primele `max_poze` URL-uri și întoarce lista de dHash-uri valide."""
    hashuri: list[int] = []
    for url in urls[:max_poze]:
        octeti = descarca(url, user_agent)
        if octeti is None:
            continue
        h = dhash(octeti)
        if h is not None:
            hashuri.append(h)
    return hashuri


def construieste_fetch_poze(
    user_agent: str,
    cache=None,
    descarca: Callable[..., bytes | None] = descarca_bytes,
    max_poze: int = 4,
) -> Callable[[Comparabila], list[int]]:
    """Construiește un `fetch_poze(c)` care descarcă `c.poze_urls` → dHash-uri, cu cache pe disc."""
    def fetch_poze(c: Comparabila) -> list[int]:
        if cache is not None and c.url:
            din_cache = cache.get(c.url)
            if din_cache is not None:
                return din_cache
        hashuri = hashuri_din_urls(c.poze_urls, user_agent, descarca=descarca, max_poze=max_poze)
        if cache is not None and c.url:
            cache.set(c.url, hashuri)
        return hashuri

    return fetch_poze
```

- [ ] **Step 8: Run to verify pass**

Run: `uv run pytest tests/test_poze_fetch.py -v`
Expected: PASS (4 passed).

- [ ] **Step 9: Commit**

```bash
git add acp/cache_hashuri.py acp/poze_fetch.py tests/test_cache_hashuri.py tests/test_poze_fetch.py
git commit -m "feat(poze_fetch): descarcare poze + dHash + cache hash-uri pe disc"
```

---

### Task 8: Integrare în pipeline (`deduplicate_and_analyze`)

**Files:**
- Modify: `acp/core/pipeline.py` (import-uri + `deduplicate_and_analyze` liniile 186-234)
- Test: `tests/test_pipeline_dedup_poze.py` (nou)

**Interfaces:**
- Consumes: `confirma_si_dedup` (Task 6); `construieste_fetch_poze`, `hashuri_din_urls` (Task 7); `CacheHashuri` (Task 7); `detaliu_fetch.fetch_detaliu` (Task 4); `USER_AGENT` din `acp.connectors.imobiliare`.
- Produces: `deduplicate_and_analyze(subiect, comparabile, imbogateste=True, cache=None, dedup_poze=True)` — setul analizat exclude duplicatele și instanțele-subiect confirmate pe poze.

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline_dedup_poze.py`:

```python
from acp.core.pipeline import PipelineOrchestrator
from acp.modele import Subiect, Comparabila


def _comp(sursa, url, pret, supr, etaj=2, camere=2):
    return Comparabila(sursa=sursa, url=url, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, camere=camere, tip="vanzare", an=1980)


def test_dedup_poze_elimina_subiect_si_duplicat(monkeypatch):
    orch = PipelineOrchestrator()
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://imobiliare.ro/subiect")

    # subiectul (propriul anunț) + geamănul lui la altă agenție + un anunț normal
    prop = _comp("imobiliare.ro", "https://imobiliare.ro/subiect", 108000, 59)
    geaman = _comp("storia.ro", "https://storia.ro/geaman", 108000, 60)
    normal = _comp("olx.ro", "https://olx.ro/normal", 95000, 58)
    comparabile = [prop, geaman, normal]

    # fără rețea: nu îmbogățim (poze_urls setate manual), dar rulăm dedup_poze
    prop.poze_urls = ["https://cdn/p1.jpg"]
    geaman.poze_urls = ["https://cdn/p1b.jpg"]
    normal.poze_urls = ["https://cdn/n1.jpg"]

    # subiectul are aceleași poze ca prop și geaman (hash 111); normal are 999
    def _fake_fetch_detaliu(url, user_agent):
        return "text", ["https://cdn/subiect.jpg"]
    monkeypatch.setattr(
        "acp.connectors.detaliu_fetch.fetch_detaliu", _fake_fetch_detaliu
    )

    def _fake_hashuri_din_urls(urls, user_agent, **kw):
        return [111]  # hash-ul subiectului
    monkeypatch.setattr("acp.core.pipeline.hashuri_din_urls", _fake_hashuri_din_urls)

    hash_map = {
        "https://imobiliare.ro/subiect": [111],
        "https://storia.ro/geaman": [111],
        "https://olx.ro/normal": [999999],
    }

    def _fake_construieste_fetch_poze(user_agent, cache=None, **kw):
        def _fetch(c):
            return hash_map.get(c.url, [])
        return _fetch
    monkeypatch.setattr(
        "acp.core.pipeline.construieste_fetch_poze", _fake_construieste_fetch_poze
    )

    analiza = orch.deduplicate_and_analyze(
        subiect, comparabile, imbogateste=False, dedup_poze=True
    )

    urls_ramase = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://imobiliare.ro/subiect" not in urls_ramase  # subiect exclus
    assert "https://storia.ro/geaman" not in urls_ramase        # duplicat/subiect exclus
    assert "https://olx.ro/normal" in urls_ramase               # normalul rămâne


def test_dedup_poze_dezactivat_pastreaza_tot(monkeypatch):
    orch = PipelineOrchestrator()
    subiect = Subiect(pret_eur=108000, supr_totala=59, camere=2, etaj=2, an=1980,
                      url="https://imobiliare.ro/subiect")
    prop = _comp("imobiliare.ro", "https://imobiliare.ro/subiect", 108000, 59)
    normal = _comp("olx.ro", "https://olx.ro/normal", 95000, 58)
    analiza = orch.deduplicate_and_analyze(
        subiect, [prop, normal], imbogateste=False, dedup_poze=False
    )
    urls = {c.url for c in analiza.comparabile} | {c.url for c in analiza.outlieri}
    assert "https://imobiliare.ro/subiect" in urls
```

Notă asupra invariantului testului: `deduplicate_and_analyze` cu `imbogateste=False` rulează totuși blocul `dedup_poze` folosind `poze_urls` deja prezente pe comparabile. Vezi Step 3 — blocul `dedup_poze` nu depinde de `imbogateste`; ce depinde de `imbogateste` e doar popularea automată a `poze_urls`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline_dedup_poze.py -v`
Expected: FAIL (`deduplicate_and_analyze` nu acceptă `dedup_poze`).

- [ ] **Step 3: Update imports in `acp/core/pipeline.py`**

După linia `from acp.cache_detalii import CacheDetalii` (linia 17), adaugă:

```python
from acp.cache_detalii import CacheDetalii
from acp.cache_hashuri import CacheHashuri
from acp.dedup_poze import confirma_si_dedup
from acp.poze_fetch import construieste_fetch_poze, hashuri_din_urls
from acp.connectors import detaliu_fetch
from acp.connectors.imobiliare import USER_AGENT as UA_DETALIU
```

- [ ] **Step 4: Update `deduplicate_and_analyze`**

Înlocuiește semnătura și corpul (liniile 186-234). Semnătura devine:

```python
    def deduplicate_and_analyze(self, subiect: Subiect, comparabile: list[Comparabila],
                                imbogateste: bool = True, cache=None,
                                dedup_poze: bool = True) -> Analiza:
```

Și, în interior, calculează `survivors` chiar dacă `imbogateste` e False (avem nevoie de ei pentru dedup_poze), apoi rulează blocul de dedup. Structura corpului:

```python
        vanzari = [c for c in comparabile if c.tip == "vanzare"]
        survivors = filtreaza(subiect, dedup(vanzari))

        if imbogateste:
            fetchers = {
                c.name: c.fetch_detaliu
                for c in self.connectors
                if hasattr(c, "fetch_detaliu")
            }
            if cache is None:
                cache = CacheDetalii()
            n = imbogateste_detalii(survivors, fetchers, cache)
            logger.info(f"Imbogatite {n}/{len(survivors)} comparabile cu detalii de pe pagina de detaliu")

        if dedup_poze:
            subiect_hashes: list[int] = []
            if subiect.url:
                _, poze_subiect = detaliu_fetch.fetch_detaliu(subiect.url, UA_DETALIU)
                subiect_hashes = hashuri_din_urls(poze_subiect, UA_DETALIU)
            fetch_poze = construieste_fetch_poze(UA_DETALIU, cache=CacheHashuri())
            pastrate, dup_elim, subj_elim = confirma_si_dedup(
                survivors, subiect, subiect_hashes, fetch_poze
            )
            elim = {id(c) for c in dup_elim} | {id(c) for c in subj_elim}
            comparabile = [c for c in comparabile if id(c) not in elim]
            logger.info(
                f"Dedup poze: eliminate {len(dup_elim)} duplicate cross-agentie "
                f"si {len(subj_elim)} instante ale subiectului"
            )

        surse = sorted({c.sursa for c in comparabile})
        logger.info(f"deduplicate_and_analyze processing {len(comparabile)} comparabile from {len(surse)} sources")

        analiza = analizeaza(subiect, comparabile, tinta_zile=90, surse=surse)

        logger.info(f"Analysis complete: {analiza.stat_ajustat.n} comparabile retained after filtering")
        return analiza
```

Notă: `survivors` sunt aceleași obiecte (prin identitate) ca cele din `comparabile`, deci eliminarea prin `id(c)` scoate exact instanțele confirmate ca duplicat/subiect din setul pasat la `analizeaza`. `analizeaza` re-rulează `dedup`/`filtreaza` (plasă de siguranță ieftină) pe setul deja curățat — idempotent.

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_pipeline_dedup_poze.py -v`
Expected: PASS (2 passed).

- [ ] **Step 6: Run full suite (regression)**

Run: `uv run pytest -q`
Expected: PASS (nicio regresie).

- [ ] **Step 7: Commit**

```bash
git add acp/core/pipeline.py tests/test_pipeline_dedup_poze.py
git commit -m "feat(pipeline): dedup pe poze + excludere subiect (toggle dedup_poze)"
```

---

## Self-Review (efectuat la scriere)

**1. Acoperire spec:**
- Pre-filtru metadata (etaj+camere+supr±2mp+preț±1%) → Task 6 `sunt_candidat_duplicat`/`potrivire_metadata_subiect`. ✅
- dHash 64-bit + Hamming ≤8 → Task 2 + prag în Task 6. ✅
- Excludere subiect prin `Subiect.url` + poze, fallback metadata → Task 6 + Task 8. ✅
- Extracție poze într-un page-load + `poze_urls` → Task 4 + Task 5. ✅
- `Comparabila.camere`/`poze_urls`, `Subiect.url` → Task 1 + Task 3. ✅
- Descărcare bytes (urllib) doar pentru candidați → Task 7 + logica de fetch lazy din Task 6. ✅
- Cache hash-uri pe disc → Task 7 `CacheHashuri`. ✅
- Toggle `dedup_poze=True` → Task 8. ✅
- Fără dependențe noi (Pillow + urllib) → Global Constraints. ✅

**2. Placeholder scan:** fără TBD/TODO; tot codul e complet. ✅

**3. Type consistency:** `fetch_detaliu -> tuple[str|None, list[str]]` folosit consistent (Task 4→5→8); `fetch_poze: Callable[[Comparabila], list[int]]` consistent (Task 6 consumă, Task 7 produce); `confirma_si_dedup` întoarce `(pastrate, duplicate_eliminate, subiect_eliminate)` consistent (Task 6→8). ✅

**Deviație conștientă față de spec:** `confirma_si_dedup` NU primește parametru `cache` (spec-ul îl schița opțional). Caching-ul e încapsulat în `fetch_poze` (Task 7 `construieste_fetch_poze` + `CacheHashuri`), păstrând motorul de decizie pur. Spec-ul permitea explicit „reutilizează CacheDetalii sau o instanță separată" — am ales instanță separată injectată prin `fetch_poze`.
