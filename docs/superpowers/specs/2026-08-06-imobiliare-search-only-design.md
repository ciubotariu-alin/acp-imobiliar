# imobiliare.ro doar din search (fără îmbogățire) — Design

**Goal:** Păstrează imobiliare.ro ca sursă de comparabile (cel mai bun inventar) folosind **doar lista din pagina de căutare** — o singură încărcare prin Chrome real — fără să deschidem paginile de detaliu `/oferta/`. Astfel imobiliare contribuie comparabile fără să declanșeze escaladarea Cloudflare cauzată de volumul de îmbogățire, iar excluderea subiectului se face fără niciun fetch.

## Context (de ce)

imobiliare.ro pune un **Cloudflare managed challenge** pe path-urile `/oferta/*` și search. Testat exhaustiv (2026-08-06):

- **Niciun browser headless nu trece** — Chromium bundle, Chrome real, Firefox, WebKit, patchright: toate primesc soft-block (pagină generică, 0 anunțuri) sau rămân blocate în challenge. Cloudflare detectează robust modul headless.
- **Doar Chrome real headed (vizibil) trece** — `channel="chrome"`, `headless=False`, profil proaspăt → 26-30 anunțuri de Colentina.
- **Volumul escaladează** — la îmbogățire (~17 pagini `/oferta/` în rafală) Cloudflare trece de la challenge silențios la unul **interactiv** (checkbox Turnstile) pe care automation-ul nu-l rezolvă.
- **Profilul se „flag-uiește"** cu traficul → challenge interactiv blocant; un profil **proaspăt** trece în ~1s.

Concluzie: singura cale sustenabilă e **volum minim (1 încărcare de search) + Chrome real headed + profil efemer**. Renunțăm la îmbogățirea imobiliare (poze + dotări din detaliu).

## Ce păstrăm / ce pierdem

**Păstrăm:**
- imobiliare ca sursă de comparabile cu **ajustare pe datele din card**: etaj/vechime/mărime (din etaj/an/suprafață — `an` prezent la 25/26 din `data-year`) **și** stare/structură/încălzire/parcare (din textul cardului, populate deja de `_normalize_listing_to_comparabila`). Ajustarea se face — doar pe ce știm din search, nu din detaliu.
- **Excluderea subiectului** — pe **metadata**, fără fetch: `potrivire_metadata_subiect` (etaj+camere+±2mp+±1% preț) prinde atât **propriul anunț** (se potrivește exact cu subiectul) cât și **geamănul** de la altă agenție. Validat: a scos fix subiect+geamăn, zero fals-pozitive.

**Pierdem conștient:**
- Ajustările de **dotări din pagina de detaliu** (mobilat/AC/balcon/boxă) pentru comparabilele imobiliare — dar **nebiasat** (garda `detalii_complete=False` nu aplică ajustări de dotări pe comparabile ne-îmbogățite). Restul ajustărilor (numerice + stare/structură/încălzire/parcare din card) se aplică normal.
- **Dedup pe poze pentru imobiliare** — duplicatele cross-agenție/cross-portal ale unor apartamente *care nu-s subiectul* nu se prind (rar). Subiectul + geamănul rămân excluse (URL + metadata).
- **Risc rezidual (mic):** excluderea pe metadata (fără confirmare pe poze) ar putea, teoretic, scoate un apartament *genuin diferit* care se potrivește exact pe etaj+camere+±2mp+±1% preț cu subiectul. Validat gol în cazul de test (Colentina: a scos fix subiect+geamăn), dar riscul există când mai multe apartamente aproape-identice ca preț/suprafață/etaj coexistă în zonă. Acceptat conștient (pierdem eventual 1 comparabilă genuină în schimbul excluderii sigure a auto-comparației).

## Constrângeri (Global Constraints)

