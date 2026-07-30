# Design — ACP Imobiliar (Analiză Comparativă de Piață)

**Data:** 2026-07-30
**Autor:** Alin (uz personal)
**Status:** Design aprobat pe secțiuni; în așteptarea revizuirii finale a spec-ului

## 1. Scop

Un automatism pentru **uz personal** care preia un anunț imobiliar (link sau date manuale) și
produce un **raport de Analiză Comparativă de Piață (ACP)** în format PDF, în stilul documentului
de referință `exemple/ACP_ConfortCity_90zile.pdf`.

Raportul nu e doar o cifră de preț — e un **document de consultanță de vânzare** complet:
fișa proprietății, tabel de comparabile cu €/mp, verdict de poziționare, plan de preț eșalonat
calibrat pe o **țintă de zile dată de utilizator**, profiluri de cumpărător, unghi de investiție
(randament), reguli de negociere și un text de anunț gata de publicat.

Partea narativă e generată de un agent care se comportă ca un **agent imobiliar cu 20 de ani de
experiență** pe piața locală.

### Non-obiective (YAGNI pentru v1)
- Nu e produs multi-utilizator, fără hosting/conturi/scalare.
- Nu e evaluare autorizată ANEVAR (se spune explicit în raport).
- Nu rulează 100% neasistat: e un flux semi-supravegheat, orchestrat de agent.

## 2. Abordare aleasă

**Opțiunea 1 — Skill + agent, cu scripturi ajutătoare (hibrid).**

Motivație: partea valoroasă (strategie + redactare) e judecată de piață, exact ce face bine un
LLM; scraping-ul e fragil și e mai ușor de reparat în bucăți mici deterministe. Uz ocazional →
fără infrastructură. Cel mai mic efort de întreținere pentru cel mai bun rezultat.

Împărțirea muncii:
- **Determinist (scripturi testabile):** scraping per portal, calcul €/mp + statistici, randare HTML→PDF.
- **Agent (judecată):** alegerea comparabilelor bune, verdictul de poziționare, narativul, strategia.

## 3. Arhitectură — pipeline în 7 etape

```
[0] INPUT
    ├─ Link (imobiliare.ro / storia.ro / olx.ro / …)  → extrage automat fișa
    ├─ Date manuale (zonă, mp, camere, etaj, an…)      → completate de utilizator
    └─ Ținta de zile (N) + constrângeri opționale       → obligatoriu N

[1] FIȘA SUBIECTULUI  (obiect structurat)

[2] LOCALIZARE  → normalizează zona (locație reală vs. etichetă anunț) → parametri căutare + rază

[3] CĂUTARE COMPARABILE  (connector per portal: camere + suprafață ±X% + zonă/rază)

[4] FILTRARE & DEDUPLICARE  (comparabilitate, dedupe cross-portal, outlieri)

[5] ANALIZĂ  (€/mp per comp, €/mp subiect, min/mediană/max, poziționare, ajustări)

[6] NARATIV  (agent „20 ani": strategie pe N zile, profiluri, reguli, text anunț)

[7] RANDARE PDF  (template HTML/CSS → PDF, stilul documentului de referință)
```

Fiecare etapă are intrare/ieșire clare (obiect de date bine definit) pentru a putea repara o
etapă fără a strica restul — mai ales connectorii de scraping.

## 4. Etapa 0–1: Input & fișa subiectului

Intrare de la utilizator la pornire:
- **Anunțul subiect**: link SAU date manuale.
- **Ținta de zile** (ex. 30/60/90) — obligatoriu; calibrează strategia.
- Opțional: constrângeri cunoscute (ex. „parcare alocată", „preț minim acceptabil X").

Comportament:
- Dacă e **link** → script încearcă extragerea automată; câmpurile lipsă/blocate sunt cerute
  punctual de agent (nu se reia tot).
- Dacă e **manual** → utilizatorul completează câmpurile esențiale.

**Fișa subiectului** (obiect standard):

| Câmp | Exemplu |
|---|---|
| Preț cerut | 87.000 € |
| Suprafață totală / utilă | 66 mp / ~61 mp |
| Camere (+ potențial) | 2 (transformabil în 3) |
| Etaj / total | 10 / 11 |
| An construcție / structură | 2009 / cărămidă |
| Încălzire, dotări | centrală proprie, mobilat+utilat, A/C |
| Locație reală + coordonate | Confort City, Splaiul Unirii 9, S3/Popești |
| Parcare | neconfirmat / inclus |
| Tip vânzător | persoană fizică |

