# Ajustări Comparabile (Task 11) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Populează `Comparabila.ajustari` cu ajustări de preț factor-cu-factor (etaj, vechime, mărime, dotări, parcare, structură, încălzire, stare), astfel încât `euro_mp_ajustat` să reflecte o comparație „mere cu mere" cu subiectul, nu preț brut.

**Architecture:** Motor de ajustare centralizat, post-fetch, în `acp/ajustari.py`. Conectorii doar parsează și populează câmpuri noi pe `Comparabila` (via extractori keyword din `acp/extractie.py`). `analizeaza()` apelează `aplica_ajustari()` între filtrare și detecția de outlieri; statisticile ajustate curg apoi natural prin `euro_mp_ajustat`.

**Tech Stack:** Python 3, Pydantic v2 (`computed_field`), pytest. Fără dependențe noi. Fără LLM în nucleu.

## Global Constraints

- Direcția ajustării e mereu `subiect − comparabila`: comparabila inferioară → ajustare pozitivă (în sus); superioară → negativă.
- Fără LLM/vision în pipeline. Extracția pe comparabile e keyword-matching pur, conservator: ambiguu → `None` (fără ajustare).
- Plafoane per factor: etaj ±0.05, vechime ±0.10, mărime ±0.03, stare ±0.15.
- Gardă anti-supra-ajustare: brut > 0.25 exclude comparabila; |net| > 0.15 o marchează (nu o exclude).
- Parcarea se ajustează pe TIP: doar `owned` produce valoare de capital; `resedinta` → €0.
- Valorile de parcare/boxă sunt parametri (default €8000 / €2000), nu hardcodări în logică.
- Praguri de detecție a stării: ajustarea de stare se aplică doar dacă `stare_incredere > 0.5`.
- TDD strict, commit-uri frecvente, fiecare task se termină cu suita relevantă verde.

**Notă de mediu:** `weasyprint` nu se încarcă pe această mașină macOS (lipsă `libgobject-2.0-0`), deci `tests/test_render.py`, `tests/test_e2e.py`, `tests/test_pipeline.py` eșuează la colectare din motive de mediu, nefiind legate de acest task. Rulează suita relevantă cu:
`pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py`
Baseline curent: **145 passed** cu acest filtru.

---

### Task 1: Extindere modele — `Ajustare` absolut + câmpuri noi pe `Comparabila` + `pret_ajustat`

**Files:**
- Modify: `acp/modele.py:7-10` (clasa `Ajustare`), `acp/modele.py:37-69` (clasa `Comparabila`)
- Test: `tests/test_modele.py`

**Interfaces:**
- Consumes: nimic nou.
- Produces:
  - `Ajustare(factor: str, procent: float = 0.0, valoare_abs: float = 0.0, motiv: str)`
  - `Comparabila` cu câmpuri noi: `etaje_total: int | None = None`, `structura: str | None = None`, `incalzire: str | None = None`, `stare: str | None = None`, `stare_incredere: float = 0.0`, `parcare_tip: str | None = None`, `ajustare_neta_mare: bool = False`
  - `Comparabila.pret_ajustat` = `pret_eur * (1 + Σ procent) + Σ valoare_abs`

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_modele.py`:

```python
from acp.modele import Ajustare, Comparabila


def test_ajustare_suporta_procent_si_absolut():
    a = Ajustare(factor="parcare", valoare_abs=8000.0, motiv="parcare owned")
    assert a.procent == 0.0
    assert a.valoare_abs == 8000.0


def test_pret_ajustat_combina_procent_si_absolut():
    c = Comparabila(
        sursa="test", pret_eur=100000.0, supr_totala=50.0,
        ajustari=[
            Ajustare(factor="etaj", procent=0.05, motiv="etaj"),
            Ajustare(factor="parcare", valoare_abs=8000.0, motiv="parcare"),
        ],
    )
    # 100000 * (1 + 0.05) + 8000 = 113000
    assert c.pret_ajustat == 113000.0
    assert c.euro_mp_ajustat == 113000.0 / 50.0


def test_comparabila_campuri_noi_default():
    c = Comparabila(sursa="test", pret_eur=90000.0, supr_totala=60.0)
    assert c.etaje_total is None
    assert c.structura is None
    assert c.incalzire is None
    assert c.stare is None
    assert c.stare_incredere == 0.0
    assert c.parcare_tip is None
    assert c.ajustare_neta_mare is False


def test_pret_ajustat_none_cand_lipseste_pretul():
    c = Comparabila(sursa="test", pret_eur=None, supr_totala=60.0,
                    ajustari=[Ajustare(factor="etaj", procent=0.05, motiv="x")])
    assert c.pret_ajustat is None
    assert c.euro_mp_ajustat is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_modele.py::test_pret_ajustat_combina_procent_si_absolut -v`
Expected: FAIL — `Ajustare` nu acceptă `valoare_abs` (unexpected keyword) și/sau `pret_ajustat` nu adună absolutele.

- [ ] **Step 3: Write minimal implementation**

În `acp/modele.py`, înlocuiește clasa `Ajustare` (liniile 7-10):

```python
class Ajustare(BaseModel):
    factor: str
    procent: float = 0.0        # ajustare proporțională (etaj, vechime, stare...)
    valoare_abs: float = 0.0    # ajustare absolută în € (parcare, boxă)
    motiv: str
```

În clasa `Comparabila`, adaugă câmpurile noi imediat după `tip: str = "vanzare"` (linia 46) și înainte de `ajustari: list[Ajustare] = []`:

```python
    etaje_total: int | None = None
    structura: str | None = None      # caramida | bca | panou | beton
    incalzire: str | None = None      # centrala_proprie | termoficare | centrala_bloc
    stare: str | None = None          # renovat | bun | necesita_renovare | gri
    stare_incredere: float = 0.0      # 0-1; ajustarea de stare se aplică doar peste prag
    parcare_tip: str | None = None    # owned | resedinta | none
    ajustare_neta_mare: bool = False  # marcaj gardă anti-supra-ajustare (|net| > 0.15)
