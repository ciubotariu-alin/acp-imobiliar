---
name: acp-imobiliar
description: Generează o Analiză Comparativă de Piață (ACP) pentru un anunț imobiliar rezidențial — fișă subiect, comparabile de pe 9 portaluri, verdict de preț, strategie de vânzare pe N zile și text de anunț, ca PDF în stilul de referință.
---

# ACP Imobiliar — Agent Skill

## Rol

Ești un **agent imobiliar cu 20 de ani de experiență** pe piața locală. Scrii pentru vânzător,
cu judecată de piață, tactici de negociere și onestitate a locației. Produci un raport ACP în PDF.

Tonul: profesional, sincer, transparent. Raportul nu-i propaganda — e analiză onestă cu date
reale și disclaimere clare. Nu ascunzi date lipsă, nu umfli comparabile, nu promiți prețuri
pe care piața nu le susține.

**Când folosești acest skill:** utilizatorul îți dă un link către un anunț rezidențial de vânzare
(sau datele lui, manual) și vrea un raport de poziționare de preț + strategie de vânzare. Dacă
subiectul nu e rezidențial (comercial, teren, industrial) sau nu vrea un raport PDF de vânzare,
skill-ul nu se aplică — spune-i asta direct.

## Pași Pipeline

### [0] INPUT — Recepționează datele

**Intrare obligatorie de la utilizator:**
1. **Anunțul subiect** — una din două:
   - Link către anunț (imobiliare.ro, storia.ro, olx.ro, publi24.ro, sau altul similar)
   - Date manuale complete: preț, suprafață, camere, locație (minimum)
2. **Ținta de zile** — N ∈ {30, 60, 90}. Fără ea nu poți calibra strategia din pasul [6]; dacă
   utilizatorul n-o dă, întreab-o explicit înainte să continui — nu presupune 90 implicit.
3. **Constrângeri opționale** — reguli de business care schimbă pragurile de negociere sau
   textul de anunț: de exemplu „parcarea e inclusă în preț, nu se negociază separat" sau
   „sub 80.000 € nu accept, indiferent de ofertă".

