# Deduplicare cross-agenție + excludere subiect (prin poze) — Design

**Goal:** Elimină din comparabile (a) anunțul propriu al subiectului, listat de una sau mai multe agenții, și (b) același apartament re-listat de agenții diferite — folosind metadata ca pre-filtru ieftin și **potrivirea de poze ca verdict**. Astfel mediana nu mai e ancorată artificial de apartamentul-subiect comparat cu el însuși.

**Context (bug confirmat live):** În analiza de Colentina, apartamentul-subiect apărea de **două ori** printre comparabile — anunțul propriu (id 275238880, 108.000 €, 59mp, etaj 2) și geamănul lui de la altă agenție (id 275736626, 108.000 €, 60mp, etaj 2). `dedup` actual (semnătură `(round(supr), etaj, an, round(pret))`) le rata pentru că suprafața (59 vs 60) și anul (1980 vs 1978) diferă ușor, deși prețul e identic la euro. Perechea 48mp/etaj5/2024 la 133.097 vs 134.266 € (0,9% diferență) confirmă tiparul.

## Principiul
- **Metadata = pre-filtru ieftin.** Marchează perechi *suspecte* de duplicat; nu decide singură.
- **Pozele = verdictul.** Descărcăm și hash-uim poze DOAR pentru anunțurile din grupuri-candidat (nu pentru toate), apoi confirmăm.
- Două anunțuri care împart o poză (sub prag perceptual) = **același apartament**.
- O comparabilă care împarte o poză cu **subiectul** = subiectul însuși → **exclusă**.

## Decizii (din brainstorming)
- **Excludere subiect:** metadata + confirmare pe poze. Agentul furnizează `Subiect.url`; îi extragem pozele o dată și le hash-uim. Fallback la excludere doar-metadata dacă `url` lipsește (date manuale).
- **Pre-filtru candidat:** același **etaj** + același **număr de camere** + suprafață **±2mp** + preț **±1%**.
- **Poze = confirmare peste metadata** (nu înlocuiesc metadata; o confirmă).

## Flux (unde se plug-uiește)
```
fetch → filtreaza (zonă / supr / camere / an)
      → îmbogățire survivors (detalii + [NOU] extrage URL-uri poze)
      → [NOU] dedup pe poze + excludere subiect
      → analizeaza (statistici pe setul curat)
```
Rulează **după îmbogățire** (acolo devin disponibile pozele), **înainte de `analizeaza`**. Dedup-ul de metadata din `analizeaza` rămâne ca plasă de siguranță ieftină (idempotentă pe setul deja curățat).

## Componente

### 1. `acp/modele.py` — câmpuri noi
```python
class Subiect(BaseModel):
    ...
    url: str | None = None        # linkul anunțului subiect (agentul îl dă la pasul [0])

class Comparabila(BaseModel):
    ...
    camere: int | None = None     # pentru pre-filtrul de duplicat (connectorii îl extrag deja)
    poze_urls: list[str] = []     # URL-uri de poze (galerie), populate la îmbogățire
```

### 2. `acp/imagini.py` (nou) — perceptual hashing (fără dependență nouă)
Folosește doar Pillow (deja instalat). dHash pe 64 biți (grayscale, 9×8 → diferențe orizontale → 64 biți).
```python
def dhash(imagine_bytes: bytes) -> int | None:
    """Perceptual hash (dHash 64-bit) al unei imagini. None dacă bytes invalizi."""

def distanta_hamming(h1: int, h2: int) -> int:
    """Numărul de biți diferiți între două hash-uri (0 = identice)."""
```
dHash e robust la redimensionare/recompresie și, pe grayscale downscalat, la watermark same-portal.

### 3. `acp/dedup_poze.py` (nou) — motorul de deduplicare
```python
def sunt_candidat_duplicat(a: Comparabila, b: Comparabila) -> bool:
    """Pre-filtru metadata: același etaj, aceleași camere, supr ±2mp, preț ±1%."""

def potrivire_metadata_subiect(subiect: Subiect, c: Comparabila) -> bool:
    """Pre-filtru: comparabila se potrivește cu subiectul (etaj, camere, supr ±2mp, preț ±1%)."""

def confirma_si_dedup(
    comparabile: list[Comparabila],
    subiect: Subiect,
    subiect_hashes: list[int],
    fetch_poze: Callable[[Comparabila], list[int]],
    cache=None,
) -> tuple[list[Comparabila], list[Comparabila], list[Comparabila]]:
    """Întoarce (pastrate, duplicate_eliminate, subiect_eliminate).

    - Pentru comparabilele din grupuri-candidat (metadata) SAU candidate față de subiect,
      obține hash-urile de poze via `fetch_poze` (injectabil; cu cache).
    - Comparabilă cu o poză sub prag față de `subiect_hashes` → subiect_eliminate.
    - Două comparabile candidat cu o poză sub prag între ele → același apt; păstrează una
      (prima văzută), cealaltă în duplicate_eliminate.
    - Comparabilele fără grup-candidat rămân neatinse (nu descărcăm poze degeaba).
    """
```
`fetch_poze` e **injectabil** → testabil fără rețea. Motorul de decizie e pur.