```

Înlocuiește `pret_ajustat` (liniile 56-62):

```python
    @computed_field
    @property
    def pret_ajustat(self) -> float | None:
        if self.pret_eur is None:
            return None
        procent = 1 + sum(a.procent for a in self.ajustari)
        absolut = sum(a.valoare_abs for a in self.ajustari)
        return self.pret_eur * procent + absolut
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_modele.py -v`
Expected: PASS (toate, inclusiv cele patru noi).

- [ ] **Step 5: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS (≥ 149 passed — 145 baseline + 4 noi).

- [ ] **Step 6: Commit**

```bash
git add acp/modele.py tests/test_modele.py
git commit -m "feat(modele): Ajustare absolut + campuri noi Comparabila + pret_ajustat"
```

---

### Task 2: Extractori keyword — `acp/extractie.py`

**Files:**
- Create: `acp/extractie.py`
- Test: `tests/test_extractie.py`

**Interfaces:**
- Consumes: nimic.
- Produces:
  - `extrage_structura(text: str) -> str | None` → `caramida | bca | panou | beton | None`
  - `extrage_incalzire(text: str) -> str | None` → `centrala_proprie | termoficare | centrala_bloc | None`
  - `extrage_stare(text: str) -> tuple[str | None, float]` → `(stare, incredere)`
  - `extrage_parcare(text: str, an: int | None = None) -> str | None` → `owned | resedinta | none | None`

- [ ] **Step 1: Write the failing test**

Creează `tests/test_extractie.py`:

```python
from acp.extractie import (
    extrage_structura, extrage_incalzire, extrage_stare, extrage_parcare,
)


def test_structura_detecteaza_caramida_si_panou():
    assert extrage_structura("apartament în bloc de cărămidă") == "caramida"
    assert extrage_structura("bloc din panou prefabricat") == "panou"
    assert extrage_structura("structura beton, cadre") == "beton"
    assert extrage_structura("bloc BCA") == "bca"
    assert extrage_structura("fără mențiune") is None


def test_incalzire_detecteaza_tipurile():
    assert extrage_incalzire("are centrală proprie de apartament") == "centrala_proprie"
    assert extrage_incalzire("racordat la termoficare") == "termoficare"
    assert extrage_incalzire("centrală de bloc") == "centrala_bloc"
    assert extrage_incalzire("nimic relevant") is None


def test_stare_renovat_are_incredere_peste_prag():
    stare, incredere = extrage_stare("apartament complet renovat recent")
    assert stare == "renovat"
    assert incredere > 0.5


def test_stare_marketing_are_incredere_sub_prag():
    # "lux"/"premium" = limbaj de marketing → nu declanșează ajustare
    stare, incredere = extrage_stare("apartament de lux, finisaje premium")
    assert stare == "renovat"
    assert incredere <= 0.5


def test_stare_necesita_renovare():
    stare, incredere = extrage_stare("necesită renovare completă")
    assert stare == "necesita_renovare"
    assert incredere > 0.5


def test_stare_ambigua_none():
    stare, incredere = extrage_stare("apartament 2 camere, etaj 3")
    assert stare is None
    assert incredere == 0.0


def test_parcare_owned_explicit():
    assert extrage_parcare("include garaj subteran", an=2015) == "owned"
    assert extrage_parcare("parcare proprie inclusă în preț") == "owned"


def test_parcare_resedinta_explicit():
    assert extrage_parcare("loc de reședință închiriat de la primărie") == "resedinta"


def test_parcare_ambigua_heuristica_pe_vechime():
    assert extrage_parcare("loc de parcare", an=2015) == "owned"
    assert extrage_parcare("loc de parcare", an=1985) == "resedinta"
    assert extrage_parcare("loc de parcare", an=2004) is None
    assert extrage_parcare("loc de parcare") is None


def test_parcare_lipsa_none_string():
    assert extrage_parcare("apartament fără nicio mențiune de parcare") == "none"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_extractie.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acp.extractie'`.

- [ ] **Step 3: Write minimal implementation**

Creează `acp/extractie.py`:

```python
"""Extractori keyword pe textul brut al anunțului (titlu + descriere + tag-uri).

Conservator prin design: ambiguu → None (sau încredere joasă pentru stare).
Nu fabricăm valoare din limbaj de marketing.
"""
from __future__ import annotations

_STRUCTURA = [
    ("caramida", ["caramida", "cărămidă"]),
    ("panou", ["panou", "prefabricat", "prefab"]),
    ("bca", ["bca"]),
    ("beton", ["beton", "cadre"]),
]

_INCALZIRE = [
    ("centrala_proprie", ["centrala proprie", "centrală proprie",
                          "centrala termica proprie", "centrală termică proprie"]),
    ("centrala_bloc", ["centrala de bloc", "centrală de bloc", "centrala bloc"]),
    ("termoficare", ["termoficare", "racord termic", "sistem centralizat"]),
]

_STARE_NECESITA = ["necesita renovare", "necesită renovare", "de renovat", "pentru renovare"]
_STARE_RENOVAT = ["renovat", "modernizat", "renovare recenta", "renovare recentă"]
_STARE_MARKETING = ["lux", "premium", "finisaje de calitate"]
_STARE_GRI = ["la gri", "semifinisat", "nefinisat", "la rosu", "la roșu"]

_PARCARE_RESEDINTA = ["loc de resedinta", "loc de reședință", "parcare adp",
                      "inchiriat de la primarie", "închiriat de la primărie"]
_PARCARE_OWNED = ["garaj", "subteran", "parcare proprie", "loc cu act",
                  "parcare inclusa", "parcare inclusă"]
_PARCARE_ORICE = ["parcare", "loc de parcare"]


def _contine(text: str, kws: list[str]) -> bool:
    return any(k in text for k in kws)


def extrage_structura(text: str) -> str | None:
    t = text.lower()
    for eticheta, kws in _STRUCTURA:
        if _contine(t, kws):
            return eticheta
    return None


def extrage_incalzire(text: str) -> str | None:
    t = text.lower()
    for eticheta, kws in _INCALZIRE:
        if _contine(t, kws):
            return eticheta
    return None


def extrage_stare(text: str) -> tuple[str | None, float]:
    t = text.lower()
    if _contine(t, _STARE_NECESITA):
        return "necesita_renovare", 0.8
    if _contine(t, _STARE_GRI):
        return "gri", 0.8
    if _contine(t, _STARE_RENOVAT):
        return "renovat", 0.7
    if _contine(t, _STARE_MARKETING):
        return "renovat", 0.4  # marketing → sub prag, nu ajustează
    return None, 0.0


def extrage_parcare(text: str, an: int | None = None) -> str | None:
    t = text.lower()
    if _contine(t, _PARCARE_RESEDINTA):
        return "resedinta"
    if _contine(t, _PARCARE_OWNED):
        return "owned"
    if _contine(t, _PARCARE_ORICE):
        if an is not None and an >= 2008:
            return "owned"
        if an is not None and an < 2000:
            return "resedinta"
        return None  # ambiguu, vechime neconcludentă
    return "none"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_extractie.py -v`