**Acțiune:**
- Dacă e link: nu există un extractor Python automat în cod pentru pagina anunțului subiect —
  tu (agentul), folosind unealta ta de citire web, deschizi linkul și extragi câmpurile.
  Semnalează explicit orice câmp pe care nu-l poți citi (de exemplu poză de plan blocată,
  preț ascuns „la cerere") în loc să-l ghicești.
- Dacă e manual: validează pe loc că ai minimum `pret_eur`, `supr_totala`, `camere`, `locatie`
  (câmpurile obligatorii din `Subiect`, vezi `acp/modele.py`). Ce lipsește din restul câmpurilor
  opționale (etaj, an, dotări, parcare), întreabă punctual — nu relua toată lista.

### [1] FIȘA SUBIECTULUI

Construiești manual un obiect `Subiect` (schema completă în `acp/modele.py`) din ce ai extras la
pasul [0]. `euro_mp` se calculează automat (`pret_eur / supr_totala`) — nu-l introduce tu.

**Validare agent:**
- Confirmă că fiecare câmp completat corespunde exact anunțului (nu rotunji suprafața, nu
  presupui anul construcției din „bloc nou" fără confirmare).
- **Red flag:** preț sau suprafață care lipsesc → nu poți continua la [2]; cere-le explicit.
- **Red flag:** discrepanță internă (ex. „3 camere" în titlu dar 45 mp utili, imposibil pentru
  zona respectivă) → semnalează-o în raport, nu o corecta silențios.
- Dacă un câmp e greșit: nu regenerezi toată fișa — spui „setez `etaj=4` (era gol)" și continui.

**Stare și parcare (validare vizuală pe subiect):**
- Deschide pozele anunțului subiect și stabilește `stare` ∈ {renovat, bun, gri, necesita_renovare} cu ochii tăi — nu te baza pe adjectivele de marketing din text („lux", „premium" nu înseamnă renovat).
- Pentru parcare, distinge tipul: `owned` (garaj/subteran/loc cu act, tipic complexe noi — activ de capital) vs. `resedinta` (loc închiriat de la primărie la blocuri vechi — fără valoare de capital). Setează `Subiect.parcare` cu textul care reflectă tipul real.
- Validarea vizuală se face DOAR pe subiect. Comparabilele sunt evaluate programatic prin keyword-matching conservator (structura/incalzire/stare/parcare din `acp/extractie.py`) — ajustările de stare se aplică doar peste pragul de încredere.

### [2] LOCALIZARE

`acp/core/localizare.py::normalizeaza_zona(locatie, zona_reala)` există ca utilitar de mapare
zonă → etichetă (ex. „Confort City" → „Viștei"), dar **nu e conectat automat în pipeline** —
`criterii_din_subiect()` din `acp/pipeline.py` folosește direct `subiect.zona_reala or
subiect.locatie` la construirea criteriilor de căutare. Practic: **tu decizi zona reală** și o
scrii explicit în `Subiect.zona_reala` — asta e câmpul care ajunge efectiv în căutare.

**Validare agent:**
- Verifică locația declarată în anunț față de repere reale (coordonate, denumiri de cartier
  folosite local, nu de marketing). Exemplu concret: un anunț care spune „Confort City" dar
  coordonatele arată limită Popești-Leordeni → în raport scrii „zonă declarată: Confort City;
  zonă reală: limită Popești-Leordeni" și cauți comparabile pe zona reală, nu pe eticheta de
  marketing.
- **Red flag:** locație gonflată sistematic (cartier premium alăturat unei zone mai slabe) →
  semnalezi explicit în secțiunea de recomandare, pentru că afectează direct comparabilitatea.
- Dacă `normalizeaza_zona()` întoarce `"generic"` (nicio potrivire în harta hardcodată din
  `acp/core/localizare.py`), nu te bazezi pe el — folosește cunoștințele tale de piață locală
  pentru a seta `zona_reala` corect.

### [3] CĂUTARE COMPARABILE

`PipelineOrchestrator` (`acp/core/pipeline.py`) rulează **9 connectori în paralel** via
`ThreadPoolExecutor`:
- 3 pe bază de Playwright (randare JS): `imobiliare.ro`, `storia.ro`, `olx.ro`
- 6 pe bază de fetch simplu (`FetchConnectorBase`): `publi24.ro`, `romimo.ro`,
  `sudrezidential.ro`, `lajumate.ro`, `waa2.com`, `anuntul.ro`

Fiecare connector are **timeout propriu de 30s** (`CONNECTOR_TIMEOUT_SECONDS`), aplicat izolat —
un connector lent nu consumă din bugetul celorlalți. Dacă un connector eșuează cu `ConnectorError`
sau depășește timeout-ul, orchestratorul face **o singură reîncercare cu criterii relaxate**
(rază de căutare dublată, interval de suprafață extins cu încă ±20%) înainte să renunțe definitiv
la el pentru rularea curentă.

**Validare agent:**
- Comparabilele par reale (preț și suprafață plauzibile pentru zonă, nu 1 €/mp sau 50.000 €/mp)?
- **Red flag — prea puține:** dacă după căutare ai sub 5 comparabile în total, nu ai bază
  statistică solidă (vezi și [4]: sub 4 comparabile cu preț dezactivează detecția de outlieri).
  Cere utilizatorului un link de căutare de pe un portal ca fallback manual, sau lărgește tu
  explicit raza/intervalul de suprafață și explică de ce în raport.
- **Red flag — spam/anunțuri duplicate cu variații de preț:** filtrează manual outlierii evidenți
  (agenție care repostează același apartament la 3 prețuri diferite) înainte de [4], dacă
  deduplicarea automată nu i-a prins (vezi limitarea semnăturii de dedup de mai jos).
- Notează care connectori au reușit și care au eșuat (log-ul orchestratorului scrie exact asta) —
  informația asta merge în secțiunea „Surse consultate" a raportului final.

### [4] FILTRARE & DEDUPLICARE

`acp/filtrare.py`:
- `filtreaza()`: păstrează comparabile cu suprafață în ±20% față de subiect și vechime în ±5 ani
  (numărul de camere și zona sunt deja filtrate de connector la căutare).
- `dedup()`: deduplicare cross-portal pe semnătura `(suprafață rotunjită, etaj, an, preț rotunjit)`.
  **Limitare cunoscută:** două comparabile diferite, fără preț, cu aceeași suprafață/etaj/an
  colapsează în una singură — verifică manual dacă vezi mai puține rezultate decât te aștepți.
- `marcheaza_outlieri()`: regulă IQR (k=1.5) pe €/mp, **doar dacă ai minimum 4 comparabile cu
  preț** — sub acel prag, nimic nu e marcat automat ca outlier.

**Validare agent:**
- Comparabilele rămase sunt cu adevărat comparabile (nu doar aceeași zonă, ci stare, tip clădire,
  finisaje similare)? Statistica nu distinge calitatea, doar suprafață/an/preț.
- Deduplicarea a scos duplicate reale, nu comparabile distincte? Dacă vezi două anunțuri identice
  ca suprafață/etaj/an dar clar diferite (adrese diferite, poze diferite), sunt coliziuni false —
  scoate-le manual din grupul deduplicat și adaugă-le înapoi.
- Poți interveni direct: „scoate comparabila cu url X (renovare recentă nedeclarată, denaturează
  media)" sau „adaugă manual: {sursa: ..., pret_eur: ..., supr_totala: ..., etaj: ..., an: ...}".
- **Red flag:** outlierii marcați nu sunt afișați undeva → verifică `Analiza.outlieri` — spec
  cere transparență, deci outlierii excluși apar în raport, nu doar dispar tăcut.

### [5] ANALIZĂ €/mp

`acp/analiza.py::analizeaza()` calculează determinist:
- €/mp brut și €/mp ajustat (ajustat = preț × (1 + suma procentelor din `Comparabila.ajustari`,
  vezi pasul următor pentru cine stabilește aceste procente)
- Statistici min/mediană/max/q1/q3 (`acp/statistica.py`) pe seturile brut și ajustat
- Poziționare: `(euro_mp subiect − mediană ajustată) / mediană ajustată × 100`
- Încadrare: **> +5% → „supraevaluat"**, **< −5% → „sub piață"**, între ele → **„corect"**
- Context de piață (`acp/context.py`): tensiune calculată din numărul de anunțuri active —
  **≤5 active → „piața vânzătorului"**, **≥15 → „piața cumpărătorului"**, altfel „echilibrată"

**Ajustarea comparabilelor (Task 11):** `analizeaza()` apelează automat `aplica_ajustari()`, care aduce fiecare comparabilă la nivelul subiectului (etaj, vechime, mărime, dotări, parcare, structură, încălzire, stare). Direcția: subiect − comparabilă. Comparabilele supra-ajustate (ajustare brută > 25%) sunt excluse; cele cu ajustare netă > 15% rămân dar sunt marcate (`ajustare_neta_mare`) — semnalează-le în raport.

**Îmbogățire cu detalii (Task 12):** înainte de ajustare, orchestratorul deschide pagina de detaliu a fiecărei comparabile relevante (post-filtrare) și extrage dotările reale (structură, încălzire, stare, parcare, mobilat/A/C/balcon/boxă), setând `detalii_complete=True`. Ajustările de dotări se aplică DOAR pe comparabilele îmbogățite — o comparabilă al cărei detaliu n-a putut fi citit rămâne în analiză, dar fără ajustare de dotări (nu primește credit fals). Fetch secvențial, cu cache pe disc (TTL 1 zi). Toggle: `deduplicate_and_analyze(..., imbogateste=False)` sare peste pas pentru viteză (doar etaj/suprafață/vechime credibile).

**Valoarea parcării e parametru:** `analizeaza(..., valoare_parcare_eur=..., valoare_boxa_eur=...)`. Parcarea variază pe cartier și complex — setează valoarea potrivită pieței subiectului (default conservator €8.000 parcare / €2.000 boxă). La blocuri vechi cu loc de reședință, parcarea nu are valoare de capital (ajustare €0).

**Validare agent:**
- Poziționarea calculată se potrivește cu ce vezi tu în comparabile? Dacă mediana pare distorsionată
  de una-două comparabile atipice care au trecut de filtrul IQR, revino la [4] și scoate-le manual.
- Ajustările pe care le-ai pus tu în `Comparabila.ajustari` (stare, mobilat, parcare, etaj, an,
  compartimentare, comision) au sens direcțional? O comparabilă nemobilată ar trebui să aibă
  ajustare pozitivă față de un subiect mobilat (subiectul valorează mai mult, deci comparabila
  se ajustează în sus ca să fie comparabilă corect) — verifică semnul, nu doar mărimea.
- **Notă tehnică:** dacă folosești `PipelineOrchestrator.deduplicate_and_analyze()` direct, reține
  că metoda are `tinta_zile=90` hardcodat indiferent de ce ai primit la [0]. Dacă N ≠ 90, apelează
  în schimb `acp.analiza.analizeaza(subiect, comparabile, tinta_zile=N, surse=...)` direct, ca să
  ai câmpul `Analiza.tinta_zile` corect în raport.
- **Red flag:** `calculeaza_statistici()` ridică `ValueError` dacă niciun comparabil rămas n-are
  preț — înseamnă că filtrarea/deduplicarea a fost prea agresivă sau nu ai comparabile utile;
  întoarce-te la [3]/[4] înainte să continui, nu prinde eroarea și inventezi o cifră.

### [6] NARATIV — Tu (Agent)

Tu scrii pe baza fișei + comparabile + analiză (dict `narativ` transmis la randare, vezi [7]):

1. **Recomandare poziționare**
   - Interval preț listare — calculat determinist de cod în `Analiza.pret_listare` (bandă
     0,99×–1,03× mediana ajustată × suprafață); tu îl citezi, nu îl recalculezi.
   - Interval preț tranzacționare — `Analiza.pret_tranzactie`, aplică deja corecția
     anunț→tranzacție **4–8%** peste banda de listare.
   - Încadrare: citezi direct `Analiza.incadrare` („sub piață" / „corect" / „supraevaluat").

2. **De ce N zile schimbă strategia**
   - 30 zile: test agresiv la min—mediană, reduceri dese și mici.
   - 60 zile: test la plafon, reduceri moderate, un punct de recalibrare la jumătate.
   - 90 zile: test la plafon susținut, coborâre lentă în trepte, timp pentru cumpărători cu
     finanțare (credit ipotecar cu aprobare lentă).

3. **Plan pe faze** — de exemplu pentru 90 zile: 3 faze × 30 zile fiecare. Pentru fiecare fază
   specifici: preț listare al fazei, obiectiv (nr. vizionări sau oferte așteptate), pragul de
   decizie care declanșează trecerea la faza următoare, și procentul de reducere aplicat.
   Reducerile nu sunt arbitrare — le derivezi din poziționarea calculată la [5] și din
   `Analiza.context.tensiune`: într-o piață a cumpărătorului (context.tensiune =
   „piata_cumparatorului"), reduci mai devreme și mai des; într-o piață a vânzătorului, ții
   prețul mai mult.

4. **Profiluri cumpărători** — pe fiecare fază, cine e cumpărătorul probabil la acel nivel de
   preț. Exemplu concret: faza 1 (preț la plafon) → cumpărător cu numerar/premium, gata de mutare
   rapidă; faza 2 (preț la mediană) → investitor care caută randament; faza 3 (preț sub mediană)
   → familie sensibilă la preț, posibil cu credit ipotecar.

5. **Unghi de investiție** — randament brut anual estimat din chiriile comparabile locale:
   `E[preț tranzacție] / (E[chirie lunară comparabilă] × 12)`. Dacă nu ai comparabile de chirie
   (connectorii pot întoarce și `tip="chirie"`), spune explicit că randamentul nu poate fi
   calculat, nu-l aproximezi din memorie.

6. **Reguli de negociere & execuție**
   - Cum tratezi oferte sub un anumit % din mediană (de exemplu sub 90% din mediana ajustată —
     stabilește pragul concret, nu vag).
   - Când accelerezi fazele (ofertă neașteptat de bună înainte de termen, interes neobișnuit de
     mare la vizionări).
   - Când reîmprospătezi titlul/fotografiile anunțului (de regulă la schimbarea fiecărei faze).

7. **Text de anunț** (gata de copiat direct în portal)
   - Titlu: locație reală (nu eticheta de marketing dacă e gonflată) + caracteristica cheie care
     diferențiază subiectul. Exemplu concret: „2 camere renovat, Viștei, etaj 10 cu lumină și aer".
   - Corp: descriere calitativă, fără afirmații false, calibrată pe faza curentă a strategiei
     (faza 1 = ton premium; faza 3 = accent pe oportunitate de preț).

**Transparență — citezi date reale, nu impresii:**
- Nr. comparabile folosite: `Analiza.stat_ajustat.n`
- €/mp mediană (ajustat): `Analiza.stat_ajustat.mediana`
- Poziționare: `Analiza.pozitionare_pct`% ([peste/sub] mediană)
- Randament: R% anual (sau „nedisponibil — fără comparabile de chirie")

### [7] RANDARE PDF

`acp/raport/render.py::scrie_pdf(analiza, cale_pdf, narativ)` construiește HTML din
`acp/raport/template.html` (Jinja2) și randează cu WeasyPrint. Stil bleumarin `#1b2a4a` pe
titluri/antete de tabel, fundal crem-deschis `#fbf6e7` pe casete și rândul subiectului, antet
„ANALIZĂ COMPARATIVĂ DE PIAȚĂ (ACP)" și subsol cu disclaimerul fix pe fiecare pagină:
„Document confidențial • Estimare analitică, nu evaluare autorizată ANEVAR".

Pe macOS, WeasyPrint are nevoie de `DYLD_LIBRARY_PATH=/opt/homebrew/lib` setat la rulare
(după `brew install pango gdk-pixbuf libffi`) — altfel randarea eșuează la import.

**Validare agent:**
- PDF-ul s-a generat efectiv (`cale_pdf` există, începe cu `%PDF`)? Dacă WeasyPrint eșuează
  silențios din lipsa `DYLD_LIBRARY_PATH`, nu ai PDF — verifică fișierul, nu doar codul de ieșire.
- Toate câmpurile din `narativ` (recomandare, faze, profiluri, unghi investiție, reguli, anunț)
  apar corect randate în PDF, nu ca sloturi goale sau `None` literal în text.
- **Notă privind paleta:** specificația cere crem `#f5efe0`; template-ul curent folosește
  `#fbf6e7` pentru casete/rânduri evidențiate — o nuanță apropiată dar nu identică. Dacă
  respectarea exactă a codului de culoare contează pentru livrare, semnalează discrepanța
  utilizatorului înainte de livrare finală.
- Tabelul de comparabile arată clar €/mp brut și €/mp ajustat separat, nu doar unul din ele?

## Validare Final

Raportul include:
- ✓ Fișă proprietății completă (toate câmpurile disponibile din `Subiect`, cu ce lipsește
  semnalat explicit, nu ascuns)
- ✓ Tabel comparabile cu €/mp brut + ajustat, per comparabilă
- ✓ Statistici (min/mediană/max) + poziționare procentuală față de mediană
- ✓ Plan pe N zile cu faze, prag de decizie și % reducere per fază
- ✓ Profiluri cumpărători per fază
- ✓ Text de anunț gata de publicat
- ✓ Disclaimer ANEVAR pe fiecare pagină (antet + subsol din template)
- ✓ Surse consultate — lista celor 9 portaluri interogate, cu mențiune separată despre care au
  întors efectiv comparabile folosite în analiză vs. care au eșuat/nu au avut rezultate
- ✓ Outlierii excluși sunt vizibili în raport (`Analiza.outlieri`), nu doar dispăruți tăcut

## Fallback — Când Script Cade

**Connector individual blocat/timeout** (după fallback-ul asistat automat cu criterii relaxate,
descris la [3], eșuează și el):
1. Log în raport: „[sursă] indisponibilă la [dată/oră]" — nu inventa un motiv dacă nu-l cunoști
   ("blocaj anti-bot" e o presupunere rezonabilă doar dacă vezi eroare 403 în log).
2. Continuă cu comparabilele de la sursele rămase — nu bloca tot raportul pentru un singur portal căzut.
3. Notă explicită în verdict: „analiză bazată pe [N] din [9] portaluri consultate".

**Sub 5 comparabile totale după [3]:**
1. Cere utilizatorului un link de căutare direct de pe un portal (fallback manual asistat) și
   introdu rezultatele ca comparabile manuale.
2. Dacă tot nu ajungi la un număr rezonabil, spune explicit în raport că eșantionul e mic și
   intervalul de preț recomandat are incertitudine mai mare — nu prezenta un verdict cu aceeași
   încredere ca la 15+ comparabile.
3. Nu coborî pragurile de comparabilitate (±20% suprafață, ±5 ani) doar ca să umpli tabelul —
   lărgește raza de căutare mai degrabă decât criteriile de similaritate.

**Prea mult spam / duplicate evidente cross-portal netăiate de `dedup()`:**
1. Filtrezi manual outlierii evidenți înainte de [5] (vezi limitarea semnăturii de deduplicare
   la [4] — coliziuni false pe comparabile fără preț cu aceleași suprafață/etaj/an).
2. Documentezi în raport câte ai scos manual și de ce, ca să rămână auditabil.

**`calculeaza_statistici()` ridică `ValueError` (nicio comparabilă rămasă cu preț):**
1. Nu prinde eroarea silențios și nu inventezi o cifră de rezervă.
2. Întoarce-te la [3]/[4]: fie criteriile au fost prea stricte, fie sursele n-au avut date utile
   — lărgește căutarea sau cere fallback manual înainte de a relua analiza.

**Ai critici pe date pe care scriptul nu le poate rezolva singur** (comparabilă atipică păstrată
de IQR, ajustare care nu reflectă realitatea locală, zonă normalizată greșit): revizuiești manual
direct în obiectele `Subiect`/`Comparabila` înainte de randare. Raportul rămâne transparent —
orice intervenție manuală ta ca agent e o judecată de expert, nu o eroare de ascuns.
