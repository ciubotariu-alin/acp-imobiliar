# Îmbogățire cu Detalii (Task 12) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extrage dotările REALE ale comparabilelor din paginile lor de detaliu, ca ajustările de dotări să se aplice pe date, nu pe presupunerea „card gol = nu are" — eliminând biasul sistematic de +8% care răstoarnă verdictul.

**Architecture:** Un flag `detalii_complete` pe `Comparabila` gate-uiește ajustările de dotări. Un motor pur `acp/detalii.py` (fără rețea, cu fetcher injectabil) îmbogățește comparabilele post-filtrare deschizându-le pagina de detaliu (Playwright secvențial, per-conector, cu cache pe disc), rulează extractorii din `acp/extractie.py` și populează câmpurile. Orchestratorul cheamă îmbogățirea între filtrare și `analizeaza`.

**Tech Stack:** Python 3, Pydantic v2, pytest, Playwright (async, deja folosit de conectori). Fără dependențe noi.

## Global Constraints

- Ajustarea de dotări se aplică DOAR când `comp.detalii_complete is True` (necunoscut → nicio ajustare, simetric cu structură/încălzire/stare).
- Îmbogățire doar pe comparabilele post-filtrare (`filtreaza(dedup(vanzari))`), nu pe toate.
- Fetch secvențial; fetch eșuat/gol → `detalii_complete` rămâne `False` (comparabila rămâne în analiză, fără credit fals).
- Cache pe disc, TTL implicit 1 zi; directorul `.cache/` gitignorat.
- `acp/detalii.py` e PUR: nicio importare de Playwright/rețea; fetcher-ul e injectat.
- `analizeaza` rămâne pură (fără I/O); îmbogățirea stă în orchestrator.
- Toggle `imbogateste=True` default pe orchestrator.
- Direcția și pragurile ajustărilor rămân neschimbate față de Task 11.
- TDD, commit-uri frecvente. Suita fără WeasyPrint: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q` (cele 3 fișiere eșuează la colectare din cauza `libgobject`, nelegat de acest task). Activează venv întâi: `source .venv/bin/activate`.

---

### Task 1: Flag `detalii_complete` pe `Comparabila`

**Files:**
- Modify: `acp/modele.py` (clasa `Comparabila`, după `ajustare_neta_mare`)
- Test: `tests/test_modele.py`

**Interfaces:**
- Produces: `Comparabila.detalii_complete: bool = False`

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_modele.py`:

```python
def test_comparabila_detalii_complete_default_false():
    c = Comparabila(sursa="test", pret_eur=90000.0, supr_totala=60.0)
    assert c.detalii_complete is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modele.py::test_comparabila_detalii_complete_default_false -v`
Expected: FAIL — `detalii_complete` nu există.

- [ ] **Step 3: Write minimal implementation**

În `acp/modele.py`, în clasa `Comparabila`, adaugă imediat după linia `ajustare_neta_mare: bool = False`:

```python
    detalii_complete: bool = False    # True doar după fetch+parse reușit al paginii de detaliu
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_modele.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acp/modele.py tests/test_modele.py
git commit -m "feat(modele): flag detalii_complete pe Comparabila"
```

---

### Task 2: Extractori `extrage_dotari` + `extrage_etaje_total` + constante KW publice

**Files:**
- Modify: `acp/extractie.py`
- Test: `tests/test_extractie.py`

**Interfaces:**
- Produces:
  - `KW_MOBILAT`, `KW_AC`, `KW_BALCON`, `KW_BOXA` (liste publice de cuvinte-cheie, sursa unică — `acp/ajustari.py` le va importa în Task 3)
  - `extrage_dotari(text: str) -> list[str]` → subset din `["mobilat", "aer condiționat", "balcon", "boxă"]`
  - `extrage_etaje_total(text: str) -> int | None`

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_extractie.py`:

```python
from acp.extractie import extrage_dotari, extrage_etaje_total


def test_extrage_dotari_detecteaza_etichete_canonice():
    text = "Apartament mobilat, aer condiționat, 2 balcoane, boxă la subsol"
    d = extrage_dotari(text)
    assert "mobilat" in d
    assert "aer condiționat" in d
    assert "balcon" in d
    assert "boxă" in d


def test_extrage_dotari_gol_cand_lipsesc():
    assert extrage_dotari("apartament 2 camere, etaj 3") == []


def test_extrage_dotari_utilat_conteaza_ca_mobilat():
    # KW_MOBILAT = ["mobilat", "utilat"] → eticheta canonică "mobilat"
    assert "mobilat" in extrage_dotari("complet utilat")


