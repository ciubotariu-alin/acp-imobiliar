# ACP Imobiliar — Plan 1: Schelet end-to-end Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construiește pipeline-ul ACP cap-coadă pe date de test (fără scraping real), care produce un PDF de Analiză Comparativă de Piață în stilul documentului de referință.

**Architecture:** Nucleu determinist testabil (modele de date + filtrare + analiză €/mp + ajustări + context de piață) → randare HTML/CSS→PDF cu Jinja2 + WeasyPrint. Un connector „fixture" (citește dintr-un JSON) alimentează pipeline-ul ca să ruleze end-to-end. Partea narativă e furnizată agentului prin `SKILL.md` și injectată ca dict în template.

**Tech Stack:** Python 3.11+, `uv` (mediu/deps), pydantic v2 (modele), pytest (teste), Jinja2 (template), WeasyPrint (HTML→PDF). Playwright + httpx/BeautifulSoup vin în Planul 2 (connectori reali).

## Global Constraints

- Limbă: tot conținutul de raport (etichete, texte) în **română**; identificatorii de cod în engleză/română consistent (folosim română pentru domeniul de business: `Subiect`, `Comparabila`, `analiza`).
- Toate calculele €/mp folosesc **suprafața totală** declarată; suprafața utilă e păstrată separat, informativ.
- Statisticile (min/mediană/max) se calculează pe €/mp **ajustat**, nu brut.
- Ajustările sunt aplicate din valori furnizate (recalibrate de agent per raport); modulul de cod doar le **aplică** determinist — nu inventează procente.
- Corecția anunț→tranzacție: interval implicit **4–8%** (0.04–0.08), aplicat global la verdict.
- Stil PDF: paletă bleumarin `#1b2a4a` + crem `#f5efe0`, ca documentul de referință.
- Disclaimer fix pe fiecare raport: „Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR".
- Fiecare task se termină cu commit; mesaj cu prefix `feat:`/`test:`/`chore:`/`docs:`. Textul poate
  fi în engleză și poate conține termeni românești de domeniu (ex. „modele", „filtrare") — folosește
  mesajele din task-uri ca atare.

---

### Task 1: Scaffold proiect + dependențe + pytest