- **Fără dependențe Python noi.** E folosește Chrome real prin `channel="chrome"` (Playwright deja instalat). NU folosește patchright (testat, n-a ajutat — de dezinstalat împreună cu Firefox/WebKit).
- **Cerință de runtime:** Google Chrome instalat pe mașină. Dacă lipsește sau lansarea eșuează → `ConnectorError`, orchestratorul continuă fără imobiliare (degradare grațioasă).
- **imobiliare = sursă search-only:** ZERO încărcări `/oferta/`. Nici la căutare (post-parsare din cardul de search), nici la îmbogățire, nici la poze.
- **1 încărcare de search per analiză**, prin **profil efemer** (temp dir per search, șters după) — evită acumularea de flag pe profil.
- **Headed obligatoriu** (fereastră vizibilă ~câteva secunde). Headless-ul e blocat de Cloudflare — nu e opțiune.
- olx / storia / romimo rămân **neatinse** (invizibile, fără Cloudflare).
- Suita de teste rămâne verde.

## Componente

### 1. `acp/connectors/real_chrome.py` (nou) — fetch prin Chrome real headed

Modul izolat pentru încărcarea unei pagini imobiliare prin Google Chrome real, trecând challenge-ul Cloudflare.

```python
def chrome_disponibil() -> bool:
    """True dacă Google Chrome (channel=chrome) poate fi lansat."""

def fetch_html(url: str, user_agent: str, timeout_ms: int = 60000,
               scroll: int = 6, challenge_sec: int = 20) -> str:
    """Deschide `url` cu Chrome real (channel='chrome', headless=False) pe un profil
    EFEMER (tempfile.mkdtemp, șters în finally), așteaptă dispariția challenge-ului
    Cloudflare (titlul nu mai conține 'moment', ≤ challenge_sec), derulează pentru
    listele lazy și întoarce HTML-ul.

    Ridică RuntimeError dacă challenge-ul nu se rezolvă (profil/IP flag-uit) sau dacă
    Chrome nu poate fi lansat — apelantul (connectorul) o transformă în ConnectorError.
    """
```

Detalii: `launch_persistent_context(mkdtemp, channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"], viewport=1366x900, locale="ro-RO", user_agent=UA)`. După `goto(wait_until="domcontentloaded")`, poll title ≤`challenge_sec`; apoi `wait_for_timeout(3000)` + `scroll` derulări; `page.content()`. `finally`: close context + `shutil.rmtree(profil, ignore_errors=True)`.

### 2. `acp/connectors/imobiliare.py` — search prin Chrome real

`_fetch_html` (folosit doar de search) delegă la `real_chrome.fetch_html` în loc de Chromium bundle:

```python
async def _fetch_html(self, url: str) -> str:
    from acp.connectors import real_chrome
    if not real_chrome.chrome_disponibil():
        raise ConnectorError("imobiliare.ro: Google Chrome real indisponibil", connector=self.name)
    await self._respect_rate_limit()
    try:
        return await asyncio.to_thread(
            real_chrome.fetch_html, url, USER_AGENT, self.timeout_ms
        )
    except Exception as e:
        raise ConnectorError(f"imobiliare.ro Chrome real: {e}", connector=self.name) from e
    finally:
        self._last_request_monotonic = time.monotonic()
```

(Notă: `real_chrome.fetch_html` e sincron cu propriul `asyncio.run` intern → rulat prin `asyncio.to_thread` ca să nu se lovească de bucla curentă.)

**Elimină îmbogățirea imobiliare:** se scot metodele `fetch_detaliu` și `fetch_detaliu_text` de pe `ImobiliareConnector`. Astfel filtrul `hasattr(c, "fetch_detaliu")` din pipeline exclude automat imobiliare din îmbogățire; comparabilele imobiliare rămân `detalii_complete=False` și `poze_urls=[]`.

### 3. `acp/core/pipeline.py` — mod de excludere subiect

Motorul `confirma_si_dedup` rămâne neschimbat (fără url-match). Excluderea subiectului pentru imobiliare se face exclusiv pe **metadata**, activată prin `fallback_metadata_subiect=True` (vezi mai jos). Metadata prinde atât propriul anunț (potrivire exactă) cât și geamănul.