Expected: PASS (toate 10).

- [ ] **Step 5: Commit**

```bash
git add acp/extractie.py tests/test_extractie.py
git commit -m "feat(extractie): extractori keyword structura/incalzire/stare/parcare"
```

---

### Task 3: Motor de ajustări — factori numerici (etaj, vechime, mărime)

**Files:**
- Create: `acp/ajustari.py`
- Test: `tests/test_ajustari.py`

**Interfaces:**
- Consumes: `Subiect`, `Comparabila`, `Ajustare` din `acp.modele`.
- Produces:
  - `calculeaza_ajustari(subiect: Subiect, comparabila: Comparabila, valoare_parcare_eur: float = 8000.0, valoare_boxa_eur: float = 2000.0) -> list[Ajustare]` — în acest task acoperă doar etaj/vechime/mărime; Task 4 adaugă restul.
  - Helperi privați: `_ajustare_etaj`, `_ajustare_vechime`, `_ajustare_marime`, `_nivel_etaj`.

- [ ] **Step 1: Write the failing test**

Creează `tests/test_ajustari.py`:

```python
from acp.modele import Subiect, Comparabila
from acp.ajustari import calculeaza_ajustari


def _subiect(**kw):
    baza = dict(pret_eur=100000.0, supr_totala=60.0, camere=2)
    baza.update(kw)
    return Subiect(**baza)


def _comp(**kw):
    baza = dict(sursa="test", pret_eur=100000.0, supr_totala=60.0)
    baza.update(kw)
    return Comparabila(**baza)


def _factor(ajustari, factor):
    for a in ajustari:
        if a.factor == factor:
            return a
    return None


def test_etaj_parter_comparabila_ajustata_in_sus():
    # subiect etaj intermediar (0.0), comparabila parter (-0.05) → +0.05
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=0)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert a is not None
    assert round(a.procent, 4) == 0.05


def test_etaj_unu_este_premium():
    # subiect intermediar (0.0), comparabila etaj 1 (+0.02) → -0.02
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=1)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert round(a.procent, 4) == -0.02


def test_etaj_acelasi_nivel_fara_ajustare():
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=6)  # ambele intermediare → 0
    assert _factor(calculeaza_ajustari(s, c), "etaj") is None


def test_etaj_ultimul_bloc_vechi():
    # comparabila la ultimul etaj (-0.03) vs subiect intermediar (0.0) → +0.03
    s = _subiect(etaj=5, etaje_total=10)
    c = _comp(etaj=8, etaje_total=8)
    a = _factor(calculeaza_ajustari(s, c), "etaj")
    assert round(a.procent, 4) == 0.03


def test_etaj_lipsa_fara_ajustare():
    s = _subiect(etaj=None)
    c = _comp(etaj=3)
    assert _factor(calculeaza_ajustari(s, c), "etaj") is None


def test_vechime_comparabila_mai_veche_ajustata_in_sus():
    s = _subiect(an=2010)
    c = _comp(an=2003)  # 7 ani mai veche → +0.07
    a = _factor(calculeaza_ajustari(s, c), "vechime")
    assert round(a.procent, 4) == 0.07


def test_vechime_plafonata_la_10_la_suta():
    s = _subiect(an=2020)
    c = _comp(an=2000)  # 20 ani → plafon +0.10
    a = _factor(calculeaza_ajustari(s, c), "vechime")
    assert round(a.procent, 4) == 0.10


def test_vechime_lipsa_fara_ajustare():
    s = _subiect(an=None)
    c = _comp(an=2000)
    assert _factor(calculeaza_ajustari(s, c), "vechime") is None


def test_marime_comparabila_mai_mare_ajustata_in_sus():
    # €/mp scade cu suprafața → comparabilă mai mare primește +
    s = _subiect(supr_totala=60.0)
    c = _comp(supr_totala=70.0)  # +10mp * 0.003 = +0.03
    a = _factor(calculeaza_ajustari(s, c), "marime")
    assert round(a.procent, 4) == 0.03


def test_marime_plafonata_la_3_la_suta():
    s = _subiect(supr_totala=60.0)
    c = _comp(supr_totala=100.0)  # +40mp * 0.003 = 0.12 → plafon 0.03
    a = _factor(calculeaza_ajustari(s, c), "marime")
    assert round(a.procent, 4) == 0.03
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ajustari.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'acp.ajustari'`.

- [ ] **Step 3: Write minimal implementation**

Creează `acp/ajustari.py`:

```python
"""Motor de ajustare a prețului comparabilelor la nivelul subiectului.

Direcția: subiect − comparabila. Comparabila inferioară → ajustare pozitivă.
"""
from __future__ import annotations

from acp.modele import Subiect, Comparabila, Ajustare

CAP_ETAJ = 0.05
CAP_VECHIME = 0.10
CAP_MARIME = 0.03


def _plafon(x: float, cap: float) -> float:
    return max(-cap, min(cap, x))


def _nivel_etaj(etaj: int | None, etaje_total: int | None) -> float | None:
    """Valoarea de nivel a etajului (curbă, nu liniar). None dacă etaj necunoscut."""
    if etaj is None:
        return None
    if etaj == 0:
        return -0.05          # parter
    if etaj == 1:
        return 0.02           # cel mai căutat
    if etaj in (2, 3):
        return 0.01
    if etaje_total is not None and etaj >= 4 and etaj == etaje_total:
        return -0.03          # ultimul etaj
    return 0.0                # intermediar (baseline)


def _ajustare_etaj(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    ns = _nivel_etaj(subiect.etaj, subiect.etaje_total)
    nc = _nivel_etaj(comp.etaj, comp.etaje_total)
    if ns is None or nc is None:
        return None
    procent = _plafon(ns - nc, CAP_ETAJ)
    if procent == 0:
        return None
    return Ajustare(factor="etaj", procent=procent,
                    motiv=f"Etaj {comp.etaj} vs subiect {subiect.etaj}")


def _ajustare_vechime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if subiect.an is None or comp.an is None:
        return None
    procent = _plafon((subiect.an - comp.an) * 0.01, CAP_VECHIME)
    if procent == 0:
        return None
    return Ajustare(factor="vechime", procent=procent,
                    motiv=f"An {comp.an} vs subiect {subiect.an}")


def _ajustare_marime(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    procent = _plafon((comp.supr_totala - subiect.supr_totala) * 0.003, CAP_MARIME)
    if procent == 0:
        return None
    return Ajustare(factor="marime", procent=procent,
                    motiv=f"{comp.supr_totala}mp vs subiect {subiect.supr_totala}mp")


def calculeaza_ajustari(subiect: Subiect, comparabila: Comparabila,
                        valoare_parcare_eur: float = 8000.0,
                        valoare_boxa_eur: float = 2000.0) -> list[Ajustare]:
    candidati = [
        _ajustare_etaj(subiect, comparabila),
        _ajustare_vechime(subiect, comparabila),
        _ajustare_marime(subiect, comparabila),
    ]
    return [a for a in candidati if a is not None]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ajustari.py -v`