### 4. Extracție + descărcare poze
- **Extracție URL-uri (un singur page-load):** pozele NU sunt în textul body, ci în DOM. Extind fetch-ul de detaliu ca să întoarcă text **și** URL-uri de poze din aceeași navigare, ca să nu încărcăm pagina de două ori:
  - `acp/connectors/detaliu_fetch.py`: async `_extrage_text_pagina` întoarce acum `(text, poze_urls)`; funcția publică devine `fetch_detaliu(url, user_agent, ...) -> tuple[str | None, list[str]]` (text + primele ~4 URL-uri de galerie, filtrând `gallery-thumb`). Se păstrează și un wrapper `fetch_detaliu_text(url, ...) -> str | None` (întoarce doar textul) pentru compatibilitate.
  - Metoda per-conector `fetch_detaliu(self, url) -> tuple[str | None, list[str]]` delegă cu `USER_AGENT`-ul propriu.
  - `acp/detalii.py::imbogateste_detalii`: fetcher-ul întoarce acum `(text, poze_urls)`; funcția stochează `c.poze_urls = poze_urls` pe lângă câmpurile din `parseaza_detaliu(text, ...)`. (Semnătura `fetchers` se schimbă din `Callable[[str], str|None]` în `Callable[[str], tuple[str|None, list[str]]]`.)
- **Descărcare bytes:** `urllib.request` (stdlib) cu user-agent, pentru fiecare URL de poză; timeout scurt; eșec → sări poza.
- **Producția `fetch_poze`:** o funcție care, dată o `Comparabila`, ia `c.poze_urls` (din îmbogățire), descarcă bytes, calculează `dhash` pentru fiecare → listă de hash-uri.

### 5. Cache
- Hash-urile de poze cache-uite pe disc, cheie = URL-ul anunțului → listă de hash-uri (int-uri), TTL 1 zi. Reutilizează design-ul `CacheDetalii` (fișier JSON) sau o instanță separată `CacheHashuri`.

### 6. Integrare orchestrator (`acp/core/pipeline.py`)
`deduplicate_and_analyze(..., dedup_poze: bool = True)`:
- După `imbogateste_detalii(survivors, ...)`, dacă `dedup_poze`:
  - Dacă `subiect.url`: fetch pozele subiectului o dată → `subiect_hashes` (altfel `[]` → excludere doar-metadata).
  - `pastrate, dup_elim, subj_elim = confirma_si_dedup(survivors, subiect, subiect_hashes, fetch_poze, cache)`.
  - Log: câte duplicate + câte instanțe-subiect eliminate.
  - Pasează `pastrate` (+ restul comparabilelor ne-survivor) mai departe; `analizeaza` lucrează pe setul curat.
- Toggle `dedup_poze=True` default; `False` pentru viteză (sare descărcarea de poze).

### 7. Excludere subiect — detaliu
- Agentul setează `Subiect.url` la pasul [0]. Orchestratorul îi fetch-uiește pagina de detaliu → URL-uri poze → `subiect_hashes`.
- O comparabilă `c` e subiectul dacă `potrivire_metadata_subiect(subiect, c)` **și** există o poză a lui `c` sub prag Hamming față de vreun hash din `subiect_hashes`.
- **Fallback (fără `url`):** exclude comparabilele cu `potrivire_metadata_subiect` (doar metadata), acceptând riscul mic de fals-excludere.

## Parametri (impliciți, tunabili)
- **dHash:** 64 biți (9×8 grayscale, diferențe orizontale).
- **Prag potrivire poze:** distanță Hamming **≤ 8** biți între cea mai bună pereche de poze → același apartament.
- **Poze per anunț:** primele **4** de galerie (sar thumbnail-urile `gallery-thumb`).
- **Preț candidat:** ±1%. **Suprafață:** ±2mp. **Etaj + camere:** egale.

## Testare
- **Unit `imagini`:** `dhash` pe imagine sintetică → identică distanță 0; redimensionată (×0.5) distanță mică (≤ prag); imagine complet diferită distanță mare. `distanta_hamming` corectă.
- **Unit `dedup_poze.sunt_candidat_duplicat` / `potrivire_metadata_subiect`:** perechi pe/în afara pragurilor.
- **Unit `confirma_si_dedup`** cu `fetch_poze` injectat (dict hash-uri, fără rețea):
  - două candidate cu hash comun → una eliminată;
  - două candidate fără hash comun → ambele păstrate;
  - comparabilă cu hash comun cu subiectul → în subiect_eliminate;
  - comparabilă fără grup-candidat → neatinsă, fără fetch poze;
  - fallback fără `subiect_hashes` → excludere doar-metadata.
- **Integrare orchestrator** cu `fetch_poze` mock (fără rețea): setul final nu conține duplicatele/subiectul.
- **Regresie:** suita existentă rămâne verde.
- **Live (manual, controller):** re-rulare Colentina cu `Subiect.url` setat → 275238880 și 275736626 dispar din comparabile; mediana se recalculează fără auto-comparație.

## Non-scope (YAGNI)
- Vision/ML embeddings (dHash e suficient și ieftin).
- Descărcare de poze pentru anunțuri fără grup-candidat de metadata.
- Recuperarea recall-ului cross-portal când watermark-urile diferă (follow-up separat).
- Detecția de duplicat pe descriere text (pozele sunt semnalul).