**Locație reală vs. etichetă anunț:** agentul verifică coordonatele/reperele și folosește locația
reală atât pentru comparabile, cât și pentru raport (ex. „Vitan-Bârzești" declarat, dar de fapt
la limita Popești-Leordeni).

## 5. Etapa 2–3: Localizare & căutare comparabile

Etapa cea mai fragilă → **un connector per portal**, aceeași interfață:
`caută(criterii) → listă comparabile brute`. Un connector căzut nu blochează restul.

Criterii de căutare derivate din fișă: aceeași zonă/ansamblu (sau rază), același nr. camere,
suprafață apropiată, tip apartament, fereastră de vechime.

**Strategie tehnică pe niveluri:**
- **Nivel 1 — fetch simplu** (HTTP + parsare HTML/JSON): portaluri fără anti-bot dur.
- **Nivel 2 — browser automation** (Playwright, „politicos": ritm lent, pauze): imobiliare, grup OLX/storia.
- **Nivel 3 — fallback asistat de agent** (WebFetch/browser punctual) când scriptul e blocat.
- **Fără abuz:** volum mic, ocazional; nu ocolim login/captcha, nu forțăm.

**Categorii de informație strânse (nu doar „active"):**
1. **Anunțuri active** comparabile → miezul analizei (prețuri *cerute*).
2. **Referințe „vândut/rezervat"** (unde portalul le marchează) → calibrare, cu corecție
   anunț→tranzacție **4–8%**. Notă onestă: în România prețurile reale de tranzacție **nu sunt
   publice** la nivel de apartament.
3. **Chirii comparabile** → unghiul de randament (buy-to-let).
4. **Context** ad-hoc (rapoarte de piață, note cartier/transport).

**Portaluri (toate incluse de la lansare, arhitectură extensibilă pentru altele):**

Mari (anti-bot → browser politicos + fallback agent):
`imobiliare.ro, storia.ro, olx.ro`

Secundare / de nișă (de obicei fetch simplu):
`publi24.ro, romimo.ro, sudrezidential.ro, lajumate.ro, waa2.com, anuntul.ro`

Ad-hoc, unde apar comparabile în zonă: `directproprietar.ro` + site-uri de agenții (ex. Elixir, VIB).

**Așteptare onestă:** scopul e *acoperire bună*, nu *garantată exhaustivă*. Raportul listează mereu
sursele efectiv consultate la acea rulare.

## 6. Etapa 4–5: Filtrare, deduplicare & analiză

**Filtrare (praguri implicite, ajustabile):**
- Zonă: același ansamblu/cartier sau rază mică (prioritizare după proximitate).
- Camere: identic (±0).
- Suprafață: ±20% față de subiect.
- Vechime: fereastră ±5 ani.
- Excludem necomparabilele evidente.

**Deduplicare cross-portal:** același apartament apare pe 3–4 portaluri → unificare după semnătură
(suprafață + etaj + an + preț + adresă/poze) ca să nu se numere de mai multe ori.

**Outlieri:** prețuri evident greșite semnalate și scoase din mediană, dar rămân vizibile în listă
cu notă (transparență).

**Calcule (determinist, testabil):**
- €/mp per comparabilă (pe suprafață **totală** declarată; util-ul notat separat).
- €/mp subiect.
- Statistici: nr. comparabile, **min / mediană / max**, eventual quartile — pe €/mp **ajustat**.
- Poziționarea subiectului față de mediană („+X% peste mediană").

### Ajustări (recalibrate de agent per raport)

**Mecanism:** fiecare comparabilă e normalizată spre subiect — se ajustează prețul comparabilei ca
și cum ar avea aceleași caracteristici ca proprietatea subiect. Statistica se calculează pe €/mp
*ajustat*.

```
preț ajustat comp = preț comp × (1 + Σ ajustări pentru diferențele față de subiect)
```

**Model hibrid:** tabelul de mai jos e baza/guardrail; **agentul „20 ani" recalibrează valorile
per raport** pe baza evidenței din datele locale (ex. cât valorează efectiv parcarea în zona
respectivă), și **explică fiecare ajustare** în raport (cifră + motiv, nu „din burtă"). Fiecare
ajustare e vizibilă și contestabilă.

| Factor | Regulă | Magnitudine tipică (start) |
|---|---|---|
| Stare/finisaje | necesită renovare vs. renovat | −10…−20% (≈ cost renovare) |
| Mobilat + utilat | complet vs. gol | +3…+7% (≈ 3–6k) |
| Parcare | loc deținut inclus | +8.000…+15.000 € (premium); +2…5k în ansamblu de graniță |
| Etaj | parter −5…−8%; ultimul −2…−4% (dacă nu penthouse); etaj înalt cu lift+lumină +1…+3% | |
| An / vechime | mai nou = premium | ±3…5% / deceniu (≈0 în același ansamblu) |
| Suprafață | unități mari au €/mp mai mic | ponderare mai mare pentru mp apropiat; corecție de gradient dacă diferă mult |
| Compartimentare | decomandat vs. semidecomandat | +1…+3% |
| Balcon / terasă | terasă mare / balcon generos | +1…+3% |
| Tip vânzător / comision | agenție cu comision cumpărător vs. „comision 0%" | ajustare la preț efectiv |
| Anunț→tranzacție | preț cerut → preț închidere | −4…−8% (aplicat global la final) |

### Context de piață (ofertă & tensiune)

Indicator care **nu ajustează comparabilele**, ci calibrează strategia și verdictul:
- **Nr. comparabile active** în zonă la data analizei (oferta curentă) — mereu, derivat din Etapa 3.
- Când portalul oferă: **timp mediu pe piață** (days on market), **câte au deja reduceri de preț**,
  **ritmul de anunțuri noi** — semnale de tensiune.
- Derivat: încadrare **„piața cumpărătorului / echilibrată / a vânzătorului"**.

Efect: ofertă mare → presiune în jos, start aproape de mediană, reduceri mai dese pe ținta de zile;
ofertă mică → testezi plafonul mai mult, reduceri mai lente. Intră direct în calibrarea planului pe
faze (Etapa 6).

**Verdict de poziționare** (combinând statistici ajustate + context de piață + **ținta de zile**):
- interval **preț de listare** recomandat;
- interval realist **preț de tranzacționare** (cu corecția anunț→tranzacție);
- încadrare: „sub piață / corect / supraevaluat".

## 7. Etapa 6: Narativ (persona „20 de ani experiență")

Pasul rulează sub instrucțiunea: *„ești agent imobiliar cu 20 de ani de experiență pe piața
locală; scrii pentru vânzător, cu judecată de piață, tactici de negociere, onestitate a locației."*
Intrare: fișă + comparabile + analiză + ținta de zile. Produce:

1. **Recomandarea de poziționare** — sinteza de sus.
2. **„De ce N zile schimbă strategia"** — registru calibrat pe N (≤45 zile: sub mediană din start;
   ~90 zile: testezi plafonul, cobori în trepte). Nu copiază orb „90 zile".
3. **Plan de preț eșalonat** — N împărțit în faze (ex. 3×30), fiecare cu preț de listare, obiectiv,
   prag de decizie (nr. vizionări/oferte); reducerile ca mărime/ritm derivă din poziționare **și din
   contextul de piață** (ofertă mare → reduceri mai dese/agresive; ofertă mică → mai lente);
   fiecare reducere = „relansare".
4. **Profiluri de cumpărător** pe faze (premium „gata de mutare" → investitor randament → familie/
   navetist sensibil la preț) + „cine NU e clientul".
5. **Unghi de investiție** — randament brut din chiriile comparabile.
6. **Reguli de execuție** — refresh titlu/foto la schimbarea fazei, tratarea lowball-urilor, când
   grăbești fazele.
7. **Anexă: text de anunț gata de publicat** — titlu + descriere calibrate pe strategie și pe
   locația reală, copiabil direct.

Toate secțiunile citează **date reale** din analiză (mediană, nr. comparabile, randament).

## 8. Etapa 7: Randare PDF & stil

Template **HTML + CSS → PDF**, reproducând fidel documentul de referință (bleumarin/crem).

Elemente:
- Antet/subsol pe fiecare pagină (titlu ACP, identificare proprietate, „Document confidențial •
  Estimare analitică, nu evaluare autorizată ANEVAR", nr. pagină).
- Fișa proprietății (tabel 2 coloane cheie/valoare).
- Bloc **Context de piață** (nr. comparabile active, tensiune ofertă, days-on-market dacă există).
- Tabel comparabile (rând „Subiect" evidențiat; coloane: comparabilă, supr., etaj, an,
  dotări/parcare, preț, €/mp brut și **ajustat**; note pentru ajustare/„listat"/outlier).
- Casete evidențiate (fundal crem, bordură) pentru recomandări/concluzii.
- Tabel plan pe faze (fază, zile, preț, obiectiv, prag).
- Blocuri profiluri cumpărători (etichete Faza 1/2/3).
- Anexă anunț (casetă titlu + descriere).

**Elemente fixe (transparență):** notă metodologică (surse, corecția anunț→tranzacție), lista
surselor consultate, data analizei, disclaimer ANEVAR.

Ieșire: `output/ACP_<proprietate>_<Nzile>_<data>.pdf` + HTML intermediar (editabil înainte de export).

## 9. Structura proiectului

Locație: `~/OwnDevelopment/acp-imobiliar/`.

```
acp-imobiliar/
├─ SKILL.md                 # instrucțiunile agentului (persona 20 ani + pașii pipeline)
├─ connectors/              # câte un scraper pe portal, aceeași interfață
│   ├─ imobiliare.py        # mari (browser politicos)
│   ├─ storia.py
│   ├─ olx.py
│   ├─ publi24.py           # secundare (fetch simplu)
│   ├─ romimo.py
│   ├─ sudrezidential.py
│   ├─ lajumate.py
│   ├─ waa2.py
│   ├─ anuntul.py
│   └─ …                    # extensibil (directproprietar, agenții)
├─ core/
│   ├─ subiect.py           # extragere/normalizare fișă subiect
│   ├─ filtrare.py          # comparabilitate + deduplicare + outlieri
│   └─ analiza.py           # €/mp, statistici, poziționare (determinist, testabil)
├─ raport/
│   ├─ template.html        # stilul PDF (bleumarin/crem)
│   └─ render.py            # HTML → PDF
├─ tests/                   # teste filtrare/analiză + fixturi HTML salvate
├─ exemple/                 # PDF-ul de referință
└─ output/                  # rapoartele generate
```

**Determinist vs. agent:** `core/` și `render.py` = scripturi pure cu teste (calculul €/mp mereu
corect); scraping cu fixturi salvate pentru testarea parsării fără a lovi site-urile; narativ +
alegere comparabile + verdict = treaba agentului.

**Limbaj:** Python (scraping/Playwright + randare PDF).

## 10. Cum se rulează (uz personal)

1. Deschizi proiectul în Claude Code și dai comanda cu link (sau date manuale) + ținta de zile.
2. Agentul: extrage fișa → caută pe portaluri → filtrează/analizează → arată pe scurt comparabilele
   și verdictul.
3. Confirmi/ajustezi (ex. „scoate comparabila X", „am parcare inclusă").
4. Agentul scrie narativul și generează PDF-ul în `output/`.

## 11. Riscuri & mitigări

- **Anti-bot / ToS portaluri:** volum mic, ritm politicos, fallback asistat de agent; acoperire bună
  nu garantată exhaustivă; connectori izolați ca să nu cadă tot.
- **Fragilitate parsare (schimbări de site):** connectori mici + fixturi de test → reparare rapidă.
- **Prețuri de tranzacție nepublice:** folosim marcaje „vândut" + corecție anunț→tranzacție 4–8%,
  declarate transparent.
- **Duplicate care umflă statistica:** deduplicare cross-portal după semnătură.
- **Outlieri:** semnalați și excluși din mediană, dar vizibili cu notă.

## 12. Criterii de succes (v1)

- Pentru un link/subiect dat + N zile, produce un PDF în stilul de referință cu: fișă, tabel
  comparabile real strânse, statistici €/mp, verdict, plan pe N zile, profiluri, text anunț.
- Calculul €/mp și statisticile au teste care trec.
- Toate portalurile din listă au connector la lansare (mari + secundare); arhitectură extensibilă
  pentru altele. Un connector căzut nu blochează restul, iar raportul declară sursele efectiv folosite.
- Raportul declară mereu sursele consultate și disclaimerele.