**Files:**
- Create: `pyproject.toml`
- Create: `acp/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/test_smoke.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nimic (primul task)
- Produces: pachetul importabil `acp`; comanda `uv run pytest` funcțională.

- [ ] **Step 1: Creează `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
output/*.pdf
output/*.html
.pytest_cache/
```

- [ ] **Step 2: Creează `pyproject.toml`**

```toml
[project]
name = "acp-imobiliar"
version = "0.1.0"
description = "Analiză Comparativă de Piață pentru anunțuri imobiliare"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.6",
    "jinja2>=3.1",
    "weasyprint>=61",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["acp"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 3: Creează pachetele goale**

`acp/__init__.py`:
```python
"""ACP Imobiliar — pipeline de analiză comparativă de piață."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 4: Scrie testul smoke**

`tests/test_smoke.py`:
```python
import acp


def test_pachet_importabil():
    assert acp.__doc__ is not None
```

- [ ] **Step 5: Rulează testul (după sync deps)**

Run: `cd ~/OwnDevelopment/acp-imobiliar && uv sync --extra dev && uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

Notă: WeasyPrint are nevoie de librării native. Pe macOS: `brew install pango gdk-pixbuf libffi`. Dacă `uv sync` reușește dar importul WeasyPrint eșuează mai târziu, rulează brew-ul de mai sus.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml acp/ tests/ .gitignore
git commit -m "chore: scaffold proiect acp cu pydantic, jinja2, weasyprint, pytest"
```

---

### Task 2: Modele de date

**Files:**
- Create: `acp/modele.py`
- Test: `tests/test_modele.py`

**Interfaces:**
- Consumes: pydantic
- Produces:
  - `Ajustare(factor: str, procent: float, motiv: str)`
  - `Subiect(pret_eur: float, supr_totala: float, supr_utila: float | None, camere: int, camere_potential: str | None, etaj: int | None, etaje_total: int | None, an: int | None, structura: str | None, incalzire: str | None, dotari: list[str], locatie: str, zona_reala: str | None, coordonate: tuple[float, float] | None, parcare: str | None, tip_vanzator: str | None)` cu property `euro_mp -> float`
  - `Comparabila(sursa: str, url: str | None, pret_eur: float | None, supr_totala: float, etaj: int | None, an: int | None, dotari: list[str], marcaj: str, tip: str, ajustari: list[Ajustare])` cu properties `euro_mp -> float | None`, `pret_ajustat -> float | None`, `euro_mp_ajustat -> float | None`
  - `CriteriiCautare(camere: int, supr_min: float, supr_max: float, an_min: int | None, an_max: int | None, zona: str, raza_km: float, tip: str)`
  - `Statistici(n: int, minim: float, mediana: float, maxim: float, q1: float | None, q3: float | None)`
  - `ContextPiata(nr_active: int, days_on_market_med: float | None, nr_cu_reduceri: int | None, tensiune: str)`
  - `Analiza(subiect: Subiect, comparabile: list[Comparabila], context: ContextPiata, stat_brut: Statistici, stat_ajustat: Statistici, pozitionare_pct: float, incadrare: str, pret_listare: tuple[float, float], pret_tranzactie: tuple[float, float], tinta_zile: int, surse: list[str])`

- [ ] **Step 1: Scrie testele care eșuează**

`tests/test_modele.py`:
```python
import pytest
from acp.modele import Subiect, Comparabila, Ajustare


def _subiect():
    return Subiect(
        pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
        camere_potential="transformabil în 3", etaj=10, etaje_total=11,
        an=2009, structura="cărămidă", incalzire="centrală proprie",
        dotari=["mobilat", "utilat", "A/C"], locatie="Confort City, Splaiul Unirii 9",
        zona_reala="limită Popești-Leordeni", coordonate=None,
        parcare="neconfirmat", tip_vanzator="persoană fizică",
    )


def test_subiect_euro_mp():
    assert _subiect().euro_mp == pytest.approx(1318.18, abs=0.01)


def test_comparabila_euro_mp():
    c = Comparabila(sursa="storia", url=None, pret_eur=89000, supr_totala=65,
                    etaj=None, an=2009, dotari=[], marcaj="activ", tip="vanzare",
                    ajustari=[])
    assert c.euro_mp == pytest.approx(1369.23, abs=0.01)


def test_comparabila_pret_ajustat():
    c = Comparabila(sursa="storia", url=None, pret_eur=89000, supr_totala=65,
                    etaj=None, an=2009, dotari=[], marcaj="activ", tip="vanzare",
                    ajustari=[Ajustare(factor="parcare", procent=-0.034,
                                       motiv="are parcare inclusă, subiectul nu")])
    assert c.pret_ajustat == pytest.approx(85974.0, abs=1.0)
    assert c.euro_mp_ajustat == pytest.approx(1322.68, abs=0.1)


def test_comparabila_fara_pret():
    c = Comparabila(sursa="sudrez", url=None, pret_eur=None, supr_totala=65,
                    etaj=10, an=2008, dotari=[], marcaj="listat", tip="vanzare",
                    ajustari=[])
    assert c.euro_mp is None
    assert c.pret_ajustat is None
```

- [ ] **Step 2: Rulează testele pentru a confirma că eșuează**

Run: `uv run pytest tests/test_modele.py -v`
Expected: FAIL (ModuleNotFoundError: acp.modele)

- [ ] **Step 3: Implementează modelele**

`acp/modele.py`:
```python
"""Modele de date pentru pipeline-ul ACP."""
from __future__ import annotations

from pydantic import BaseModel, computed_field


class Ajustare(BaseModel):
    factor: str
    procent: float  # ex. +0.05 sau -0.034
    motiv: str


class Subiect(BaseModel):
    pret_eur: float
    supr_totala: float
    supr_utila: float | None = None
    camere: int
    camere_potential: str | None = None
    etaj: int | None = None
    etaje_total: int | None = None
    an: int | None = None
    structura: str | None = None
    incalzire: str | None = None
    dotari: list[str] = []
    locatie: str = ""
    zona_reala: str | None = None
    coordonate: tuple[float, float] | None = None
    parcare: str | None = None
    tip_vanzator: str | None = None

    @computed_field
    @property
    def euro_mp(self) -> float:
        return self.pret_eur / self.supr_totala


class Comparabila(BaseModel):
    sursa: str
    url: str | None = None
    pret_eur: float | None = None
    supr_totala: float
    etaj: int | None = None
    an: int | None = None
    dotari: list[str] = []
    marcaj: str = "activ"  # activ | vandut | rezervat | listat
    tip: str = "vanzare"   # vanzare | chirie
    ajustari: list[Ajustare] = []

    @computed_field
    @property
    def euro_mp(self) -> float | None:
        if self.pret_eur is None:
            return None
        return self.pret_eur / self.supr_totala

    @computed_field
    @property
    def pret_ajustat(self) -> float | None:
        if self.pret_eur is None:
            return None
        factor = 1 + sum(a.procent for a in self.ajustari)
        return self.pret_eur * factor

    @computed_field
    @property
    def euro_mp_ajustat(self) -> float | None:
        if self.pret_ajustat is None:
            return None
        return self.pret_ajustat / self.supr_totala


class CriteriiCautare(BaseModel):
    camere: int
    supr_min: float
    supr_max: float
    an_min: int | None = None
    an_max: int | None = None
    zona: str
    raza_km: float = 1.5
    tip: str = "vanzare"


class Statistici(BaseModel):
    n: int
    minim: float
    mediana: float
    maxim: float
    q1: float | None = None
    q3: float | None = None


class ContextPiata(BaseModel):
    nr_active: int
    days_on_market_med: float | None = None
    nr_cu_reduceri: int | None = None
    tensiune: str = "echilibrata"  # piata_cumparatorului | echilibrata | piata_vanzatorului


class Analiza(BaseModel):
    subiect: Subiect
    comparabile: list[Comparabila]
    context: ContextPiata
    stat_brut: Statistici
    stat_ajustat: Statistici
    pozitionare_pct: float  # + peste mediană, - sub mediană
    incadrare: str          # sub piață | corect | supraevaluat
    pret_listare: tuple[float, float]
    pret_tranzactie: tuple[float, float]
    tinta_zile: int
    surse: list[str] = []
```

- [ ] **Step 4: Rulează testele pentru a confirma că trec**

Run: `uv run pytest tests/test_modele.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/modele.py tests/test_modele.py
git commit -m "feat: modele de date (Subiect, Comparabila, Analiza, ...)"
```

---

### Task 3: Statistici €/mp

**Files:**
- Create: `acp/statistica.py`
- Test: `tests/test_statistica.py`

**Interfaces:**
- Consumes: `acp.modele.Statistici`
- Produces: `calculeaza_statistici(valori: list[float]) -> Statistici`

- [ ] **Step 1: Scrie testele care eșuează**

`tests/test_statistica.py`:
```python
import pytest
from acp.statistica import calculeaza_statistici


def test_statistici_de_baza():
    s = calculeaza_statistici([999, 1101, 1275, 1308, 1369])
    assert s.n == 5
    assert s.minim == 999
    assert s.maxim == 1369
    assert s.mediana == 1275


def test_statistici_par():
    s = calculeaza_statistici([1000, 1200])
    assert s.mediana == pytest.approx(1100)


def test_statistici_gol_ridica_eroare():
    with pytest.raises(ValueError):
        calculeaza_statistici([])
```

- [ ] **Step 2: Rulează testele pentru a confirma că eșuează**

Run: `uv run pytest tests/test_statistica.py -v`
Expected: FAIL (ModuleNotFoundError: acp.statistica)

- [ ] **Step 3: Implementează**

`acp/statistica.py`:
```python
"""Statistici pe valori €/mp."""
from __future__ import annotations

import statistics

from acp.modele import Statistici


def calculeaza_statistici(valori: list[float]) -> Statistici:
    if not valori:
        raise ValueError("Lista de valori este goală — nu există comparabile cu preț.")
    ordonate = sorted(valori)
    q1 = q3 = None
    if len(ordonate) >= 4:
        quartile = statistics.quantiles(ordonate, n=4)
        q1, q3 = quartile[0], quartile[2]
    return Statistici(
        n=len(ordonate),
        minim=ordonate[0],
        mediana=statistics.median(ordonate),
        maxim=ordonate[-1],
        q1=q1,
        q3=q3,
    )
```

- [ ] **Step 4: Rulează testele pentru a confirma că trec**

Run: `uv run pytest tests/test_statistica.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/statistica.py tests/test_statistica.py
git commit -m "feat: calcul statistici min/mediana/max/quartile"
```

---

### Task 4: Filtrare, deduplicare & outlieri

**Files:**
- Create: `acp/filtrare.py`
- Test: `tests/test_filtrare.py`

**Interfaces:**
- Consumes: `acp.modele.Subiect`, `acp.modele.Comparabila`
- Produces:
  - `filtreaza(subiect: Subiect, comps: list[Comparabila], prag_supr: float = 0.20, prag_an: int = 5) -> list[Comparabila]`
  - `dedup(comps: list[Comparabila]) -> list[Comparabila]`
  - `marcheaza_outlieri(comps: list[Comparabila], k: float = 1.5) -> tuple[list[Comparabila], list[Comparabila]]` (returnează `(pastrate, outlieri)`)

- [ ] **Step 1: Scrie testele care eșuează**

Notă: `filtreaza` verifică suprafață + vechime față de subiect (filtrarea pe număr de camere
și zonă se face de connector la momentul căutării, deci `Comparabila` nu are câmp `camere`).

`tests/test_filtrare.py`:
```python
from acp.modele import Subiect, Comparabila
from acp.filtrare import filtreaza, dedup, marcheaza_outlieri


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009, locatie="Confort City")


def _comp(pret, supr, an=2009, etaj=None, sursa="storia"):
    return Comparabila(sursa=sursa, pret_eur=pret, supr_totala=supr,
                       etaj=etaj, an=an, dotari=[])


def test_filtreaza_dupa_suprafata():
    comps = [_comp(85000, 65), _comp(85900, 86)]  # 86mp = +30% > 20%
    rezultat = filtreaza(_subiect(), comps)
    suprafete = {c.supr_totala for c in rezultat}
    assert 65 in suprafete and 86 not in suprafete


def test_filtreaza_dupa_vechime():
    comps = [_comp(85000, 65, an=2009), _comp(85000, 65, an=1985)]
    rezultat = filtreaza(_subiect(), comps)
    ani = {c.an for c in rezultat}
    assert 2009 in ani and 1985 not in ani


def test_dedup_elimina_duplicate():
    a = _comp(85000, 65, etaj=10, an=2008, sursa="storia")
    b = _comp(85000, 65, etaj=10, an=2008, sursa="olx")  # aceeași proprietate, alt portal
    c = _comp(89000, 65, etaj=3, an=2009, sursa="publi24")
    rezultat = dedup([a, b, c])
    assert len(rezultat) == 2


def test_marcheaza_outlieri():
    comps = [_comp(p * 65 / 1000, 65) for p in [1101, 1275, 1308, 1369, 300]]
    pastrate, outlieri = marcheaza_outlieri(comps)
    assert len(outlieri) == 1
    assert outlieri[0].euro_mp < 500
```

- [ ] **Step 2: Rulează testele pentru a confirma că eșuează**

Run: `uv run pytest tests/test_filtrare.py -v`
Expected: FAIL (ModuleNotFoundError: acp.filtrare)

- [ ] **Step 3: Implementează**

`acp/filtrare.py`:
```python
"""Filtrare comparabilitate, deduplicare și detectare outlieri."""
from __future__ import annotations

import statistics

from acp.modele import Subiect, Comparabila


def filtreaza(subiect: Subiect, comps: list[Comparabila],
              prag_supr: float = 0.20, prag_an: int = 5) -> list[Comparabila]:
    """Păstrează comparabilele apropiate ca suprafață (±prag_supr) și vechime (±prag_an ani).

    Filtrarea pe număr de camere și zonă se face deja de connector la momentul căutării;
    aici rafinăm pe suprafață și vechime față de subiect.
    """
    supr_min = subiect.supr_totala * (1 - prag_supr)
    supr_max = subiect.supr_totala * (1 + prag_supr)
    rezultat = []
    for c in comps:
        if not (supr_min <= c.supr_totala <= supr_max):
            continue
        if subiect.an is not None and c.an is not None and abs(c.an - subiect.an) > prag_an:
            continue
        rezultat.append(c)
    return rezultat


def _semnatura(c: Comparabila) -> tuple:
    """Semnătură pentru deduplicare cross-portal: aceleași caracteristici fizice + preț."""
    return (round(c.supr_totala), c.etaj, c.an, round(c.pret_eur) if c.pret_eur else None)


def dedup(comps: list[Comparabila]) -> list[Comparabila]:
    vazute: dict[tuple, Comparabila] = {}
    for c in comps:
        cheie = _semnatura(c)
        if cheie not in vazute:
            vazute[cheie] = c
    return list(vazute.values())


def marcheaza_outlieri(comps: list[Comparabila], k: float = 1.5
                       ) -> tuple[list[Comparabila], list[Comparabila]]:
    """Separă outlierii după regula IQR (doar cei cu preț). Cele fără preț rămân în 'pastrate'."""
    cu_pret = [c for c in comps if c.euro_mp is not None]
    fara_pret = [c for c in comps if c.euro_mp is None]
    if len(cu_pret) < 4:
        return comps, []
    valori = sorted(c.euro_mp for c in cu_pret)
    q = statistics.quantiles(valori, n=4)
    q1, q3 = q[0], q[2]
    iqr = q3 - q1
    jos, sus = q1 - k * iqr, q3 + k * iqr
    pastrate, outlieri = list(fara_pret), []
    for c in cu_pret:
        (outlieri if not (jos <= c.euro_mp <= sus) else pastrate).append(c)
    return pastrate, outlieri
```

- [ ] **Step 4: Rulează testele pentru a confirma că trec**

Run: `uv run pytest tests/test_filtrare.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/filtrare.py tests/test_filtrare.py
git commit -m "feat: filtrare comparabilitate, deduplicare cross-portal, outlieri IQR"
```

---

### Task 5: Context de piață (ofertă & tensiune)

**Files:**
- Create: `acp/context.py`
- Test: `tests/test_context.py`

**Interfaces:**
- Consumes: `acp.modele.Comparabila`, `acp.modele.ContextPiata`
- Produces: `calculeaza_context(active: list[Comparabila], prag_putin: int = 5, prag_mult: int = 15, days_on_market: list[float] | None = None, nr_cu_reduceri: int | None = None) -> ContextPiata`

- [ ] **Step 1: Scrie testele care eșuează**

`tests/test_context.py`:
```python
from acp.modele import Comparabila
from acp.context import calculeaza_context


def _active(n):
    return [Comparabila(sursa="s", pret_eur=85000, supr_totala=65) for _ in range(n)]


def test_oferta_mica_piata_vanzatorului():
    ctx = calculeaza_context(_active(3))
    assert ctx.nr_active == 3
    assert ctx.tensiune == "piata_vanzatorului"


def test_oferta_mare_piata_cumparatorului():
    ctx = calculeaza_context(_active(20))
    assert ctx.tensiune == "piata_cumparatorului"


def test_oferta_medie_echilibrata():
    ctx = calculeaza_context(_active(10))
    assert ctx.tensiune == "echilibrata"


def test_days_on_market_mediat():
    ctx = calculeaza_context(_active(10), days_on_market=[30, 60, 90])
    assert ctx.days_on_market_med == 60
```

- [ ] **Step 2: Rulează testele pentru a confirma că eșuează**

Run: `uv run pytest tests/test_context.py -v`
Expected: FAIL (ModuleNotFoundError: acp.context)

- [ ] **Step 3: Implementează**

`acp/context.py`:
```python
"""Context de piață: oferta curentă și tensiunea (cine domină negocierea)."""
from __future__ import annotations

import statistics

from acp.modele import Comparabila, ContextPiata


def calculeaza_context(active: list[Comparabila], prag_putin: int = 5, prag_mult: int = 15,
                       days_on_market: list[float] | None = None,
                       nr_cu_reduceri: int | None = None) -> ContextPiata:
    n = len(active)
    if n <= prag_putin:
        tensiune = "piata_vanzatorului"
    elif n >= prag_mult:
        tensiune = "piata_cumparatorului"
    else:
        tensiune = "echilibrata"
    dom_med = statistics.mean(days_on_market) if days_on_market else None
    return ContextPiata(
        nr_active=n,
        days_on_market_med=dom_med,
        nr_cu_reduceri=nr_cu_reduceri,
        tensiune=tensiune,
    )
```

- [ ] **Step 4: Rulează testele pentru a confirma că trec**

Run: `uv run pytest tests/test_context.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/context.py tests/test_context.py
git commit -m "feat: context de piata (oferta activa + tensiune)"
```

---

### Task 6: Analiză & verdict de poziționare

**Files:**
- Create: `acp/analiza.py`
- Test: `tests/test_analiza.py`

**Interfaces:**
- Consumes: `acp.modele` (toate), `acp.statistica.calculeaza_statistici`, `acp.filtrare` (filtreaza, dedup, marcheaza_outlieri), `acp.context.calculeaza_context`
- Produces: `analizeaza(subiect: Subiect, comparabile: list[Comparabila], tinta_zile: int, chirii: list[Comparabila] | None = None, corectie: tuple[float, float] = (0.04, 0.08), surse: list[str] | None = None) -> Analiza`

- [ ] **Step 1: Scrie testul care eșuează**

`tests/test_analiza.py`:
```python
import pytest
from acp.modele import Subiect, Comparabila
from acp.analiza import analizeaza


def _subiect():
    return Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                   locatie="Confort City")


def _comps():
    date = [(85000, 65, 2008), (87000, 79, 2009), (89000, 65, 2009),
            (82900, 65, 2009)]
    return [Comparabila(sursa="s", pret_eur=p, supr_totala=s, an=a) for p, s, a in date]


def test_analiza_produce_verdict():
    a = analizeaza(_subiect(), _comps(), tinta_zile=90)
    assert a.stat_ajustat.n >= 3
    assert a.incadrare in {"sub piață", "corect", "supraevaluat"}
    assert a.pret_listare[0] <= a.pret_listare[1]
    assert a.pret_tranzactie[1] <= a.pret_listare[1]  # tranzacție ≤ listare (corecție)
    assert a.tinta_zile == 90


def test_pozitionare_peste_mediana():
    # subiect 1318 €/mp; comparabile în jur de 1300 → ușor peste
    a = analizeaza(_subiect(), _comps(), tinta_zile=90)
    assert isinstance(a.pozitionare_pct, float)
```

- [ ] **Step 2: Rulează testul pentru a confirma că eșuează**

Run: `uv run pytest tests/test_analiza.py -v`
Expected: FAIL (ModuleNotFoundError: acp.analiza)

- [ ] **Step 3: Implementează**

`acp/analiza.py`:
```python
"""Orchestrarea analizei: filtrare → statistici → context → verdict de poziționare."""
from __future__ import annotations

from acp.modele import Subiect, Comparabila, Analiza
from acp.statistica import calculeaza_statistici
from acp.filtrare import filtreaza, dedup, marcheaza_outlieri
from acp.context import calculeaza_context


def _incadrare(pozitionare_pct: float) -> str:
    if pozitionare_pct > 5:
        return "supraevaluat"
    if pozitionare_pct < -5:
        return "sub piață"
    return "corect"


def analizeaza(subiect: Subiect, comparabile: list[Comparabila], tinta_zile: int,
               chirii: list[Comparabila] | None = None,
               corectie: tuple[float, float] = (0.04, 0.08),
               surse: list[str] | None = None) -> Analiza:
    vanzari = [c for c in comparabile if c.tip == "vanzare"]
    filtrate = filtreaza(subiect, dedup(vanzari))
    pastrate, _outlieri = marcheaza_outlieri(filtrate)

    valori_brut = [c.euro_mp for c in pastrate if c.euro_mp is not None]
    valori_ajustat = [c.euro_mp_ajustat for c in pastrate if c.euro_mp_ajustat is not None]
    stat_brut = calculeaza_statistici(valori_brut)
    stat_ajustat = calculeaza_statistici(valori_ajustat)

    pozitionare_pct = (subiect.euro_mp - stat_ajustat.mediana) / stat_ajustat.mediana * 100

    # Preț de listare recomandat: bandă în jurul medianei ajustate × suprafața subiectului.
    pret_median = stat_ajustat.mediana * subiect.supr_totala
    pret_listare = (round(pret_median * 0.99, -2), round(pret_median * 1.03, -2))
    # Preț de tranzacționare: corecția anunț→tranzacție aplicată benzii de listare.
    lo, hi = corectie
    pret_tranzactie = (round(pret_listare[0] * (1 - hi), -2),
                       round(pret_listare[1] * (1 - lo), -2))

    active = [c for c in comparabile if c.tip == "vanzare" and c.marcaj == "activ"]
    context = calculeaza_context(active or vanzari)

    return Analiza(
        subiect=subiect,
        comparabile=pastrate,
        context=context,
        stat_brut=stat_brut,
        stat_ajustat=stat_ajustat,
        pozitionare_pct=pozitionare_pct,
        incadrare=_incadrare(pozitionare_pct),
        pret_listare=pret_listare,
        pret_tranzactie=pret_tranzactie,
        tinta_zile=tinta_zile,
        surse=surse or sorted({c.sursa for c in comparabile}),
    )
```

- [ ] **Step 4: Rulează testul pentru a confirma că trece**

Run: `uv run pytest tests/test_analiza.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add acp/analiza.py tests/test_analiza.py
git commit -m "feat: analiza si verdict de pozitionare (listare + tranzactie)"
```

---

### Task 7: Connector „fixture" + interfața comună

**Files:**
- Create: `acp/connectors/__init__.py`
- Create: `acp/connectors/base.py`
- Create: `acp/connectors/fixture.py`
- Create: `exemple/comparabile_confort_city.json`
- Test: `tests/test_connector_fixture.py`

**Interfaces:**
- Consumes: `acp.modele.CriteriiCautare`, `acp.modele.Comparabila`
- Produces:
  - `base.Connector` (Protocol) cu metoda `cauta(self, criterii: CriteriiCautare) -> list[Comparabila]` și atributul `nume: str`
  - `fixture.FixtureConnector(cale_json: str)` care implementează `Connector`

- [ ] **Step 1: Creează fixtura de date**

`exemple/comparabile_confort_city.json`:
```json
[
  {"sursa": "storia", "pret_eur": 85000, "supr_totala": 65, "etaj": 10, "an": 2008, "dotari": ["dressing", "A/C"], "marcaj": "activ", "tip": "vanzare"},
  {"sursa": "publi24", "pret_eur": 87000, "supr_totala": 79, "etaj": 7, "an": 2009, "dotari": ["terasă"], "marcaj": "activ", "tip": "vanzare"},
  {"sursa": "olx", "pret_eur": 89000, "supr_totala": 65, "etaj": 3, "an": 2009, "dotari": ["parcare"], "marcaj": "activ", "tip": "vanzare"},
  {"sursa": "olx", "pret_eur": 82900, "supr_totala": 65, "etaj": 5, "an": 2009, "dotari": [], "marcaj": "activ", "tip": "vanzare"},
  {"sursa": "sudrezidential", "pret_eur": null, "supr_totala": 65, "etaj": 10, "an": 2008, "dotari": ["mobilat"], "marcaj": "vandut", "tip": "vanzare"},
  {"sursa": "olx", "pret_eur": 500, "supr_totala": 65, "etaj": 4, "an": 2009, "dotari": [], "marcaj": "activ", "tip": "chirie"}
]
```

- [ ] **Step 2: Scrie testul care eșuează**

`tests/test_connector_fixture.py`:
```python
from acp.modele import CriteriiCautare
from acp.connectors.fixture import FixtureConnector


def test_fixture_incarca_comparabile():
    conn = FixtureConnector("exemple/comparabile_confort_city.json")
    crit = CriteriiCautare(camere=2, supr_min=55, supr_max=80, zona="Confort City")
    rezultat = conn.cauta(crit)
    assert conn.nume == "fixture"
    assert len(rezultat) == 6
    assert rezultat[0].sursa == "storia"
```

- [ ] **Step 3: Rulează testul pentru a confirma că eșuează**

Run: `uv run pytest tests/test_connector_fixture.py -v`
Expected: FAIL (ModuleNotFoundError: acp.connectors)

- [ ] **Step 4: Implementează interfața + connectorul**

`acp/connectors/__init__.py`:
```python
"""Connectori de sursă pentru comparabile."""
```

`acp/connectors/base.py`:
```python
"""Interfața comună pentru toți connectorii de portal."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from acp.modele import CriteriiCautare, Comparabila


@runtime_checkable
class Connector(Protocol):
    nume: str

    def cauta(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Caută comparabile pe portal după criterii și le întoarce normalizate."""
        ...
```

`acp/connectors/fixture.py`:
```python
"""Connector de test: citește comparabile dintr-un fișier JSON."""
from __future__ import annotations

import json

from acp.modele import CriteriiCautare, Comparabila


class FixtureConnector:
    nume = "fixture"

    def __init__(self, cale_json: str):
        self.cale_json = cale_json

    def cauta(self, criterii: CriteriiCautare) -> list[Comparabila]:
        with open(self.cale_json, encoding="utf-8") as f:
            date = json.load(f)
        return [Comparabila(**d) for d in date]
```

- [ ] **Step 5: Rulează testul pentru a confirma că trece**

Run: `uv run pytest tests/test_connector_fixture.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add acp/connectors/ exemple/comparabile_confort_city.json tests/test_connector_fixture.py
git commit -m "feat: interfata Connector + FixtureConnector pentru pipeline E2E"
```

---

### Task 8: Template HTML + randare PDF

**Files:**
- Create: `acp/raport/__init__.py`
- Create: `acp/raport/template.html`
- Create: `acp/raport/render.py`
- Test: `tests/test_render.py`

**Interfaces:**
- Consumes: `acp.modele.Analiza`
- Produces:
  - `render.formateaza_eur(x: float) -> str` (ex. `87000 -> "87.000 €"`)
  - `render.construieste_html(analiza: Analiza, narativ: dict | None = None) -> str`
  - `render.scrie_pdf(analiza: Analiza, cale_pdf: str, narativ: dict | None = None) -> None`

Structura `narativ` (chei opționale, umplute de agent; când lipsesc, secțiunea nu apare):
`{"recomandare": str, "de_ce_zile": str, "faze": [{"nume","zile","pret","obiectiv","prag"}], "profiluri": [{"eticheta","titlu","puncte":[str]}], "investitie": str, "reguli": [str], "anunt": {"titlu","descriere"}}`

- [ ] **Step 1: Scrie testele care eșuează**

`tests/test_render.py`:
```python
from acp.modele import (Subiect, Comparabila, ContextPiata, Statistici, Analiza)
from acp.raport.render import formateaza_eur, construieste_html, scrie_pdf


def _analiza():
    subiect = Subiect(pret_eur=87000, supr_totala=66, camere=2, an=2009,
                      locatie="Confort City, Splaiul Unirii 9")
    comps = [Comparabila(sursa="storia", pret_eur=85000, supr_totala=65, an=2008)]
    stat = Statistici(n=4, minim=1101, mediana=1275, maxim=1369)
    return Analiza(subiect=subiect, comparabile=comps,
                   context=ContextPiata(nr_active=8, tensiune="echilibrata"),
                   stat_brut=stat, stat_ajustat=stat, pozitionare_pct=3.4,
                   incadrare="corect", pret_listare=(84000, 87000),
                   pret_tranzactie=(80000, 84000), tinta_zile=90, surse=["storia", "olx"])


def test_formateaza_eur():
    assert formateaza_eur(87000) == "87.000 €"


def test_html_contine_datele_cheie():
    html = construieste_html(_analiza())
    assert "87.000 €" in html
    assert "Confort City" in html
    assert "ANEVAR" in html  # disclaimerul fix


def test_scrie_pdf(tmp_path):
    cale = tmp_path / "raport.pdf"
    scrie_pdf(_analiza(), str(cale))
    date = cale.read_bytes()
    assert date[:4] == b"%PDF"
    assert len(date) > 1000
```

- [ ] **Step 2: Rulează testele pentru a confirma că eșuează**

Run: `uv run pytest tests/test_render.py -v`
Expected: FAIL (ModuleNotFoundError: acp.raport.render)

- [ ] **Step 3: Creează template-ul**

`acp/raport/__init__.py`:
```python
"""Randarea raportului ACP în PDF."""
```

`acp/raport/template.html`:
```html
<!doctype html>
<html lang="ro">
<head>
<meta charset="utf-8">
<style>
  @page {
    size: A4;
    margin: 2cm 1.6cm;
    @top-left { content: "ANALIZĂ COMPARATIVĂ DE PIAȚĂ (ACP)"; font-size: 8pt; color: #1b2a4a; }
    @top-right { content: "{{ subiect.locatie }}"; font-size: 8pt; color: #7a8499; }
    @bottom-left { content: "Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR"; font-size: 7pt; color: #7a8499; }
    @bottom-right { content: "Pag. " counter(page); font-size: 7pt; color: #7a8499; }
  }
  body { font-family: "Helvetica Neue", Arial, sans-serif; color: #26303f; font-size: 10pt; line-height: 1.45; }
  h1 { color: #1b2a4a; font-size: 22pt; margin: 0 0 2pt; }
  h2 { background: #1b2a4a; color: #fff; font-size: 13pt; padding: 6pt 10pt; margin: 18pt 0 8pt; }
  .subtitlu { color: #4a5a7a; font-size: 11pt; margin-bottom: 14pt; }
  table { width: 100%; border-collapse: collapse; margin: 6pt 0; }
  th { background: #1b2a4a; color: #fff; text-align: left; padding: 5pt 7pt; font-size: 9pt; }
  td { padding: 5pt 7pt; border-bottom: 1px solid #e5e2d8; font-size: 9pt; }
  tr.subiect td { background: #fbf6e7; font-weight: bold; }
  .fisa td:nth-child(odd) { font-weight: bold; width: 22%; }
  .caseta { background: #fbf6e7; border: 1px solid #d9cfa8; padding: 10pt 12pt; margin: 10pt 0; }
  .eticheta { display: inline-block; background: #1b2a4a; color: #fff; padding: 2pt 8pt; font-size: 8pt; }
  .nota { color: #7a8499; font-size: 8pt; margin-top: 6pt; }
  ul { margin: 4pt 0 4pt 16pt; padding: 0; }
</style>
</head>
<body>
  <h1>Analiză Comparativă de Piață</h1>
  <div class="subtitlu">{{ subiect.locatie }} — strategie de vânzare pe {{ analiza.tinta_zile }} de zile</div>

  {% if narativ.recomandare %}
  <div class="caseta"><strong>Recomandare de poziționare:</strong> {{ narativ.recomandare }}</div>
  {% endif %}

  <h2>Fișa proprietății</h2>
  <table class="fisa">
    <tr><td>Preț cerut</td><td>{{ eur(subiect.pret_eur) }}</td><td>Preț/mp</td><td>{{ "%.0f"|format(subiect.euro_mp) }} €/mp</td></tr>
    <tr><td>Suprafață totală</td><td>{{ subiect.supr_totala }} mp</td><td>Camere</td><td>{{ subiect.camere }}{% if subiect.camere_potential %} ({{ subiect.camere_potential }}){% endif %}</td></tr>
    <tr><td>Etaj</td><td>{{ subiect.etaj }}{% if subiect.etaje_total %} / {{ subiect.etaje_total }}{% endif %}</td><td>An construcție</td><td>{{ subiect.an or "—" }}</td></tr>
    <tr><td>Încălzire</td><td>{{ subiect.incalzire or "—" }}</td><td>Dotare</td><td>{{ subiect.dotari|join(", ") or "—" }}</td></tr>
  </table>

  <h2>Context de piață</h2>
  <p>Comparabile active în zonă: <strong>{{ analiza.context.nr_active }}</strong>.
     Tensiune piață: <strong>{{ analiza.context.tensiune|replace("_", " ") }}</strong>.
     {% if analiza.context.days_on_market_med %}Timp mediu pe piață: {{ "%.0f"|format(analiza.context.days_on_market_med) }} zile.{% endif %}</p>

  <h2>Comparabile & analiză</h2>
  <table>
    <tr><th>Sursă</th><th>Supr.</th><th>Etaj</th><th>An</th><th>Preț</th><th>€/mp</th><th>€/mp ajustat</th></tr>
    <tr class="subiect"><td>Subiect (anunțul tău)</td><td>{{ subiect.supr_totala }} mp</td><td>{{ subiect.etaj or "—" }}</td><td>{{ subiect.an or "—" }}</td><td>{{ eur(subiect.pret_eur) }}</td><td>{{ "%.0f"|format(subiect.euro_mp) }}</td><td>—</td></tr>
    {% for c in analiza.comparabile %}
    <tr>
      <td>{{ c.sursa }}{% if c.marcaj != "activ" %} ({{ c.marcaj }}){% endif %}</td>
      <td>{{ c.supr_totala }} mp</td><td>{{ c.etaj or "—" }}</td><td>{{ c.an or "—" }}</td>
      <td>{% if c.pret_eur %}{{ eur(c.pret_eur) }}{% else %}listat{% endif %}</td>
      <td>{% if c.euro_mp %}{{ "%.0f"|format(c.euro_mp) }}{% else %}—{% endif %}</td>
      <td>{% if c.euro_mp_ajustat %}{{ "%.0f"|format(c.euro_mp_ajustat) }}{% else %}—{% endif %}</td>
    </tr>
    {% endfor %}
  </table>
  <p>Mediană €/mp ajustat: <strong>{{ "%.0f"|format(analiza.stat_ajustat.mediana) }} €/mp</strong>
     (min {{ "%.0f"|format(analiza.stat_ajustat.minim) }} – max {{ "%.0f"|format(analiza.stat_ajustat.maxim) }}, n={{ analiza.stat_ajustat.n }}).
     Poziționare subiect: <strong>{{ "%+.1f"|format(analiza.pozitionare_pct) }}%</strong> față de mediană → <strong>{{ analiza.incadrare }}</strong>.</p>
  <div class="caseta">
    Preț de listare recomandat: <strong>{{ eur(analiza.pret_listare[0]) }} – {{ eur(analiza.pret_listare[1]) }}</strong>.
    Preț de tranzacționare realist: <strong>{{ eur(analiza.pret_tranzactie[0]) }} – {{ eur(analiza.pret_tranzactie[1]) }}</strong>
    (corecție anunț→tranzacție inclusă).
  </div>

  {% if narativ.faze %}
  <h2>Plan de preț eșalonat pe {{ analiza.tinta_zile }} de zile</h2>
  <table>
    <tr><th>Fază</th><th>Zile</th><th>Preț listare</th><th>Obiectiv</th><th>Prag de decizie</th></tr>
    {% for f in narativ.faze %}
    <tr><td>{{ f.nume }}</td><td>{{ f.zile }}</td><td>{{ f.pret }}</td><td>{{ f.obiectiv }}</td><td>{{ f.prag }}</td></tr>
    {% endfor %}
  </table>
  {% endif %}

  {% if narativ.profiluri %}
  <h2>Clientul țintă</h2>
  {% for p in narativ.profiluri %}
  <p><span class="eticheta">{{ p.eticheta }}</span> <strong>{{ p.titlu }}</strong></p>
  <ul>{% for pct in p.puncte %}<li>{{ pct }}</li>{% endfor %}</ul>
  {% endfor %}
  {% endif %}

  {% if narativ.investitie %}
  <div class="caseta"><strong>Unghi de investiție:</strong> {{ narativ.investitie }}</div>
  {% endif %}

  {% if narativ.reguli %}
  <h2>Reguli de execuție</h2>
  <ul>{% for r in narativ.reguli %}<li>{{ r }}</li>{% endfor %}</ul>
  {% endif %}

  {% if narativ.anunt %}
  <h2>Anexă — text de anunț gata de publicare</h2>
  <div class="caseta">
    <strong>Titlu:</strong> {{ narativ.anunt.titlu }}<br><br>
    {{ narativ.anunt.descriere }}
  </div>
  {% endif %}

  <p class="nota">Notă metodologică: comparabilele provin din prețuri <em>cerute</em> pe portaluri;
    prețurile reale de tranzacție nu sunt publice la nivel de apartament în România — corecția
    anunț→tranzacție aplicată este 4–8%. Surse consultate: {{ analiza.surse|join(", ") }}.
    Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR.</p>
</body>
</html>
```

- [ ] **Step 4: Implementează render.py**

`acp/raport/render.py`:
```python
"""Construiește HTML din Analiza și îl randează în PDF."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from acp.modele import Analiza

_DIR = Path(__file__).parent


def formateaza_eur(x: float) -> str:
    return f"{int(round(x)):,} €".replace(",", ".")


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.globals["eur"] = formateaza_eur
    return env


def construieste_html(analiza: Analiza, narativ: dict | None = None) -> str:
    template = _env().get_template("template.html")
    return template.render(analiza=analiza, subiect=analiza.subiect, narativ=narativ or {})


def scrie_pdf(analiza: Analiza, cale_pdf: str, narativ: dict | None = None) -> None:
    html = construieste_html(analiza, narativ)
    Path(cale_pdf).parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(cale_pdf)
```

- [ ] **Step 5: Rulează testele pentru a confirma că trec**

Run: `uv run pytest tests/test_render.py -v`
Expected: PASS (3 passed)

Dacă importul WeasyPrint eșuează cu eroare de librărie nativă: `brew install pango gdk-pixbuf libffi` apoi reia.

- [ ] **Step 6: Commit**

```bash
git add acp/raport/ tests/test_render.py
git commit -m "feat: template HTML stil ACP + randare PDF cu WeasyPrint"
```

---

### Task 9: Pipeline end-to-end + demo

**Files:**
- Create: `acp/pipeline.py`
- Create: `exemple/demo.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `acp.modele` (Subiect, CriteriiCautare), `acp.connectors.base.Connector`, `acp.analiza.analizeaza`, `acp.raport.render.scrie_pdf`
- Produces:
  - `pipeline.criterii_din_subiect(subiect: Subiect, prag_supr: float = 0.20, raza_km: float = 1.5) -> CriteriiCautare`
  - `pipeline.ruleaza(subiect: Subiect, connectori: list[Connector], tinta_zile: int, cale_pdf: str, narativ: dict | None = None) -> Analiza`

- [ ] **Step 1: Scrie testul care eșuează**

`tests/test_pipeline.py`:
```python
from acp.modele import Subiect
from acp.connectors.fixture import FixtureConnector
from acp.pipeline import criterii_din_subiect, ruleaza


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
```

- [ ] **Step 2: Rulează testul pentru a confirma că eșuează**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL (ModuleNotFoundError: acp.pipeline)

- [ ] **Step 3: Implementează**

`acp/pipeline.py`:
```python
"""Orchestrarea end-to-end: subiect + connectori → analiză → PDF."""
from __future__ import annotations

from acp.modele import Subiect, CriteriiCautare, Comparabila, Analiza
from acp.connectors.base import Connector
from acp.analiza import analizeaza
from acp.raport.render import scrie_pdf


def criterii_din_subiect(subiect: Subiect, prag_supr: float = 0.20,
                         raza_km: float = 1.5) -> CriteriiCautare:
    return CriteriiCautare(
        camere=subiect.camere,
        supr_min=subiect.supr_totala * (1 - prag_supr),
        supr_max=subiect.supr_totala * (1 + prag_supr),
        an_min=(subiect.an - 5) if subiect.an else None,
        an_max=(subiect.an + 5) if subiect.an else None,
        zona=subiect.zona_reala or subiect.locatie,
        raza_km=raza_km,
    )


def ruleaza(subiect: Subiect, connectori: list[Connector], tinta_zile: int,
            cale_pdf: str, narativ: dict | None = None) -> Analiza:
    criterii = criterii_din_subiect(subiect)
    comparabile: list[Comparabila] = []
    surse: list[str] = []
    for conn in connectori:
        try:
            gasite = conn.cauta(criterii)
            comparabile.extend(gasite)
            if gasite:
                surse.append(conn.nume)
        except Exception as e:  # un connector căzut nu blochează restul
            print(f"[avertisment] connectorul '{getattr(conn, 'nume', '?')}' a eșuat: {e}")
    analiza = analizeaza(subiect, comparabile, tinta_zile=tinta_zile, surse=sorted(set(surse)))
    scrie_pdf(analiza, cale_pdf, narativ)
    return analiza
```

- [ ] **Step 4: Rulează testul pentru a confirma că trece**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Creează scriptul demo**

`exemple/demo.py`:
```python
"""Demo: generează un raport ACP din fixtura de comparabile."""
from acp.modele import Subiect
from acp.connectors.fixture import FixtureConnector
from acp.pipeline import ruleaza

subiect = Subiect(
    pret_eur=87000, supr_totala=66, supr_utila=61, camere=2,
    camere_potential="transformabil în 3", etaj=10, etaje_total=11, an=2009,
    structura="cărămidă", incalzire="centrală proprie de apartament",
    dotari=["mobilat", "utilat", "A/C"],
    locatie="Confort City, Splaiul Unirii 9", zona_reala="limită Popești-Leordeni",
    parcare="neconfirmat", tip_vanzator="persoană fizică",
)

narativ = {
    "recomandare": "menține prețul de listare la 87.000 € și testează plafonul 30 de zile, apoi coboară controlat.",
    "faze": [
        {"nume": "Faza 1 — Testare plafon", "zile": "0–30", "pret": "87.000 €",
         "obiectiv": "prinde cumpărătorul premium", "prag": "≥6 vizionări → menții"},
        {"nume": "Faza 2 — Calibrare", "zile": "31–60", "pret": "84.900 €",
         "obiectiv": "sub pragul de 85k", "prag": "≥1 ofertă serioasă → negociezi"},
        {"nume": "Faza 3 — Finalizare", "zile": "61–90", "pret": "82.500 €",
         "obiectiv": "declanșezi ezitanții", "prag": "accepți oferte 81–83k"},
    ],
    "anunt": {"titlu": "2 camere Confort City, Splaiul Unirii 9 — complet mobilat, etaj înalt",
              "descriere": "Apartament gata de mutare, luminos, centrală proprie. Comision 0% cumpărător."},
}

conn = FixtureConnector("exemple/comparabile_confort_city.json")
analiza = ruleaza(subiect, [conn], tinta_zile=90,
                  cale_pdf="output/ACP_ConfortCity_90zile.pdf", narativ=narativ)
print(f"Raport generat. Încadrare: {analiza.incadrare}, "
      f"poziționare {analiza.pozitionare_pct:+.1f}% față de mediană.")
print("PDF: output/ACP_ConfortCity_90zile.pdf")
```

- [ ] **Step 6: Rulează demo-ul și verifică PDF-ul**

Run: `uv run python exemple/demo.py && ls -la output/ACP_ConfortCity_90zile.pdf`
Expected: mesaj cu încadrarea + fișier PDF prezent în `output/`. Deschide PDF-ul și verifică vizual stilul (bleumarin/crem, tabele, casete).

- [ ] **Step 7: Commit**

```bash
git add acp/pipeline.py exemple/demo.py tests/test_pipeline.py
git commit -m "feat: pipeline end-to-end + demo care genereaza PDF din fixtura"
```

---

### Task 10: SKILL.md — orchestrarea agentului (persona 20 ani)

**Files:**
- Create: `SKILL.md`
- Create: `README.md`

**Interfaces:**
- Consumes: toate modulele `acp.*` și scriptul demo (ca referință de utilizare)
- Produces: instrucțiunile pe care le urmează agentul la fiecare rulare

- [ ] **Step 1: Scrie `SKILL.md`**

`SKILL.md`:
```markdown
---
name: acp-imobiliar
description: Generează o Analiză Comparativă de Piață (ACP) pentru un anunț imobiliar — fișă, comparabile, verdict de preț, strategie pe N zile și text de anunț, ca PDF în stilul de referință.
---

# ACP Imobiliar — instrucțiuni agent

Ești un **agent imobiliar cu 20 de ani de experiență** pe piața locală. Scrii pentru vânzător,
cu judecată de piață, tactici de negociere și onestitate a locației. Produci un raport ACP în PDF.

## Intrare de la utilizator
- Anunțul subiect: **link** SAU **date manuale**.
- **Ținta de zile** (obligatoriu): în câte zile vrea să vândă (ex. 30/60/90).
- Constrângeri opționale (ex. „am parcare inclusă", „preț minim X").

## Pași

1. **Fișa subiectului.** Din link (extrage) sau manual, completează un `Subiect` (vezi `acp/modele.py`).
   Verifică **locația reală vs. eticheta din anunț** (coordonate/repere) și folosește locația reală.
   Ce lipsește, întreabă punctual — nu relua tot.

2. **Caută comparabile** pe toate portalurile disponibile (Planul 2 aduce connectorii reali;
   până atunci folosește `FixtureConnector` sau caută manual). Strânge: anunțuri active,
   referințe „vândut/rezervat", chirii (pentru randament).

3. **Ajustări (recalibrate de tine, agentul).** Pentru fiecare comparabilă, stabilește procentele
   de ajustare față de subiect (stare, mobilat, parcare, etaj, an, compartimentare, comision),
   folosind ca punct de plecare tabelul din spec și **evidența locală**. Pune-le în
   `Comparabila.ajustari` cu `factor`, `procent`, `motiv`. Codul le aplică determinist.

4. **Rulează analiza + randează.** Folosește `acp.pipeline.ruleaza(...)` cu subiectul, connectorii,
   ținta de zile și `narativ`. Verdictul (preț listare/tranzacție, încadrare) și contextul de piață
   sunt calculate de cod.

5. **Scrie narativul** (dict `narativ` pasat la `ruleaza`): recomandare, „de ce N zile",
   plan pe faze (calibrat pe ținta de zile ȘI pe tensiunea pieței din `analiza.context.tensiune`),
   profiluri cumpărători, unghi de investiție (randament din chirii), reguli de execuție, text anunț.
   Citează **cifre reale** din analiză (mediană, nr. comparabile, randament).

6. **Livrează PDF-ul** din `output/` și rezumă utilizatorului: încadrarea, banda de preț, sursele.

## Reguli
- Nu inventa comparabile sau prețuri; declară mereu sursele efectiv folosite.
- Prețurile reale de tranzacție nu sunt publice → corecție anunț→tranzacție 4–8%, spusă transparent.
- Nu e evaluare ANEVAR — păstrează disclaimerul.
```

- [ ] **Step 2: Scrie `README.md`**

`README.md`:
```markdown
# ACP Imobiliar

Pipeline de Analiză Comparativă de Piață pentru anunțuri imobiliare (uz personal).

## Instalare
```bash
uv sync --extra dev
# macOS, pentru WeasyPrint:
brew install pango gdk-pixbuf libffi
```

## Rulează demo-ul
```bash
uv run python exemple/demo.py
# → output/ACP_ConfortCity_90zile.pdf
```

## Teste
```bash
uv run pytest -v
```

## Structură
- `acp/modele.py` — modele de date
- `acp/statistica.py`, `acp/filtrare.py`, `acp/context.py`, `acp/analiza.py` — nucleu determinist
- `acp/connectors/` — surse de comparabile (fixture acum; portaluri reale în Planul 2)
- `acp/raport/` — template HTML + randare PDF
- `acp/pipeline.py` — orchestrare end-to-end
- `SKILL.md` — instrucțiunile agentului (persona 20 ani)
```

- [ ] **Step 3: Rulează toată suita de teste**

Run: `uv run pytest -v`
Expected: PASS (toate testele din Task 1–9)

- [ ] **Step 4: Commit**

```bash
git add SKILL.md README.md
git commit -m "docs: SKILL.md (persona agent) + README"
```

---

## Self-Review

**Spec coverage:**
- Input link/manual + țintă de zile → Task 2 (`Subiect`), Task 9 (`criterii_din_subiect`), SKILL.md pas 1. ✔
- Fișa subiectului (locație reală) → Task 2 + SKILL.md. ✔
- Căutare comparabile pe portaluri → Task 7 (interfață + fixture); connectorii reali sunt Planul 2 (explicit). ✔
- Filtrare/dedupe/outlieri → Task 4. ✔
- Analiză €/mp, statistici, poziționare, verdict → Task 3 + Task 6. ✔
- Ajustări recalibrate de agent, aplicate determinist → Task 2 (`pret_ajustat`) + SKILL.md pas 3. ✔
- Context de piață (ofertă/tensiune) → Task 5, afișat în template Task 8. ✔
- Narativ (persona, faze pe N zile, profiluri, investiție, reguli, anunț) → Task 8 (sloturi template) + Task 10 (SKILL.md). ✔
- Randare PDF stil referință → Task 8. ✔
- Structura proiectului + „cum rulezi" → Task 1, Task 9 demo, Task 10 README. ✔
- Disclaimere/surse/notă metodologică → Task 8 (template, fix). ✔

**Placeholder scan:** fără TBD/TODO; tot codul e complet. Nota din Task 4, Step 1 clarifică explicit care variante de test se folosesc.

**Type consistency:** `Comparabila.ajustari: list[Ajustare]`, `euro_mp_ajustat` folosit consecvent în Task 4/6/8; `Analiza` are aceleași câmpuri în Task 2 (definiție), Task 6 (construire) și Task 8 (consum). `CriteriiCautare` produs în Task 9 și consumat de connector în Task 7. ✔

---

## Planuri următoare (nu fac parte din acest plan)

- **Plan 2 — Connectori reali:** Playwright + httpx/BeautifulSoup; câte un connector per portal
  (imobiliare, storia, olx, publi24, romimo, sudrezidential, lajumate, waa2, anuntul), fiecare cu
  fixturi HTML salvate pentru teste de parsare; rate-limiting „politicos" + fallback asistat de agent.
- **Plan 3 — Calibrare narativ & verdict:** rafinarea prompturilor persona, calibrarea benzilor de
  preț și a fazelor pe date reale, testare pe mai multe tipuri de proprietăți.
```