def test_extrage_etaje_total_din_regim_inaltime():
    assert extrage_etaje_total("Regim înălțime: P+8E") == 8
    assert extrage_etaje_total("bloc P+4E cu lift") == 4


def test_extrage_etaje_total_lipsa():
    assert extrage_etaje_total("apartament fără mențiune de regim") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractie.py -v -k "dotari or etaje_total"`
Expected: FAIL — funcțiile nu există.

- [ ] **Step 3: Write minimal implementation**

În `acp/extractie.py`, adaugă `import re` sus (dacă nu există), apoi adaugă constantele publice și funcțiile la finalul fișierului:

```python
import re

# Cuvinte-cheie de dotări — sursă unică; acp/ajustari.py le importă (evită drift).
KW_MOBILAT = ["mobilat", "utilat"]
KW_AC = ["aer conditionat", "aer condiționat", "a/c", "aer cond", "clima"]
KW_BALCON = ["balcon", "terasa", "terasă", "logie"]
KW_BOXA = ["boxa", "boxă", "debara", "camara", "cămară"]

_DOTARI_ETICHETE = [
    ("mobilat", KW_MOBILAT),
    ("aer condiționat", KW_AC),
    ("balcon", KW_BALCON),
    ("boxă", KW_BOXA),
]

_ETAJE_RE = re.compile(r"P\s*\+\s*(\d+)\s*E", re.IGNORECASE)


def extrage_dotari(text: str) -> list[str]:
    """Detectează dotările din text → etichete canonice care conțin cuvintele-cheie KW_*."""
    t = text.lower()
    return [eticheta for eticheta, kws in _DOTARI_ETICHETE if any(k in t for k in kws)]


def extrage_etaje_total(text: str) -> int | None:
    """Parsează regimul de înălțime „P+NE" → N (nr. etaje peste parter)."""
    m = _ETAJE_RE.search(text)
    return int(m.group(1)) if m else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extractie.py -v`
Expected: PASS (toate, inclusiv cele existente).

- [ ] **Step 5: Commit**

```bash
git add acp/extractie.py tests/test_extractie.py
git commit -m "feat(extractie): extrage_dotari + extrage_etaje_total + KW publice"
```

---

### Task 3: Gardă pe dotări în `acp/ajustari.py` (aplică doar când `detalii_complete`)

**Files:**
- Modify: `acp/ajustari.py` (importuri KW + 4 helperi de dotări)
- Test: `tests/test_ajustari.py`

**Interfaces:**
- Consumes: `KW_MOBILAT`, `KW_AC`, `KW_BALCON`, `KW_BOXA` din `acp.extractie`.
- Produces: `_ajustare_mobilat/_ac/_balcon/_boxa` returnează `None` când `comp.detalii_complete is False`.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_ajustari.py`:

```python
def test_dotari_fara_detalii_complete_nu_ajusteaza():
    # subiect are mobilat/AC/balcon/boxă; comparabila fără detalii → nicio ajustare de dotări
    s = _subiect(dotari=["mobilat", "aer condiționat", "balcon", "boxă"])
    c = _comp(dotari=[], detalii_complete=False)
    ajust = calculeaza_ajustari(s, c)
    for factor in ("mobilat", "ac", "balcon", "boxa"):
        assert _factor(ajust, factor) is None


def test_dotari_cu_detalii_complete_ajusteaza():
    s = _subiect(dotari=["mobilat"])
    c = _comp(dotari=[], detalii_complete=True)
    assert _factor(calculeaza_ajustari(s, c), "mobilat") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ajustari.py -v -k "detalii_complete"`
Expected: FAIL — `test_dotari_fara_detalii_complete_nu_ajusteaza` eșuează (dotările se ajustează încă necondiționat).

- [ ] **Step 3: Write minimal implementation**

În `acp/ajustari.py`:

(a) Înlocuiește definițiile locale `_KW_BOXA`, `_KW_MOBILAT`, `_KW_AC`, `_KW_BALCON` (liniile ~22-25) cu un import din extractie. Adaugă lângă importul existent `from acp.extractie import extrage_parcare`:

```python
from acp.extractie import extrage_parcare, KW_MOBILAT, KW_AC, KW_BALCON, KW_BOXA
```

Și în corpul modulului, unde erau `_KW_*`, folosește direct `KW_*`. Concret, `_numara_ac` devine:

```python
def _numara_ac(dotari: list[str]) -> int:
    return sum(1 for d in dotari if any(k in d.lower() for k in KW_AC))
```

(b) La ÎNCEPUTUL fiecăruia din cei 4 helperi de dotări, adaugă garda. Rescrie-i astfel (păstrând restul logicii, dar înlocuind `_KW_*` cu `KW_*`):

```python
def _ajustare_boxa(subiect: Subiect, comp: Comparabila, valoare: float) -> Ajustare | None:
    if not comp.detalii_complete:
        return None
    s, c = _are(subiect.dotari, KW_BOXA), _are(comp.dotari, KW_BOXA)
    if s and not c:
        return Ajustare(factor="boxa", valoare_abs=valoare,
                        motiv="Subiect cu boxă, comparabila fără")
    if c and not s:
        return Ajustare(factor="boxa", valoare_abs=-valoare,
                        motiv="Comparabila cu boxă, subiect fără")
    return None


def _ajustare_mobilat(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if not comp.detalii_complete:
        return None
    s, c = _are(subiect.dotari, KW_MOBILAT), _are(comp.dotari, KW_MOBILAT)
    if s and not c:
        return Ajustare(factor="mobilat", procent=0.04,
                        motiv="Subiect mobilat/utilat, comparabila nu")
    if c and not s:
        return Ajustare(factor="mobilat", procent=-0.04,
                        motiv="Comparabila mobilat/utilat, subiect nu")
    return None


def _ajustare_ac(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if not comp.detalii_complete:
        return None
    diff = _numara_ac(subiect.dotari) - _numara_ac(comp.dotari)
    procent = _plafon(diff * 0.01, 0.03)
    if procent == 0:
        return None
    return Ajustare(factor="ac", procent=procent,
                    motiv=f"A/C: comparabila {_numara_ac(comp.dotari)} vs subiect {_numara_ac(subiect.dotari)}")


def _ajustare_balcon(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if not comp.detalii_complete:
        return None
    s, c = _are(subiect.dotari, KW_BALCON), _are(comp.dotari, KW_BALCON)
    if s and not c:
        return Ajustare(factor="balcon", procent=0.03,
                        motiv="Subiect cu balcon, comparabila fără")
    if c and not s:
        return Ajustare(factor="balcon", procent=-0.03,
                        motiv="Comparabila cu balcon, subiect fără")
    return None
```

- [ ] **Step 4: Update pre-existing amenity tests (legitimate expectation change)**

Rulează `pytest tests/test_ajustari.py -v`. Testele preexistente care așteaptă o ajustare de dotări dar construiesc comparabila FĂRĂ `detalii_complete=True` vor eșua acum — corect, e noua gardă. Identifică-le și adaugă `detalii_complete=True` în apelul `_comp(...)` din fiecare. Candidații așteptați:
- `test_boxa_pe_diferenta_dotari`
- `test_mobilat_procent`
- `test_ac_pe_numar_de_unitati_plafonat`
- `test_balcon_procent`
- `test_garda_marcheaza_ajustare_neta_mare` (folosește balcon în net)

Pentru fiecare eșec, confirmă că e cauzat DOAR de lipsa `detalii_complete` (nu de un bug real) înainte de a-l corecta. Exemplu de corecție într-un astfel de test:

```python
    c = _comp(dotari=[], detalii_complete=True)   # era fără detalii_complete
```

Nu slăbi alte aserțiuni.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_ajustari.py -v`
Expected: PASS.

- [ ] **Step 6: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add acp/ajustari.py tests/test_ajustari.py
git commit -m "feat(ajustari): ajustarea de dotari doar cand comp.detalii_complete"
```

---

### Task 4: `parseaza_detaliu` în `acp/detalii.py` (pur)

**Files:**
- Create: `acp/detalii.py`
- Test: `tests/test_detalii.py`

**Interfaces:**
- Consumes: `extrage_structura/incalzire/stare/parcare/dotari/etaje_total` din `acp.extractie`.
- Produces: `parseaza_detaliu(text: str, an: int | None = None) -> dict` cu cheile `structura, incalzire, stare, stare_incredere, parcare_tip, dotari, etaje_total`.

- [ ] **Step 1: Write the failing test**

Creează `tests/test_detalii.py`:

```python
from acp.detalii import parseaza_detaliu


def test_parseaza_detaliu_extrage_toate_campurile():
    text = (
        "Apartament renovat, structură beton, centrală proprie, mobilat, "
        "aer condiționat, balcon. Garaj subteran inclus. Regim înălțime: P+8E"
    )
    d = parseaza_detaliu(text, an=2015)
    assert d["structura"] == "beton"
    assert d["incalzire"] == "centrala_proprie"
    assert d["stare"] == "renovat"
    assert d["stare_incredere"] > 0.5
    assert d["parcare_tip"] == "owned"
    assert "mobilat" in d["dotari"]
    assert "balcon" in d["dotari"]
    assert d["etaje_total"] == 8


def test_parseaza_detaliu_camp_necunoscut_none():
    d = parseaza_detaliu("apartament 2 camere", an=None)
    assert d["structura"] is None
    assert d["stare"] is None
    assert d["dotari"] == []
    assert d["etaje_total"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detalii.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acp.detalii'`.

- [ ] **Step 3: Write minimal implementation**

Creează `acp/detalii.py`:

```python
"""Motor pur de îmbogățire cu detalii — fără rețea. Fetcher-ul e injectat."""
from __future__ import annotations

from acp.extractie import (
    extrage_structura, extrage_incalzire, extrage_stare,
    extrage_parcare, extrage_dotari, extrage_etaje_total,
)


def parseaza_detaliu(text: str, an: int | None = None) -> dict:
    """Rulează toți extractorii pe textul paginii de detaliu → dict de câmpuri Comparabila."""
    stare, incredere = extrage_stare(text)
    return {
        "structura": extrage_structura(text),
        "incalzire": extrage_incalzire(text),
        "stare": stare,
        "stare_incredere": incredere,
        "parcare_tip": extrage_parcare(text, an),
        "dotari": extrage_dotari(text),
        "etaje_total": extrage_etaje_total(text),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_detalii.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acp/detalii.py tests/test_detalii.py
git commit -m "feat(detalii): parseaza_detaliu (pur)"
```

---

### Task 5: `CacheDetalii` în `acp/cache_detalii.py`

**Files:**
- Create: `acp/cache_detalii.py`
- Test: `tests/test_cache_detalii.py`

**Interfaces:**
- Produces: `CacheDetalii(dir: str = ".cache/detalii", ttl_zile: float = 1.0)` cu `get(url) -> dict | None` și `set(url, campuri) -> None`.

- [ ] **Step 1: Write the failing test**

Creează `tests/test_cache_detalii.py`:

```python
import json
from acp.cache_detalii import CacheDetalii


def test_cache_miss_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    assert c.get("https://x.ro/anunt/1") is None


def test_cache_set_apoi_get_hit(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    campuri = {"structura": "beton", "dotari": ["mobilat"]}
    c.set("https://x.ro/anunt/1", campuri)
    assert c.get("https://x.ro/anunt/1") == campuri


def test_cache_expirat_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    url = "https://x.ro/anunt/1"
    c.set(url, {"structura": "beton"})
    # forțează expirarea: rescrie fetched_at la epoca 0
    p = c._cale(url)
    data = json.loads(p.read_text())
    data["fetched_at"] = 0.0
    p.write_text(json.dumps(data))
    assert c.get(url) is None


def test_cache_fisier_corupt_returneaza_none(tmp_path):
    c = CacheDetalii(dir=str(tmp_path / "d"))
    url = "https://x.ro/anunt/1"
    c._cale(url).write_text("{ not json")
    assert c.get(url) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cache_detalii.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acp.cache_detalii'`.

- [ ] **Step 3: Write minimal implementation**

Creează `acp/cache_detalii.py`:

```python
"""Cache pe disc pentru câmpurile parsate din paginile de detaliu."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class CacheDetalii:
    def __init__(self, dir: str = ".cache/detalii", ttl_zile: float = 1.0):
        self.dir = Path(dir)
        self.ttl_secunde = ttl_zile * 86400
        self.dir.mkdir(parents=True, exist_ok=True)

    def _cale(self, url: str) -> Path:
        h = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return self.dir / f"{h}.json"

    def get(self, url: str) -> dict | None:
        p = self._cale(url)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        if time.time() - data.get("fetched_at", 0.0) > self.ttl_secunde:
            return None
        return data.get("campuri")

    def set(self, url: str, campuri: dict) -> None:
        payload = {"fetched_at": time.time(), "campuri": campuri}
        self._cale(url).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache_detalii.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acp/cache_detalii.py tests/test_cache_detalii.py
git commit -m "feat(cache): CacheDetalii pe disc cu TTL"
```

---

