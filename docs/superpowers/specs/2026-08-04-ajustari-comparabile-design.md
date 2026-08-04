# Ajustări Comparabile (Task 11) — Design

**Goal:** Ajustarea prețurilor comparabilelor la nivelul subiectului, ca să compari „mere cu mere" — nu preț brut vs. preț brut, ci preț ajustat pentru diferențe de etaj, vechime, dotări, mărime, structură, încălzire și stare.

**Context:** Modelul `Ajustare` și câmpurile `pret_ajustat` / `euro_mp_ajustat` există deja în `acp/modele.py`, dar nimeni nu populează `Comparabila.ajustari`, deci lista e mereu goală și `euro_mp_ajustat == euro_mp`. Task 11 populează aceste ajustări.

## Scope

**Scope extins:** extindem `Comparabila` cu `structura`, `incalzire`, `stare` și le parsăm, nu doar ajustăm pe ce există deja.

## Principiul de direcție

Ajustezi **comparabila** ca să devină echivalentă cu **subiectul**. Semnul se calculează mereu `subiect − comparabila`:
- Comparabila **inferioară** subiectului → ajustare **pozitivă** (dacă ar fi la fel de bună, ar costa mai mult)
- Comparabila **superioară** → ajustare **negativă**

## Arhitectură

Abordare **post-fetch, centralizată** — nu în conectori:

```
Conectori (9) ──fetch──> Comparabile brute (cu structura/incalzire/stare parsate)
                                  │
                                  ▼
                    acp/ajustari.py::aplica_ajustari(subiect, comparabile)
                                  │  populează c.ajustari pe fiecare
                                  │  aplică garda anti-supra-ajustare
                                  ▼
                    Comparabile ajustate ──> outlieri ──> statistici (pe euro_mp_ajustat)
```

**De ce centralizat:** logica de ajustare într-un singur loc (DRY, testabil), conectorii rămân simpli (doar parsează), consistent pe toți 9 conectorii.

## Componente

### 1. `acp/modele.py` — extindere modele

**`Comparabila`** primește câmpuri noi:
```python
structura: str | None = None       # caramida | bca | panou | beton
incalzire: str | None = None       # centrala_proprie | termoficare | centrala_bloc
stare: str | None = None           # renovat | bun | necesita_renovare | gri
stare_incredere: float = 0.0       # 0-1; ajustarea de stare se aplică doar peste un prag
```

**`Ajustare`** primește suport pentru ajustări **absolute** (parcare, boxă — valori fixe în €, nu procent):
```python
class Ajustare(BaseModel):
    factor: str
    procent: float = 0.0             # ajustare proporțională (etaj, vechime, stare...)
    valoare_abs: float = 0.0         # ajustare absolută în € (parcare, boxă)
    motiv: str
```

**`pret_ajustat`** — ordinea de aplicare: procentele se aplică pe baza proporțională (scalează cu valoarea proprietății), absolutele se adaugă după:
```python
pret_ajustat = pret_eur * (1 + Σ procent) + Σ valoare_abs
```

### 2. `acp/extractie.py` (nou) — extractori din text

Keyword-matching centralizat pe textul brut al anunțului (titlu + descriere), apelat de conectori. Conectorii extrag doar textul brut; extractorii îl interpretează — evită duplicarea pe 9 conectori.

- `extrage_structura(text) -> str | None`
- `extrage_incalzire(text) -> str | None`
- `extrage_stare(text) -> tuple[str | None, float]` — întoarce `(stare, incredere)`

Regula pe stare: **ambiguu → `None` + încredere joasă**. Nu fabricăm valoare din limbaj de marketing. Ajustarea de stare se aplică doar dacă `stare_incredere > prag` (prag = 0.5).

### 3. `acp/ajustari.py` (nou) — calculul ajustărilor

- `calculeaza_ajustari(comparabila, subiect) -> list[Ajustare]` — construiește lista de ajustări factor cu factor.
- `aplica_ajustari(subiect, comparabile) -> tuple[list[Comparabila], list[Comparabila]]` — populează `c.ajustari` pe fiecare comparabilă și separă comparabilele **excluse** de garda de supra-ajustare de cele **păstrate**.

## Factorii și valorile

### Etaj — curbă, nu liniar (liftul se ignoră deocamdată)

| Poziție comparabilă | Ajustare vs. baseline |
|---|---|
| Parter | −5% |
| Etaj 1 (cel mai căutat) | +2% |
| Etaje 2–3 | +1% |
| Etaje intermediare (4 … n−2) | 0% (baseline) |
| Ultimul etaj | −3% |

Ajustarea = `nivel(subiect) − nivel(comparabila)`, plafon **±5%**. Fiecare etaj se mapează la o „valoare de nivel" din tabel; ajustarea e diferența dintre valorile de nivel ale subiectului și comparabilei.

### Vechime (an)