Pipeline-ul decide cum se exclude subiectul, în funcție de sursa lui:

```python
subiect_hashes = []
fallback_metadata = False
if subiect.url and _este_imobiliare(subiect.url):
    # subiect search-only (imobiliare): fără poze; excludere pe metadata
    fallback_metadata = True
elif subiect.url:
    # olx/storia: fetch poze subiect
    _, poze = detaliu_fetch.fetch_detaliu(subiect.url, UA_DETALIU)
    subiect_hashes = hashuri_din_urls(poze, UA_DETALIU)
    # fetch eșuat -> NU excludem agresiv pe metadata (fix existent)
else:
    fallback_metadata = True  # date manuale, fără url

pastrate, dup_elim, subj_elim = confirma_si_dedup(
    survivors, subiect, subiect_hashes, fetch_poze,
    fallback_metadata_subiect=fallback_metadata,
)
```

`_este_imobiliare(url) = "imobiliare.ro" in url`. Restul integrării (eliminare prin `id()`, `analizeaza` pe setul curat) rămâne neschimbat.

## Flux

```
fetch imobiliare (1 încărcare, Chrome real headed, profil efemer) → carduri search
  + olx/storia/romimo (invizibil, httpx/Chromium headless)
      → filtreaza (dedup + supr/an)
      → îmbogățire survivors OLX/STORIA (imobiliare exclus automat: fără fetch_detaliu)
      → dedup subiect: metadata (propriu + geamăn), fără fetch pentru imobiliare
        · dedup pe poze rămâne pentru olx/storia
      → analizeaza (set curat)
```

## Testare

- **Unit `real_chrome`:** `chrome_disponibil()` întoarce bool fără să arunce; `fetch_html` — partea de decizie de challenge e greu de testat fără browser real, deci se testează manual/integrare (vezi Live). Se poate testa un helper pur de detecție „title conține 'moment'" dacă e extras.
- **Unit `confirma_si_dedup` metadata:** cu `subiect_hashes=[]` și `fallback_metadata_subiect=True`, o comparabilă care se potrivește pe metadata cu subiectul (propriul anunț SAU geamănul) → `subiect_eliminate`; o comparabilă care nu se potrivește → păstrată. (Comportament deja acoperit de testele existente ale motorului — se verifică doar că rămâne valid.)
- **Unit pipeline:** subiect imobiliare → `fallback_metadata=True`, NU se apelează `fetch_detaliu` pentru poze subiect; subiect olx cu fetch reușit → poze folosite; subiect fără url → `fallback_metadata=True`.
- **Regresie:** testele de status-branching din `test_imobiliare_connector.py` care mock-uiau lanțul `chromium.launch(headless=True)` se actualizează/elimină (calea bundle e înlocuită); testele Task 4 pentru `imobiliare.fetch_detaliu` se elimină (metoda dispare); restul suitei rămâne verde.
- **Live (manual, IP proaspăt):** rulare Colentina → imobiliare ~26 comps din 1 încărcare; subiect (275238880) și geamăn (275736626) excluși prin metadata; zero încărcări `/oferta/`; olx/storia/romimo contribuie normal.

## Non-scope (YAGNI)

- imobiliare invizibil (headless) — imposibil, Cloudflare blochează headless (testat exhaustiv).
- Îmbogățire imobiliare (dotări/poze) și dedup pe poze pentru duplicate imobiliare care nu-s subiectul.
- Rezolvarea challenge-ului interactiv / managementul reputației IP dincolo de profil efemer (proxy rezidențial, FlareSolverr, cookie-harvest — rămân opțiuni de viitor dacă profilul efemer nu mai ajunge).
- Suport CI/server headless pentru imobiliare (cere display) — degradare grațioasă (ConnectorError, orchestratorul continuă).
- Rotație de profile în pool / reutilizare cf_clearance — profil efemer per-search e suficient la 1 încărcare/analiză.