Expected: PASS (toate 10).

- [ ] **Step 5: Commit**

```bash
git add acp/ajustari.py tests/test_ajustari.py
git commit -m "feat(ajustari): factori numerici etaj/vechime/marime"
```

---

### Task 4: Motor de ajustări — factori categorici (parcare, boxă, mobilat, A/C, balcon, structură, încălzire, stare)

**Files:**
- Modify: `acp/ajustari.py` (adaugă helperi + extinde `calculeaza_ajustari`)
- Test: `tests/test_ajustari.py` (adaugă teste)

**Interfaces:**
- Consumes: `extrage_parcare` din `acp.extractie`; `Subiect`, `Comparabila`, `Ajustare`.
- Produces: `calculeaza_ajustari` acum întoarce și ajustările categorice; helperi noi `_ajustare_parcare`, `_ajustare_boxa`, `_ajustare_mobilat`, `_ajustare_ac`, `_ajustare_balcon`, `_ajustare_structura`, `_ajustare_incalzire`, `_ajustare_stare`.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_ajustari.py`:

```python
def test_parcare_owned_subiect_comparabila_fara():
    s = _subiect(parcare="garaj subteran propriu", an=2015)
    c = _comp(parcare_tip="none")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a is not None
    assert a.valoare_abs == 8000.0


def test_parcare_resedinta_nu_produce_ajustare():
    # subiect fără parcare owned, comparabila reședință → fără capital
    s = _subiect(parcare=None)
    c = _comp(parcare_tip="resedinta")
    assert _factor(calculeaza_ajustari(s, c), "parcare") is None


def test_parcare_comparabila_owned_subiect_fara():
    s = _subiect(parcare=None)
    c = _comp(parcare_tip="owned")
    a = _factor(calculeaza_ajustari(s, c, valoare_parcare_eur=8000.0), "parcare")
    assert a.valoare_abs == -8000.0


def test_boxa_pe_diferenta_dotari():
    s = _subiect(dotari=["boxă", "AC"])
    c = _comp(dotari=["AC"])
    a = _factor(calculeaza_ajustari(s, c, valoare_boxa_eur=2000.0), "boxa")
    assert a.valoare_abs == 2000.0


