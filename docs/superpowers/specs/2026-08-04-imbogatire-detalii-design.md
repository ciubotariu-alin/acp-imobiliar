# Îmbogățire cu Detalii (Task 12) — Design

**Goal:** Deblochează ajustările de dotări (mobilat/A/C/balcon/boxă) prin extragerea datelor REALE ale comparabilelor din paginile lor de detaliu, astfel încât `euro_mp_ajustat` să reflecte o comparație corectă — nu un bias sistematic în care subiectul primește credit de dotări față de comparabile a căror dotare e de fapt necunoscută.

**Context:** Cardurile de căutare nu expun dotările comparabilelor. Factorii de dotări din `acp/ajustari.py` tratează `dotari` gol ca „comparabila nu are dotarea", producând un bias de +8% pe aproape fiecare comparabilă (dovedit live: verdictul se răstoarnă din CORECT în SUPRAEVALUAT). Fix-ul de fond: deschidem pagina de detaliu a fiecărei comparabile relevante și extragem dotările reale.

## Principiul de corectitudine (miezul)

Ajustarea de dotări se aplică **doar când chiar avem datele comparabilei**. Introducem un flag `detalii_complete: bool` pe `Comparabila`, setat `True` numai după un fetch + parse reușit al paginii de detaliu. Factorii de dotări returnează `None` când `detalii_complete=False` → necunoscut = nicio ajustare (simetric cu structură/încălzire/stare, care au deja gardă „ambele cunoscute"). Asta elimină biasul ȘI tratează uniform fetch-urile eșuate.

## Decizii de scop (din brainstorming)

- **Care comparabile:** doar cele **post-filtrare** (dedup + `filtreaza`: ±20% suprafață, cameră, zonă) — tipic ~20-30, nu ~54.
- **Care portaluri:** **toate trei** cu parsing real (imobiliare, storia, olx).
- **Latență:** **secvențial + cache** — prima rulare ~2 min, reluările pe aceleași anunțuri aproape instant.

## Arhitectură & flux

```
PipelineOrchestrator:
  fetch search (conectori)  →  dedup + filtreaza (±20% supr, cameră, zonă)
        →  [NOU] imbogateste_detalii(survivors, fetchers, cache)   ← secvențial + cache
        →  analizeaza(subiect, comps)   ← re-filtrează idempotent, ajustează pe date reale
```

Îmbogățirea stă în **orchestrator** (el deține rețeaua/conectorii). Se aplică pe **setul supraviețuitor** al filtrării. `analizeaza` rămâne **pură** (fără I/O): re-rularea `dedup`+`filtreaza` e idempotentă, iar obiectele `Comparabila` îmbogățite (aceleași referințe) curg natural prin ea.

## Componente

### 1. `acp/modele.py` — flag nou

`Comparabila` primește:
```python
detalii_complete: bool = False   # True doar după fetch+parse reușit al paginii de detaliu
```

### 2. `acp/extractie.py` — extractori noi

Detail-page-ul are text bogat (descriere + specificații structurate), deci extractorii existenți (`extrage_structura/incalzire/stare/parcare`) funcționează mult mai bine pe el decât pe carduri. Adăugăm:

- `extrage_dotari(text: str) -> list[str]` — detectează mobilat/utilat, aer condiționat, balcon/terasă, boxă/debara și le întoarce ca listă de etichete normalizate (aceleași cuvinte-cheie folosite de `_KW_*` din `acp/ajustari.py`, centralizate aici pentru DRY).
- `extrage_etaje_total(text: str) -> int | None` — parsează „Regim înălțime: P+8E" / „P+NE" → N (util pentru ajustarea de ultim etaj).

### 3. `acp/detalii.py` (nou) — motorul de îmbogățire (pur, fără rețea)

```python
def parseaza_detaliu(text: str) -> dict:
    """Rulează toți extractorii pe textul paginii de detaliu → dict de câmpuri."""
    # structura, incalzire, (stare, stare_incredere), parcare_tip, dotari, etaje_total

def imbogateste_detalii(
    comparabile: list[Comparabila],
    fetchers: dict[str, Callable[[str], str | None]],
    cache: CacheDetalii | None = None,
) -> int:
    """Pentru fiecare comparabilă cu url, fetch (cu cache) + parse detail-page,
    populează câmpurile și setează detalii_complete=True. Întoarce nr. îmbogățite.

    - fetchers: mapare sursă → funcție care ia url și întoarce textul paginii (sau None la eșec).
      Sursele fără fetcher (conectorii-schelet) sunt sărite (rămân detalii_complete=False).
    - Fetch eșuat (None) → comparabila rămâne detalii_complete=False, fără ajustare de dotări.
    """
```

`fetchers` e **injectabil** → în teste se pasează un dict fals (fără rețea). În producție, orchestratorul construiește maparea din conectorii reali.

### 4. `acp/cache_detalii.py` (nou) — cache pe disc

```python
class CacheDetalii:
    def __init__(self, dir: str = ".cache/detalii", ttl_zile: int = 1): ...
    def get(self, url: str) -> dict | None:   # None dacă miss sau expirat
    def set(self, url: str, campuri: dict) -> None:
```
Cheie = `sha256(url)`; fișier `.cache/detalii/<hash>.json` cu `{"fetched_at": ISO, "campuri": {...}}`. Stochează **câmpurile parsate**, nu HTML brut (mai mic, mai rapid). TTL implicit **1 zi** (prețurile pot scădea; vrem date proaspete). Directorul `.cache/` e gitignorat.

### 5. Per-conector — fetch text detail-page

Fiecare din cei 3 conectori reali expune:
```python
def fetch_detaliu_text(self, url: str) -> str | None:
    """Deschide pagina de detaliu (Playwright, USER_AGENT, secvențial), întoarce textul
    complet (page.inner_text('body')) sau None la eșec (timeout/403/Cloudflare persistent)."""
```
Reutilizează exact `USER_AGENT` + `locale="ro-RO"` din connector (dovedit că trece de Cloudflare pe detail-page). Timeout per pagină ~30s + 1 retry pe erori tranzitorii. 403/Cloudflare persistent → `None`.

### 6. `acp/ajustari.py` — gardă pe dotări

Factorii `_ajustare_mobilat`, `_ajustare_ac`, `_ajustare_balcon`, `_ajustare_boxa` returnează `None` la început dacă `not comp.detalii_complete`. Structură/încălzire/stare rămân neschimbate (au deja gardă „ambele cunoscute", iar acum `comp.structura/incalzire/stare` se populează din detail-page).

### 7. `acp/core/pipeline.py` — integrare + toggle

`deduplicate_and_analyze(..., imbogateste: bool = True)`:
- Dacă `imbogateste`: calculează supraviețuitorii `filtreaza(dedup(vanzari))`, construiește `fetchers` din conectori, apelează `imbogateste_detalii(survivors, fetchers, cache)`, apoi `analizeaza(subiect, comparabile_toate, ...)` (re-filtrarea idempotentă păstrează aceleași obiecte, acum îmbogățite).
- Dacă `not imbogateste`: comportamentul actual (rapid, doar etaj+suprafață credibile).

Default `True` (corectitudine); `False` pentru viteză.

## Robustețe

- Secvențial, timeout per pagină (~30s) + 1 retry pe tranzitorii.
- Orice eșec (timeout, 403, parse gol) → `detalii_complete=False` → comparabila rămâne în analiză, dar **fără** ajustare de dotări (nu primește credit fals, nu se pierde).
- Log: câte comparabile au fost îmbogățite din câte încercate.

## Testare

- **Unit** `extrage_dotari`: text cu mobilat/AC/balcon/boxă → listă corectă; text fără → `[]`.
- **Unit** `extrage_etaje_total`: „P+8E" → 8; lipsă → `None`.
- **Unit** `parseaza_detaliu`: un blob de text realist (gen pagina Colentina) → toate câmpurile corecte.
- **Unit** factori dotări: `detalii_complete=False` → `None` (fără ajustare); `True` + diferență reală → ajustare corectă.
- **Unit** `imbogateste_detalii` cu fetcher fals: populează câmpuri + `detalii_complete=True`; fetcher care întoarce `None` → `detalii_complete=False`; sursă fără fetcher → sărită.
- **Unit** `CacheDetalii`: miss → None; set apoi get → hit; intrare expirată (ttl) → None.
- **Integrare** orchestrator cu conectori mock (fără rețea): fluxul fetch→filtrare→îmbogățire(mock)→analiză produce `euro_mp_ajustat` care ține cont de dotările reale.
- **Regresie**: suita existentă rămâne verde (195 teste).
- **Live manual** (final): pe anunțul Colentina — verificăm că verdictul reflectă dotările reale ale comparabilelor, nu biasul.

## Non-scope (YAGNI)

- Îmbogățirea comparabilelor tăiate de filtrare (doar supraviețuitorii).
- Parsing real pe cei 6 conectori-schelet (rămân fără fetcher → sărite).
- Fetch paralel (am ales secvențial pentru robustețe Cloudflare).
- Vision/LLM pe poze (rămâne validare pe subiect, făcută de agent).