### Task 6: `imbogateste_detalii` în `acp/detalii.py`

**Files:**
- Modify: `acp/detalii.py`
- Test: `tests/test_detalii.py`

**Interfaces:**
- Consumes: `parseaza_detaliu`; `CacheDetalii` (doar tip, injectat); `Comparabila`.
- Produces: `imbogateste_detalii(comparabile: list[Comparabila], fetchers: dict[str, Callable[[str], str | None]], cache=None) -> int` — populează câmpurile + `detalii_complete=True` pe comparabilele cu fetch reușit; întoarce nr. îmbogățite.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_detalii.py`:

```python
from acp.modele import Comparabila
from acp.detalii import imbogateste_detalii


def _c(sursa="imobiliare.ro", url="https://imobiliare.ro/x", an=2015):
    return Comparabila(sursa=sursa, pret_eur=90000.0, supr_totala=60.0, url=url, an=an)


def test_imbogateste_populeaza_si_seteaza_flag():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: "structură beton, mobilat, garaj subteran"}
    n = imbogateste_detalii([c], fetchers)
    assert n == 1
    assert c.detalii_complete is True
    assert c.structura == "beton"
    assert "mobilat" in c.dotari
    assert c.parcare_tip == "owned"


def test_imbogateste_fetch_esuat_lasa_flag_false():
    c = _c()
    fetchers = {"imobiliare.ro": lambda url: None}
    n = imbogateste_detalii([c], fetchers)
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_sursa_fara_fetcher_sarita():
    c = _c(sursa="publi24.ro")
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: "beton"})
    assert n == 0
    assert c.detalii_complete is False


def test_imbogateste_fara_url_sarita():
    c = _c(url=None)
    n = imbogateste_detalii([c], {"imobiliare.ro": lambda url: "beton"})
    assert n == 0


def test_imbogateste_foloseste_cache_evita_fetch(tmp_path):
    from acp.cache_detalii import CacheDetalii
    cache = CacheDetalii(dir=str(tmp_path / "d"))
    c = _c()
    cache.set(c.url, {"structura": "caramida", "incalzire": None, "stare": None,
                      "stare_incredere": 0.0, "parcare_tip": None, "dotari": [],
                      "etaje_total": None})

    def _raise(url):
        raise AssertionError("fetcher nu trebuia apelat (cache hit)")

    n = imbogateste_detalii([c], {"imobiliare.ro": _raise}, cache=cache)
    assert n == 1
    assert c.structura == "caramida"
    assert c.detalii_complete is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detalii.py -v -k "imbogateste"`
Expected: FAIL — `cannot import name 'imbogateste_detalii'`.

- [ ] **Step 3: Write minimal implementation**

În `acp/detalii.py`, adaugă importul de tipuri sus și funcția la final:

```python
from typing import Callable

from acp.modele import Comparabila


def imbogateste_detalii(
    comparabile: list[Comparabila],
    fetchers: dict[str, Callable[[str], str | None]],
    cache=None,
) -> int:
    """Îmbogățește comparabilele cu date din pagina de detaliu.

    Pentru fiecare comparabilă cu `url` și o sursă prezentă în `fetchers`:
    - încearcă cache-ul; la miss apelează fetcher-ul (text) și parsează;
    - populează câmpurile și setează `detalii_complete=True`.
    Fetch eșuat (None) sau sursă fără fetcher → sărită (detalii_complete rămâne False).
    Întoarce numărul de comparabile îmbogățite.
    """
    n = 0
    for c in comparabile:
        if not c.url or c.sursa not in fetchers:
            continue
        campuri = cache.get(c.url) if cache is not None else None
        if campuri is None:
            text = fetchers[c.sursa](c.url)
            if not text:
                continue
            campuri = parseaza_detaliu(text, c.an)
            if cache is not None:
                cache.set(c.url, campuri)
        for cheie, valoare in campuri.items():
            setattr(c, cheie, valoare)
        c.detalii_complete = True
        n += 1
    return n
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_detalii.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add acp/detalii.py tests/test_detalii.py
git commit -m "feat(detalii): imbogateste_detalii cu fetcher injectabil + cache"
```

---

### Task 7: Fetch text detail-page (`acp/connectors/detaliu_fetch.py` + metodă per-conector)

**Files:**
- Create: `acp/connectors/detaliu_fetch.py`
- Modify: `acp/connectors/imobiliare.py`, `acp/connectors/storia.py`, `acp/connectors/olx.py` (adaugă metoda `fetch_detaliu_text`)
- Test: `tests/test_detaliu_fetch.py`

**Interfaces:**
- Produces:
  - `acp.connectors.detaliu_fetch.fetch_detaliu_text(url: str, user_agent: str, timeout_ms: int = 30000, retries: int = 1) -> str | None`
  - `ImobiliareConnector.fetch_detaliu_text(self, url: str) -> str | None` (și analog pe Storia/Olx) — delegă la funcția de mai sus cu `USER_AGENT`-ul propriu.

- [ ] **Step 1: Write the failing test**

Creează `tests/test_detaliu_fetch.py`:

```python
import acp.connectors.detaliu_fetch as df