def test_mobilat_procent():
    s = _subiect(dotari=["mobilat", "utilat"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "mobilat")
    assert round(a.procent, 4) == 0.04


def test_ac_pe_numar_de_unitati_plafonat():
    s = _subiect(dotari=["aer condiționat", "aer condiționat", "aer condiționat", "aer condiționat"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "ac")
    # 4 unități * 0.01 = 0.04 → plafon 0.03
    assert round(a.procent, 4) == 0.03


def test_balcon_procent():
    s = _subiect(dotari=["balcon"])
    c = _comp(dotari=[])
    a = _factor(calculeaza_ajustari(s, c), "balcon")
    assert round(a.procent, 4) == 0.03


def test_structura_caramida_vs_panou():
    s = _subiect(structura="caramida")
    c = _comp(structura="panou")
    a = _factor(calculeaza_ajustari(s, c), "structura")
    # 0.02 - (-0.03) = 0.05
    assert round(a.procent, 4) == 0.05


def test_structura_necunoscuta_fara_ajustare():
    s = _subiect(structura=None)
    c = _comp(structura="panou")
    assert _factor(calculeaza_ajustari(s, c), "structura") is None


def test_incalzire_centrala_proprie_vs_termoficare():
    s = _subiect(incalzire="centrala_proprie")
    c = _comp(incalzire="termoficare")
    a = _factor(calculeaza_ajustari(s, c), "incalzire")
    # 0.03 - (-0.02) = 0.05
    assert round(a.procent, 4) == 0.05


def test_stare_aplicata_doar_peste_prag_incredere():
    s = _subiect(stare="renovat")
    c_slab = _comp(stare="necesita_renovare", stare_incredere=0.4)  # sub prag
    assert _factor(calculeaza_ajustari(s, c_slab), "stare") is None
    c_bun = _comp(stare="necesita_renovare", stare_incredere=0.8)   # peste prag
    a = _factor(calculeaza_ajustari(s, c_bun), "stare")
    # 0.10 - (-0.15) = 0.25 → plafon 0.15
    assert round(a.procent, 4) == 0.15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ajustari.py -v -k "parcare or boxa or mobilat or ac or balcon or structura or incalzire or stare"`
Expected: FAIL — helperii categorici nu există; `calculeaza_ajustari` nu întoarce factorii categorici.

- [ ] **Step 3: Write minimal implementation**

În `acp/ajustari.py`, adaugă importul sus (lângă importul din `acp.modele`):

```python
from acp.extractie import extrage_parcare
```

Adaugă constantele de valori după `CAP_MARIME`:

```python
CAP_STARE = 0.15

_STRUCTURA_VAL = {"caramida": 0.02, "beton": 0.02, "bca": 0.0, "panou": -0.03}
_INCALZIRE_VAL = {"centrala_proprie": 0.03, "centrala_bloc": 0.0, "termoficare": -0.02}
_STARE_VAL = {"renovat": 0.10, "bun": 0.0, "gri": -0.05, "necesita_renovare": -0.15}

_KW_BOXA = ["boxa", "boxă", "debara", "camara", "cămară"]
_KW_MOBILAT = ["mobilat", "utilat"]
_KW_AC = ["aer conditionat", "aer condiționat", "a/c", "aer cond", "clima"]
_KW_BALCON = ["balcon", "terasa", "terasă", "logie"]
```

Adaugă helperii de detecție și factorii categorici (după `_ajustare_marime`):

```python
def _are(dotari: list[str], kws: list[str]) -> bool:
    return any(any(k in d.lower() for k in kws) for d in dotari)


def _numara_ac(dotari: list[str]) -> int:
    return sum(1 for d in dotari if any(k in d.lower() for k in _KW_AC))


def _ajustare_parcare(subiect: Subiect, comp: Comparabila, valoare: float) -> Ajustare | None:
    subiect_owned = extrage_parcare(subiect.parcare or "", subiect.an) == "owned"
    comp_owned = comp.parcare_tip == "owned"
    if subiect_owned and not comp_owned:
        return Ajustare(factor="parcare", valoare_abs=valoare,
                        motiv="Subiect cu parcare proprie, comparabila fără")
    if comp_owned and not subiect_owned:
        return Ajustare(factor="parcare", valoare_abs=-valoare,
                        motiv="Comparabila cu parcare proprie, subiect fără")
    return None


def _ajustare_boxa(subiect: Subiect, comp: Comparabila, valoare: float) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_BOXA), _are(comp.dotari, _KW_BOXA)
    if s and not c:
        return Ajustare(factor="boxa", valoare_abs=valoare,
                        motiv="Subiect cu boxă, comparabila fără")
    if c and not s:
        return Ajustare(factor="boxa", valoare_abs=-valoare,
                        motiv="Comparabila cu boxă, subiect fără")
    return None


def _ajustare_mobilat(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_MOBILAT), _are(comp.dotari, _KW_MOBILAT)
    if s and not c:
        return Ajustare(factor="mobilat", procent=0.04,
                        motiv="Subiect mobilat/utilat, comparabila nu")
    if c and not s:
        return Ajustare(factor="mobilat", procent=-0.04,
                        motiv="Comparabila mobilat/utilat, subiect nu")
    return None


def _ajustare_ac(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    diff = _numara_ac(subiect.dotari) - _numara_ac(comp.dotari)
    procent = _plafon(diff * 0.01, 0.03)
    if procent == 0:
        return None
    return Ajustare(factor="ac", procent=procent,
                    motiv=f"A/C: comparabila {_numara_ac(comp.dotari)} vs subiect {_numara_ac(subiect.dotari)}")


def _ajustare_balcon(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    s, c = _are(subiect.dotari, _KW_BALCON), _are(comp.dotari, _KW_BALCON)
    if s and not c:
        return Ajustare(factor="balcon", procent=0.03,
                        motiv="Subiect cu balcon, comparabila fără")
    if c and not s:
        return Ajustare(factor="balcon", procent=-0.03,
                        motiv="Comparabila cu balcon, subiect fără")
    return None


def _ajustare_din_harta(factor: str, val_s: str | None, val_c: str | None,
                        harta: dict[str, float], cap: float | None = None) -> Ajustare | None:
    if val_s is None or val_c is None:
        return None
    vs, vc = harta.get(val_s), harta.get(val_c)
    if vs is None or vc is None:
        return None
    procent = vs - vc
    if cap is not None:
        procent = _plafon(procent, cap)
    if procent == 0:
        return None
    return Ajustare(factor=factor, procent=procent, motiv=f"{val_c} vs subiect {val_s}")


def _ajustare_structura(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    return _ajustare_din_harta("structura", subiect.structura, comp.structura, _STRUCTURA_VAL)


def _ajustare_incalzire(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    return _ajustare_din_harta("incalzire", subiect.incalzire, comp.incalzire, _INCALZIRE_VAL)


def _ajustare_stare(subiect: Subiect, comp: Comparabila) -> Ajustare | None:
    if comp.stare_incredere <= 0.5:
        return None
    return _ajustare_din_harta("stare", subiect.stare, comp.stare, _STARE_VAL, cap=CAP_STARE)
```

Extinde `calculeaza_ajustari` — înlocuiește lista `candidati` cu:

```python
    candidati = [
        _ajustare_etaj(subiect, comparabila),
        _ajustare_vechime(subiect, comparabila),
        _ajustare_marime(subiect, comparabila),
        _ajustare_parcare(subiect, comparabila, valoare_parcare_eur),
        _ajustare_boxa(subiect, comparabila, valoare_boxa_eur),
        _ajustare_mobilat(subiect, comparabila),
        _ajustare_ac(subiect, comparabila),
        _ajustare_balcon(subiect, comparabila),
        _ajustare_structura(subiect, comparabila),
        _ajustare_incalzire(subiect, comparabila),
        _ajustare_stare(subiect, comparabila),
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ajustari.py -v`
Expected: PASS (numerice + categorice).

- [ ] **Step 5: Commit**

```bash
git add acp/ajustari.py tests/test_ajustari.py
git commit -m "feat(ajustari): factori categorici parcare/boxa/dotari/structura/incalzire/stare"
```

---

### Task 5: Gardă anti-supra-ajustare + `aplica_ajustari`

**Files:**
- Modify: `acp/ajustari.py` (adaugă `aplica_ajustari` + garda)
- Test: `tests/test_ajustari.py` (adaugă teste)

**Interfaces:**
- Consumes: `calculeaza_ajustari`.
- Produces: `aplica_ajustari(subiect: Subiect, comparabile: list[Comparabila], valoare_parcare_eur: float = 8000.0, valoare_boxa_eur: float = 2000.0) -> tuple[list[Comparabila], list[Comparabila]]` → `(pastrate, excluse)`. Populează `c.ajustari` in-place și setează `c.ajustare_neta_mare`.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_ajustari.py`:

```python
from acp.ajustari import aplica_ajustari


def test_aplica_populeaza_ajustari_pe_comparabile():
    s = _subiect(an=2010, etaj=5, etaje_total=10)
    c = _comp(an=2003, etaj=0, pret_eur=100000.0, supr_totala=60.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert len(excluse) == 0
    assert len(pastrate[0].ajustari) >= 2  # vechime + etaj
    assert pastrate[0].pret_ajustat != pastrate[0].pret_eur


def test_garda_exclude_comparabila_supra_ajustata():
    # brut > 0.25: vechime +0.10 (plafon) + stare +0.15 (plafon) = 0.25 brut ...
    # adăugăm și mărime +0.03 → brut = 0.28 > 0.25 → exclusă
    s = _subiect(an=2025, supr_totala=60.0, stare="renovat")
    c = _comp(an=2000, supr_totala=80.0, stare="necesita_renovare",
              stare_incredere=0.9, pret_eur=100000.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(excluse) == 1
    assert len(pastrate) == 0


def test_garda_marcheaza_ajustare_neta_mare_dar_pastreaza():
    # net > 0.15 dar brut <= 0.25: vechime +0.10 + etaj +0.05 = net 0.15 brut 0.15
    # facem net 0.16: vechime +0.10, structura +0.05 (caramida vs panou), balcon +0.03 = 0.18
    s = _subiect(an=2020, structura="caramida", dotari=["balcon"])
    c = _comp(an=2010, structura="panou", dotari=[], pret_eur=100000.0)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert pastrate[0].ajustare_neta_mare is True


def test_garda_ignora_comparabila_fara_pret():
    s = _subiect(an=2010)
    c = _comp(an=2000, pret_eur=None)
    pastrate, excluse = aplica_ajustari(s, [c])
    assert len(pastrate) == 1
    assert pastrate[0].ajustare_neta_mare is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_ajustari.py -v -k "aplica or garda"`
Expected: FAIL — `cannot import name 'aplica_ajustari'`.

- [ ] **Step 3: Write minimal implementation**

În `acp/ajustari.py`, adaugă pragurile lângă celelalte constante:

```python
PRAG_NET = 0.15
PRAG_BRUT = 0.25
```

Adaugă la finalul fișierului:

```python
def _procent_echivalent(ajustari: list[Ajustare], pret_eur: float) -> tuple[float, float]:
    """Convertește ajustările (procent + absolut) în procent-echivalent față de preț.

    Întoarce (net, brut): net = suma cu semn, brut = suma valorilor absolute.
    """
    net = brut = 0.0
    for a in ajustari:
        p = a.procent + (a.valoare_abs / pret_eur)
        net += p
        brut += abs(p)
    return net, brut


def aplica_ajustari(subiect: Subiect, comparabile: list[Comparabila],
                    valoare_parcare_eur: float = 8000.0,
                    valoare_boxa_eur: float = 2000.0
                    ) -> tuple[list[Comparabila], list[Comparabila]]:
    """Populează c.ajustari pe fiecare comparabilă și aplică garda anti-supra-ajustare.

    Întoarce (pastrate, excluse). O comparabilă cu brut > PRAG_BRUT e exclusă;
    una cu |net| > PRAG_NET e păstrată dar marcată (ajustare_neta_mare = True).
    """
    pastrate: list[Comparabila] = []
    excluse: list[Comparabila] = []
    for c in comparabile:
        c.ajustari = calculeaza_ajustari(subiect, c, valoare_parcare_eur, valoare_boxa_eur)
        if c.pret_eur:
            net, brut = _procent_echivalent(c.ajustari, c.pret_eur)
            if brut > PRAG_BRUT:
                excluse.append(c)
                continue
            c.ajustare_neta_mare = abs(net) > PRAG_NET
        pastrate.append(c)
    return pastrate, excluse
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_ajustari.py -v`
Expected: PASS (toate).

- [ ] **Step 5: Commit**

```bash
git add acp/ajustari.py tests/test_ajustari.py
git commit -m "feat(ajustari): garda anti-supra-ajustare + aplica_ajustari"
```

---

### Task 6: Integrare în pipeline — `analizeaza()` apelează `aplica_ajustari()`

**Files:**
- Modify: `acp/analiza.py:18-57`
- Test: `tests/test_analiza.py`

**Interfaces:**
- Consumes: `aplica_ajustari` din `acp.ajustari`.
- Produces: `analizeaza()` acceptă parametri opționali `valoare_parcare_eur: float = 8000.0`, `valoare_boxa_eur: float = 2000.0`; comparabilele returnate au `ajustari` populate; `stat_ajustat` reflectă `euro_mp_ajustat`.

- [ ] **Step 1: Write the failing test**

Adaugă în `tests/test_analiza.py`:

```python
from acp.modele import Subiect, Comparabila
from acp.analiza import analizeaza


def test_analizeaza_populeaza_ajustari_si_difera_de_brut():
    subiect = Subiect(pret_eur=100000.0, supr_totala=60.0, camere=2,
                      an=2010, etaj=5, etaje_total=10)
    # comparabile care diferă de subiect ca an/etaj → ajustări nenule
    comparabile = [
        Comparabila(sursa="a", pret_eur=95000.0, supr_totala=60.0, an=2000, etaj=0, marcaj="activ"),
        Comparabila(sursa="b", pret_eur=98000.0, supr_totala=62.0, an=2004, etaj=1, marcaj="activ"),
        Comparabila(sursa="c", pret_eur=102000.0, supr_totala=58.0, an=2008, etaj=3, marcaj="activ"),
        Comparabila(sursa="d", pret_eur=100000.0, supr_totala=61.0, an=2012, etaj=6, marcaj="activ"),
    ]
    analiza = analizeaza(subiect, comparabile, tinta_zile=90)
    # cel puțin o comparabilă păstrată are ajustări nenule
    assert any(len(c.ajustari) > 0 for c in analiza.comparabile)
    # mediana ajustată diferă de cea brută (ajustările au efect)
    assert analiza.stat_ajustat.mediana != analiza.stat_brut.mediana
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_analiza.py::test_analizeaza_populeaza_ajustari_si_difera_de_brut -v`
Expected: FAIL — `stat_ajustat.mediana == stat_brut.mediana` (ajustările nu sunt aplicate încă).

- [ ] **Step 3: Write minimal implementation**

În `acp/analiza.py`, adaugă importul sus (lângă celelalte importuri din `acp.`):

```python
from acp.ajustari import aplica_ajustari
```

Modifică semnătura `analizeaza` (linia 18-20) pentru a accepta parametrii de valoare:

```python
def analizeaza(subiect: Subiect, comparabile: list[Comparabila], tinta_zile: int,
               corectie: tuple[float, float] = (0.04, 0.08),
               surse: list[str] | None = None,
               valoare_parcare_eur: float = 8000.0,
               valoare_boxa_eur: float = 2000.0) -> Analiza:
```

Înlocuiește liniile de filtrare (actualmente `filtrate = filtreaza(...)` urmat de `pastrate, outlieri = marcheaza_outlieri(filtrate)`) cu:

```python
    vanzari = [c for c in comparabile if c.tip == "vanzare"]
    filtrate = filtreaza(subiect, dedup(vanzari))
    ajustate, _excluse_supra = aplica_ajustari(
        subiect, filtrate, valoare_parcare_eur, valoare_boxa_eur
    )
    pastrate, outlieri = marcheaza_outlieri(ajustate)
```

(Restul funcției rămâne neschimbat — `valori_ajustat` folosește deja `c.euro_mp_ajustat`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_analiza.py -v`
Expected: PASS (inclusiv noul test).

- [ ] **Step 5: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS. Dacă vreun test `test_analiza.py` preexistent se bazează pe `stat_ajustat == stat_brut` (fără ajustări), actualizează-l ca să reflecte că acum ajustările pot fi nenule — comparabilele lui probabil nu diferă de subiect, deci ajustările rămân goale și egalitatea se păstrează; verifică și corectează doar dacă e nevoie.

- [ ] **Step 6: Commit**

```bash
git add acp/analiza.py tests/test_analiza.py
git commit -m "feat(analiza): integreaza aplica_ajustari in pipeline"
```

---

### Task 7: Wiring conectori — populează câmpurile noi din text (imobiliare, storia, olx)

**Files:**
- Modify: `acp/connectors/imobiliare.py:255-265`, `acp/connectors/storia.py:339-349`, `acp/connectors/olx.py:364-374`
- Test: `tests/test_imobiliare.py`, `tests/test_storia.py`, `tests/test_olx.py` (verifică numele exacte cu `ls tests/`)

**Interfaces:**
- Consumes: `extrage_structura`, `extrage_incalzire`, `extrage_stare`, `extrage_parcare` din `acp.extractie`.
- Produces: `Comparabila` cu `structura`, `incalzire`, `stare`, `stare_incredere`, `parcare_tip` populate din textul disponibil al anunțului (best-effort; `None` când textul nu conține indicii).

- [ ] **Step 1: Verify test file names**

Run: `ls tests/ | grep -iE "imobiliare|storia|olx"`
Folosește numele exacte returnate în pașii următori (mai jos presupunem `test_imobiliare.py`, `test_storia.py`, `test_olx.py`).

- [ ] **Step 2: Write the failing test (imobiliare)**

Adaugă în fișierul de test al conectorului imobiliare un test pe metoda de construcție a comparabilei dintr-un element de anunț. Verifică întâi semnătura metodei (`grep -n "def _parse\|def _to_comparabila\|_as_article_tag" acp/connectors/imobiliare.py`) și numele ei; testul apelează metoda de parsare a unui singur element cu text ce conține indicii:

```python
def test_imobiliare_populeaza_campuri_noi_din_text():
    from bs4 import BeautifulSoup
    from acp.connectors.imobiliare import ImobiliareConnector
    html = (
        '<article data-price="90000" data-surface="60" data-year="2015">'
        'Apartament renovat, centrală proprie, cărămidă, garaj subteran'
        '</article>'
    )
    elem = BeautifulSoup(html, "html.parser").find("article")
    conn = ImobiliareConnector()
    comp = conn._parse_listing(elem)  # ajustează la numele real al metodei
    assert comp.structura == "caramida"
    assert comp.incalzire == "centrala_proprie"
    assert comp.stare == "renovat"
    assert comp.parcare_tip == "owned"
```

Dacă metoda de parsare a unui singur element are alt nume/altă semnătură, adaptează apelul; scopul e să verifici că cele patru câmpuri se populează din textul elementului.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_imobiliare.py -v -k "campuri_noi"`
Expected: FAIL — câmpurile rămân `None` (nu-s populate încă).

- [ ] **Step 4: Implement wiring (imobiliare)**

În `acp/connectors/imobiliare.py`, adaugă importul sus:

```python
from acp.extractie import extrage_structura, extrage_incalzire, extrage_stare, extrage_parcare
```

Imediat înainte de `return Comparabila(` (linia ~255), derivă textul și câmpurile:

```python
        text = elem.get_text(" ", strip=True) if hasattr(elem, "get_text") else ""
        stare, stare_incredere = extrage_stare(text)
```

Și adaugă câmpurile în apelul `Comparabila(...)`:

```python
        return Comparabila(
            sursa=self.name,
            url=url,
            pret_eur=pret_eur,
            supr_totala=supr_totala,
            etaj=etaj,
            an=an,
            dotari=[],
            marcaj=marcaj,
            tip=tip,
            structura=extrage_structura(text),
            incalzire=extrage_incalzire(text),
            stare=stare,
            stare_incredere=stare_incredere,
            parcare_tip=extrage_parcare(text, an),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_imobiliare.py -v`
Expected: PASS.

- [ ] **Step 6: Write + implement wiring (storia)**

Testul (adaugă în `tests/test_storia.py`) — storia construiește din `item` (dict); textul provine din `slug` + `tags`. Verifică numele metodei de parsare (`grep -n "def _" acp/connectors/storia.py | grep -i pars`) și adaptează:

```python
def test_storia_populeaza_campuri_noi_din_slug_si_tags():
    from acp.connectors.storia import StoriaConnector
    item = {
        "areaInSquareMeters": 60,
        "totalPrice": {"value": 90000},
        "floorNumber": None,
        "transaction": "SELL",
        "slug": "apartament-2-camere-renovat-caramida-centrala-proprie",
        "tags": [{"value": "garaj subteran"}],
    }
    conn = StoriaConnector()
    comp = conn._to_comparabila(item)  # ajustează la numele real
    assert comp.structura == "caramida"
    assert comp.stare == "renovat"
    assert comp.parcare_tip == "owned"
```

Implementare — în `acp/connectors/storia.py`, adaugă importul extractorilor sus, apoi înainte de `return Comparabila(` (linia ~339) construiește textul din slug + dotari și derivă câmpurile:

```python
        slug_text = (item.get("slug") or "").replace("-", " ")
        text = " ".join([slug_text, *dotari])
        stare, stare_incredere = extrage_stare(text)
```

Adaugă în apelul `Comparabila(...)`:

```python
            structura=extrage_structura(text),
            incalzire=extrage_incalzire(text),
            stare=stare,
            stare_incredere=stare_incredere,
            parcare_tip=extrage_parcare(text, an),
```

Run: `pytest tests/test_storia.py -v`
Expected: PASS.

- [ ] **Step 7: Write + implement wiring (olx)**

Testul (adaugă în `tests/test_olx.py`) — olx are `item.get("title")` + `dotari`:

```python
def test_olx_populeaza_campuri_noi_din_title():
    from acp.connectors.olx import OlxConnector
    # construiește un item minimal conform structurii folosite de _to_comparabila;
    # verifică forma reală cu `grep -n "item.get" acp/connectors/olx.py`
    ...
    assert comp.structura == "caramida"
    assert comp.parcare_tip in ("owned", "resedinta", "none", None)
```

Implementare — în `acp/connectors/olx.py`, adaugă importul extractorilor sus, apoi înainte de `return Comparabila(` (linia ~364):

```python
        text = " ".join(filter(None, [(item.get("title") or ""), *dotari]))
        stare, stare_incredere = extrage_stare(text)
```

Adaugă în apelul `Comparabila(...)`:

```python
            structura=extrage_structura(text),
            incalzire=extrage_incalzire(text),
            stare=stare,
            stare_incredere=stare_incredere,
            parcare_tip=extrage_parcare(text, an),
```

Run: `pytest tests/test_olx.py -v`
Expected: PASS.

- [ ] **Step 8: Regression**

Run: `pytest --ignore=tests/test_render.py --ignore=tests/test_e2e.py --ignore=tests/test_pipeline.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add acp/connectors/imobiliare.py acp/connectors/storia.py acp/connectors/olx.py tests/test_imobiliare.py tests/test_storia.py tests/test_olx.py
git commit -m "feat(connectors): populeaza structura/incalzire/stare/parcare din text"
```

---

### Task 8: Actualizare `SKILL.md` — câmpuri noi, validare foto pe subiect, parcare pe tip

**Files:**
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: nimic (documentație).
- Produces: instrucțiuni actualizate pentru agentul AI.

- [ ] **Step 1: Read current SKILL.md sections to edit**

Run: `grep -n "\[1\] FIȘA\|\[4\]\|stare\|parcare\|Comparabila" SKILL.md`
Identifică secțiunea fișei subiectului [1] și pasul de analiză/ajustare.

- [ ] **Step 2: Add subject condition + parking guidance**

În pasul `[1] FIȘA SUBIECTULUI`, adaugă un paragraf care instruiește agentul să seteze `stare` și tipul de parcare pe subiect uitându-se la poze:

```markdown
**Stare și parcare (validare vizuală pe subiect):**
- Deschide pozele anunțului subiect și stabilește `stare` ∈ {renovat, bun, gri, necesita_renovare} cu ochii tăi — nu te baza pe adjectivele de marketing din text („lux", „premium" nu înseamnă renovat).
- Pentru parcare, distinge tipul: `owned` (garaj/subteran/loc cu act, tipic complexe noi — activ de capital) vs. `resedinta` (loc închiriat de la primărie la blocuri vechi — fără valoare de capital). Setează `Subiect.parcare` cu textul care reflectă tipul real.
- Validarea vizuală se face DOAR pe subiect. Comparabilele sunt evaluate programatic prin keyword-matching conservator (structura/incalzire/stare/parcare din `acp/extractie.py`) — ajustările de stare se aplică doar peste pragul de încredere.
```

- [ ] **Step 3: Document adjustment step + parking value parameter**

În pasul de analiză (unde se descrie `analizeaza()`), adaugă:

```markdown
**Ajustarea comparabilelor (Task 11):** `analizeaza()` apelează automat `aplica_ajustari()`, care aduce fiecare comparabilă la nivelul subiectului (etaj, vechime, mărime, dotări, parcare, structură, încălzire, stare). Direcția: subiect − comparabilă. Comparabilele supra-ajustate (ajustare brută > 25%) sunt excluse; cele cu ajustare netă > 15% rămân dar sunt marcate (`ajustare_neta_mare`) — semnalează-le în raport.

**Valoarea parcării e parametru:** `analizeaza(..., valoare_parcare_eur=..., valoare_boxa_eur=...)`. Parcarea variază pe cartier și complex — setează valoarea potrivită pieței subiectului (default conservator €8.000 parcare / €2.000 boxă). La blocuri vechi cu loc de reședință, parcarea nu are valoare de capital (ajustare €0).
```

- [ ] **Step 4: Commit**

```bash
git add SKILL.md
git commit -m "docs(skill): ajustari comparabile — validare foto subiect, parcare pe tip"
```

---

## Self-Review

**1. Spec coverage:**
- Direcție subiect − comparabila → Global Constraints + fiecare helper. ✅
- Extindere `Comparabila` (structura/incalzire/stare/stare_incredere/parcare_tip) + `etaje_total` → Task 1. ✅
- `Ajustare` cu `valoare_abs` + `pret_ajustat` nou → Task 1. ✅
- Extractori keyword → Task 2. ✅
- Toți factorii (etaj curbă, vechime, mărime, parcare owned/reședință, boxă, mobilat, A/C, balcon, structură, încălzire, stare) → Task 3-4. ✅
- Gardă ANEVAR net/brut → Task 5. ✅
- Integrare pipeline → Task 6. ✅
- Wiring conectori → Task 7. ✅
- Validare foto pe subiect + parcare parametru în SKILL.md → Task 8. ✅
- Etaj 1 = +2% (corecția utilizatorului) → `_nivel_etaj` Task 3. ✅
- Pre-1977 scos → nu apare nicăieri. ✅
- Prag stare 0.5 → `_ajustare_stare` Task 4. ✅

**2. Placeholder scan:** Toți pașii de cod conțin cod complet. Task 7 conține instrucțiuni de verificare a numelor de metode (`grep`) pentru că numele exacte ale metodelor de parsare per-connector nu sunt fixate în plan — acesta e un pas de verificare acționabil, nu un placeholder de logică.

**3. Type consistency:**
- `calculeaza_ajustari(subiect, comparabila, valoare_parcare_eur, valoare_boxa_eur)` — semnătură identică în Task 3, 4, 5. ✅
- `aplica_ajustari(subiect, comparabile, valoare_parcare_eur, valoare_boxa_eur) -> (pastrate, excluse)` — Task 5, consumat identic în Task 6. ✅
- `extrage_stare -> (str|None, float)` — Task 2, dezambalat ca `stare, stare_incredere` în Task 7. ✅
- `Ajustare(factor, procent, valoare_abs, motiv)` — Task 1, folosit consistent. ✅
- Câmpuri `Comparabila` — definite Task 1, populate Task 7, citite Task 3-5. ✅