**1% per an diferență**, plafon **±10%**. Suplimentar: comparabilă construită **pre-1977** primește **−3%** (stigmat seismic) dacă subiectul e post-1977.

### Mărime (size curve)

€/mp scade cu suprafața. **0.3% per m² diferență**, plafon **±3%**. Comparabila mai mare → €/mp natural mai mic → ajustare **pozitivă**.

### Dotări — mix procent + absolut

| Dotare | Tip | Valoare |
|---|---|---|
| Parcare/garaj | absolut € | +€9.000 (diferență) |
| Boxă/depozit | absolut € | +€2.000 (diferență) |
| Mobilat + utilat | procent | +4% |
| A/C | procent | +1%/unitate, plafon +3% |
| Balcon/terasă | procent | +3% |

Se ajustează doar **diferența**: dacă subiectul are parcare și comparabila nu → `+€9.000` pe comparabilă; invers → `−€9.000`. Detecția se face pe listele `dotari` (subiect vs. comparabilă) prin keyword-matching.

### Structură

`caramida` +2%, `beton` +2%, `bca` 0% (baseline), `panou` −3%. Ajustarea = valoarea structurii subiectului − valoarea structurii comparabilei.

### Încălzire

`centrala_proprie` +3%, `centrala_bloc` 0% (baseline), `termoficare` −2%. Ajustarea = diferența subiect − comparabilă.

### Stare (doar dacă `stare_incredere > 0.5`)

`renovat` +10%, `bun` 0% (baseline), `gri` −5%, `necesita_renovare` −15%. Ajustarea = diferența subiect − comparabilă, plafon **±15%**.

## Garda anti-supra-ajustare (ANEVAR)

Aplicată în `aplica_ajustari`:
- **Ajustare netă** (Σ cu semn, în procent-echivalent) > **±15%** → ajustarea rămâne, dar comparabila e **marcată** (semnal în raport).
- **Ajustare brută** (Σ valori absolute, în procent-echivalent) > **±25%** → comparabila e **exclusă** din analiză (prea diferită ca s-o ajustezi credibil).

Ajustările absolute (€) se convertesc în procent-echivalent față de `pret_eur` al comparabilei pentru pragurile de mai sus.

## Integrare în pipeline

În `acp/analiza.py::analizeaza`, între `filtreaza` și `marcheaza_outlieri`:
```
filtrate = filtreaza(subiect, dedup(vanzari))
ajustate, excluse_supra = aplica_ajustari(subiect, filtrate)   # NOU
pastrate, outlieri = marcheaza_outlieri(ajustate)              # acum pe euro_mp_ajustat
```
`marcheaza_outlieri` și `calculeaza_statistici` operează pe `euro_mp_ajustat` (deja fac asta prin `stat_ajustat`).

## Parsarea pe conectori

- Conectorii cu parsing real (`imobiliare.ro`, `storia.ro`, `olx.ro`) extrag textul brut (titlu + descriere) și apelează extractorii din `acp/extractie.py` pentru a popula `structura`, `incalzire`, `stare`, `stare_incredere`.
- Conectorii-schelet (cei 6 pe `FetchConnectorBase`) primesc același hook: când capătă parsing real, apelează aceiași extractori. Nu-i implementăm acum, dar interfața e pregătită.

## Validarea foto (doar pe subiect)

Comparabilele folosesc keyword-matching (programatic, ieftin, fără LLM). **Subiectul** e citit de **agentul AI** (Claude care rulează `SKILL.md`) la pasul [0] — el deschide anunțul, se uită la poze, setează `stare` cu ochii lui. Validarea vizuală rămâne pe subiect (1 anunț, om în buclă), nu pe comparabile (zeci de anunțuri, programatic). SKILL.md se actualizează să reflecte asta.

## Testare

- **Unit** pe `calculeaza_ajustari`: fiecare factor izolat (etaj parter/1/intermediar/ultim; vechime în/peste plafon; pre-1977; mărime; fiecare dotare; structură; încălzire; stare pe praguri de încredere).
- **Unit** pe garda anti-supra-ajustare: comparabilă cu brut > 25% e exclusă; netă > 15% e marcată.
- **Unit** pe extractori: text cu keyword clar → câmp; text ambiguu → `None` + încredere joasă.
- **Unit** pe `pret_ajustat`: procent + absolut combinate, ordinea corectă.
- **Integrare**: `analizeaza` cu comparabile ce diferă de subiect → `euro_mp_ajustat != euro_mp`, mediana ajustată diferă de cea brută.
- Regresie: suita existentă (165 teste) rămâne verde.

## Non-scope (YAGNI)

- Vision/LLM pe pozele comparabilelor (cost + latență + nesigur).
- Liftul în curba etajului (simplificăm acum).
- Parsing real pe cei 6 conectori-schelet (doar hook-ul, nu implementarea).