def test_fetch_detaliu_text_intoarce_textul(monkeypatch):
    async def _fake(url, user_agent, timeout_ms):
        return "text de pe pagina de detaliu"
    monkeypatch.setattr(df, "_extrage_text_pagina", _fake)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA") == "text de pe pagina de detaliu"


def test_fetch_detaliu_text_none_la_eroare(monkeypatch):
    async def _boom(url, user_agent, timeout_ms):
        raise RuntimeError("cloudflare / timeout")
    monkeypatch.setattr(df, "_extrage_text_pagina", _boom)
    assert df.fetch_detaliu_text("https://x.ro/1", "UA", retries=1) is None


def test_connector_deleaga_cu_user_agent_propriu(monkeypatch):
    from acp.connectors.imobiliare import ImobiliareConnector, USER_AGENT
    apeluri = {}

    def _fake_fetch(url, user_agent, timeout_ms=30000, retries=1):
        apeluri["url"] = url
        apeluri["ua"] = user_agent
        return "ok"
    monkeypatch.setattr(df, "fetch_detaliu_text", _fake_fetch)
    conn = ImobiliareConnector()
    assert conn.fetch_detaliu_text("https://imobiliare.ro/y") == "ok"
    assert apeluri["url"] == "https://imobiliare.ro/y"
    assert apeluri["ua"] == USER_AGENT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detaliu_fetch.py -v`
Expected: FAIL — modulul/metodele nu există.

- [ ] **Step 3: Write minimal implementation (shared fetcher)**

Creează `acp/connectors/detaliu_fetch.py`:

```python
"""Fetch textul unei pagini de detaliu (Playwright). Izolat de motorul pur acp/detalii.py."""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright


async def _extrage_text_pagina(url: str, user_agent: str, timeout_ms: int) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=user_agent, locale="ro-RO")
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # lasă Cloudflare/JS să se așeze
            return await page.inner_text("body")
        finally:
            await browser.close()


def fetch_detaliu_text(url: str, user_agent: str, timeout_ms: int = 30000,
                       retries: int = 1) -> str | None:
    """Deschide pagina de detaliu și întoarce textul body-ului, sau None la eșec."""
    for tentativa in range(retries + 1):
        try:
            return asyncio.run(_extrage_text_pagina(url, user_agent, timeout_ms))
        except Exception:
            if tentativa >= retries:
                return None
    return None
```

- [ ] **Step 4: Add the per-connector method (all three)**

În `acp/connectors/imobiliare.py`, adaugă metoda în clasa `ImobiliareConnector`:

```python
    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
```

În `acp/connectors/storia.py`, în clasa `StoriaConnector` (folosește `USER_AGENT`-ul din storia.py):

```python
    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
```

În `acp/connectors/olx.py`, în clasa `OlxConnector` (folosește `USER_AGENT`-ul din olx.py):

```python
    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
```

(Fiecare `USER_AGENT` e deja definit la nivel de modul în fiecare connector — vezi Task 7 din planul Task 11.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_detaliu_fetch.py -v`
Expected: PASS.

- [ ] **Step 6: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add acp/connectors/detaliu_fetch.py acp/connectors/imobiliare.py acp/connectors/storia.py acp/connectors/olx.py tests/test_detaliu_fetch.py
git commit -m "feat(connectors): fetch_detaliu_text per-conector + fetcher Playwright partajat"
```

---

### Task 8: Integrare în orchestrator (`deduplicate_and_analyze` cu `imbogateste`)

**Files:**
- Modify: `acp/core/pipeline.py` (`deduplicate_and_analyze`)
- Test: `tests/test_pipeline_orchestrator.py`

**Interfaces:**
- Consumes: `imbogateste_detalii` din `acp.detalii`; `CacheDetalii` din `acp.cache_detalii`; `filtreaza`, `dedup` din `acp.filtrare`.
- Produces: `deduplicate_and_analyze(self, subiect, comparabile, imbogateste: bool = True, cache=None) -> Analiza`.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_pipeline_orchestrator.py`:

```python
def test_deduplicate_and_analyze_imbogateste_aplica_dotari(orchestrator, subiect_test, tmp_path):
    from acp.modele import Comparabila
    from acp.cache_detalii import CacheDetalii

    # subiectul are mobilat; comparabilele NU au detalii inițial
    subiect_test.dotari = ["mobilat"]
    comps = [
        Comparabila(sursa="imobiliare.ro", pret_eur=95000.0, supr_totala=64.0,
                    url="https://imobiliare.ro/a", an=2010, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=99000.0, supr_totala=66.0,
                    url="https://imobiliare.ro/b", an=2011, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=90000.0, supr_totala=62.0,
                    url="https://imobiliare.ro/c", an=2009, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=102000.0, supr_totala=68.0,
                    url="https://imobiliare.ro/d", an=2012, marcaj="activ"),
    ]
    # toate conectorii orchestratorului primesc un fetch_detaliu_text care spune "fără dotări"
    for conn in orchestrator.connectors:
        conn.fetch_detaliu_text = lambda url: "apartament nefinisat, structură beton"

    cache = CacheDetalii(dir=str(tmp_path / "d"))
    analiza = orchestrator.deduplicate_and_analyze(
        subiect_test, comps, imbogateste=True, cache=cache
    )
    # comparabilele din analiză au fost îmbogățite (detalii_complete True)
    assert all(c.detalii_complete for c in analiza.comparabile)
    # subiectul are mobilat, comparabilele nu → fiecare primește ajustare mobilat +4%
    assert any(any(a.factor == "mobilat" for a in c.ajustari) for c in analiza.comparabile)


def test_deduplicate_and_analyze_fara_imbogatire_nu_ajusteaza_dotari(orchestrator, subiect_test):
    from acp.modele import Comparabila
    subiect_test.dotari = ["mobilat"]
    comps = [
        Comparabila(sursa="imobiliare.ro", pret_eur=95000.0, supr_totala=64.0, an=2010, marcaj="activ"),
        Comparabila(sursa="imobiliare.ro", pret_eur=99000.0, supr_totala=66.0, an=2011, marcaj="activ"),
    ]
    analiza = orchestrator.deduplicate_and_analyze(subiect_test, comps, imbogateste=False)
    # fără îmbogățire, nicio comparabilă nu are detalii_complete → nicio ajustare de mobilat
    assert not any(any(a.factor == "mobilat" for a in c.ajustari) for c in analiza.comparabile)
```

Notă: fixture-urile `orchestrator` și `subiect_test` există deja în `tests/test_pipeline_orchestrator.py`. Dacă `subiect_test` nu are câmp `dotari` mutabil setabil, construiește un `Subiect` local în test cu `dotari=["mobilat"]`.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_orchestrator.py -v -k "imbogateste or imbogatire"`
Expected: FAIL — `deduplicate_and_analyze` nu acceptă `imbogateste`.

- [ ] **Step 3: Write minimal implementation**

În `acp/core/pipeline.py`, adaugă importurile sus (lângă celelalte `from acp...`):

```python
from acp.filtrare import filtreaza, dedup
from acp.detalii import imbogateste_detalii
from acp.cache_detalii import CacheDetalii
```

Înlocuiește semnătura și corpul lui `deduplicate_and_analyze`. Corpul actual construiește `surse` și cheamă `analizeaza(...)`; păstrează acele linii și inserează îmbogățirea înainte:

```python
    def deduplicate_and_analyze(self, subiect: Subiect, comparabile: list[Comparabila],
                                imbogateste: bool = True, cache=None) -> Analiza:
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

        surse = sorted({c.sursa for c in comparabile})
        logger.info(f"deduplicate_and_analyze processing {len(comparabile)} comparabile from {len(surse)} sources")
        analiza = analizeaza(subiect, comparabile, tinta_zile=90, surse=surse)
        logger.info(f"Analysis complete: {analiza.stat_ajustat.n} comparabile retained after filtering")
        return analiza
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline_orchestrator.py -v`
Expected: PASS.

Notă de mediu: `tests/test_pipeline_orchestrator.py` NU importă WeasyPrint, deci rulează normal (spre deosebire de `tests/test_pipeline.py`).

- [ ] **Step 5: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add acp/core/pipeline.py tests/test_pipeline_orchestrator.py
git commit -m "feat(pipeline): imbogatire detalii intre filtrare si analiza (toggle imbogateste)"
```

---

### Task 9: `.gitignore` pentru cache + documentație

**Files:**
- Modify: `.gitignore`, `SKILL.md`, `README.md`

**Interfaces:**
- Consumes: nimic (documentație).
- Produces: `.cache/` gitignorat; documentație actualizată.

- [ ] **Step 1: Gitignore the cache**

Verifică `.gitignore` (`cat .gitignore`). Dacă `.cache/` nu e prezent, adaugă-l pe o linie nouă:

```
.cache/
```

- [ ] **Step 2: Document in SKILL.md**

În `SKILL.md`, în pasul de analiză (unde e descrisă ajustarea comparabilelor — vezi secțiunea „Ajustarea comparabilelor (Task 11)"), adaugă un paragraf:

```markdown
**Îmbogățire cu detalii (Task 12):** înainte de ajustare, orchestratorul deschide pagina de detaliu a fiecărei comparabile relevante (post-filtrare) și extrage dotările reale (structură, încălzire, stare, parcare, mobilat/A/C/balcon/boxă), setând `detalii_complete=True`. Ajustările de dotări se aplică DOAR pe comparabilele îmbogățite — o comparabilă al cărei detaliu n-a putut fi citit rămâne în analiză, dar fără ajustare de dotări (nu primește credit fals). Fetch secvențial, cu cache pe disc (TTL 1 zi). Toggle: `deduplicate_and_analyze(..., imbogateste=False)` sare peste pas pentru viteză (doar etaj/suprafață/vechime credibile).
```

- [ ] **Step 3: Document in README.md**

În `README.md`, la secțiunea de arhitectură/flux, adaugă o linie despre pasul de îmbogățire cu detalii între filtrare și analiză (menționează `acp/detalii.py`, `acp/cache_detalii.py`, cache-ul `.cache/detalii`, TTL 1 zi, toggle `imbogateste`).

- [ ] **Step 4: Commit**

```bash
git add .gitignore SKILL.md README.md
git commit -m "docs: imbogatire cu detalii + gitignore .cache/"
```

---

## Self-Review

**1. Spec coverage:**
- Flag `detalii_complete` → Task 1. ✅
- `extrage_dotari`/`extrage_etaje_total` → Task 2. ✅
- Gardă pe factorii de dotări → Task 3. ✅
- `parseaza_detaliu` (pur) → Task 4. ✅
- `CacheDetalii` (TTL 1 zi) → Task 5. ✅
- `imbogateste_detalii` (fetcher injectabil, cache, skip la eșec/sursă necunoscută) → Task 6. ✅
- Fetch detail-page per-conector (toate trei) + Playwright izolat → Task 7. ✅
- Integrare orchestrator + toggle `imbogateste=True` → Task 8. ✅
- Doar comparabile post-filtrare → Task 8 (`survivors = filtreaza(dedup(vanzari))`). ✅
- `analizeaza` rămâne pură → nemodificată; îmbogățirea în orchestrator. ✅
- `.cache/` gitignorat + docs → Task 9. ✅
- Live manual (final) → pas de controller după merge (nu task de subagent). ✅

**2. Placeholder scan:** Toți pașii de cod au cod complet. Task 3 Step 4 și Task 9 Step 3 conțin instrucțiuni de adaptare (identifică testele afectate / adaugă o linie în README) — acțiuni concrete, nu placeholder-e de logică.

**3. Type consistency:**
- `parseaza_detaliu(text, an=None) -> dict` cu chei `structura/incalzire/stare/stare_incredere/parcare_tip/dotari/etaje_total` — Task 4, consumat identic de `imbogateste_detalii` (Task 6) via `setattr` pe câmpurile omonime din `Comparabila` (existente din Task 11 + `etaje_total` din Task 11). ✅
- `fetch_detaliu_text(url, user_agent, timeout_ms=30000, retries=1) -> str|None` — Task 7, semnătură identică în test și în delegările per-conector. ✅
- `imbogateste_detalii(comparabile, fetchers, cache=None) -> int` — Task 6, apelat identic în orchestrator (Task 8). ✅
- `KW_MOBILAT/KW_AC/KW_BALCON/KW_BOXA` — definite în extractie (Task 2), importate în ajustari (Task 3). ✅
- `CacheDetalii(dir, ttl_zile)` cu `get/set` — Task 5, folosit în Task 6 (test) și Task 8. ✅
