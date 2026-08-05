"""Connector pentru olx.ro (Playwright politicos).

olx.ro e o SPA React server-side-rendered (nu Next.js, ca storia.ro) — nu
există `__NEXT_DATA__`, dar există un echivalent funcțional: un
``<script id="olx-init-config">`` care conține, printre altele, atribuirea
JS ``window.__PRERENDERED_STATE__ = "<json escapat>";``. Valoarea e un
string JSON *dublu-encodat* (un JSON string care, odată parsat, conține el
însuși un JSON): trebuie ``json.loads`` de două ori. Structura utilă e la
``listing.listing.ads`` — o listă de anunțuri (id, title, price, params,
location, url etc.), analog cu ``searchAds.items`` la storia.ro.

Camere: spre deosebire de storia.ro (`roomsNumber` structurat) sau
imobiliare.ro (atribute `data-*`), categoria de căutare folosită aici
(apartamente-garsoniere-de-vanzare/inchiriat, id 907) NU expune un facet de
filtrare "număr de camere" pe anunțurile individuale — câmpul `params` conține
doar suprafață, an construcție (bucket) și etaj. Filtrul `filter_enum_rooms`
există global în configurația olx.ro, dar se aplică doar altor categorii
(vezi `filters.data.filter_enum_rooms[0].options[].categories`), nu acesteia.
Singura sursă fiabilă e titlul anunțului (ex. "Apartament 2 camere ...",
"Garsoniera ...", "Studio ..."), din care extragem numărul de camere cu
regex + euristici (garsonieră/studio = 1 cameră). Exact lecția din Task 3
(storia.ro): filtrarea după `criterii.camere` nu poate fi delegată URL-ului
de căutare, se face determinist după parsare, în `_search_async` — de la
început, nu ca reparație ulterioară.

Etaj: enum textual (`normalizedValue` din param-ul `floor`) — "parter" =
etaj 0 (aceeași lecție ca la celelalte două conectoare: parterul nu e "etaj
necunoscut"), "demisol" (subsol/semi-îngropat, sub parter) = etaj -1,
"fl_1".."fl_9" = etajul numeric exact, iar "fl_10" ("10 și peste") nu are un
număr exact — rămâne None, la fel ca "ABOVE_TENTH" la storia.ro.

An construcție: param-ul `constructie` e un interval bucket text ("Dupa
2000", "1990 – 2000" etc.), nu un an exact — Comparabila.an rămâne None
(nu putem ghici un an exact dintr-un interval).

Tip tranzacție: anunțurile individuale nu poartă un câmp explicit
vanzare/chirie — categoria (și deci tipul) e determinată de segmentul de URL
folosit la căutare (apartamente-garsoniere-de-vanzare vs. ...-de-inchiriat),
la fel pentru toate anunțurile dintr-un răspuns. De aceea `tip` se
transmite explicit către `_normalize_listing_to_comparabila`, nu se extrage
per-anunț.

Zona: olx.ro nu are un slug de cartier/stradă în path — filtrarea
"zonă" se face printr-un segment de căutare full-text `q-{slug}/` (ex.
`/imobiliare/apartamente-garsoniere-de-vanzare/bucuresti/q-militari/`), care
caută textul în titlu/descriere. Dacă un termen de zonă (ex. o stradă
punctuală precum "Viștei") nu are potriviri, facem fallback determinist la
căutarea pe tot orașul, la fel ca la storia.ro.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
import unicodedata

from bs4 import BeautifulSoup
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_fixed

from acp.connectors.base import ConnectorBase, ConnectorError
from acp.extractie import extrage_incalzire, extrage_parcare, extrage_stare, extrage_structura
from acp.modele import Comparabila, CriteriiCautare

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT_MS = 30_000
MIN_DELAY_SECONDS = 2.0
MAX_RETRIES = 3
SEARCH_TIMEOUT_SECONDS = 30

# Mapare normalizedValue (param `floor`) -> etaj numeric. "parter" = 0 (nu
# None — vezi nota din modul). "demisol" = -1 (sub parter). "fl_10" ("10 și
# peste") nu are un număr exact, deci nu apare aici (fallback = None).
_FLOOR_MAP = {
    "parter": 0,
    "demisol": -1,
    "fl_1": 1,
    "fl_2": 2,
    "fl_3": 3,
    "fl_4": 4,
    "fl_5": 5,
    "fl_6": 6,
    "fl_7": 7,
    "fl_8": 8,
    "fl_9": 9,
}

# Extrage un număr explicit de camere din titlu (ex. "Apartament 2 camere",
# "AP 4 camere decomandat", "1 camera"). Verificat înainte de euristica
# garsonieră/studio, ca să nu suprascriem un număr explicit (ex. titlul
# "Apartament 2 camere Tip Studio ..." conține și "2 camere" și "studio" —
# numărul explicit are prioritate).
_CAMERE_NUMERIC_RE = re.compile(r"(\d+)\s*camer", re.IGNORECASE)


class OlxTransientError(ConnectorError):
    """Eroare tranzitorie (timeout, 5xx) — poate fi reîncercată cu tenacity."""


class OlxConnector(ConnectorBase):
    """Connector pentru olx.ro cu Playwright politicos."""

    def __init__(
        self,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        min_delay_seconds: float = MIN_DELAY_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        super().__init__(name="olx.ro")
        self.base_url = "https://www.olx.ro"
        self.timeout_ms = timeout_ms
        self.min_delay_seconds = min_delay_seconds
        self.max_retries = max_retries
        self._last_request_monotonic: float | None = None

    # ---------- API public ----------

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută pe olx.ro cu Playwright.

        Politicos: min `min_delay_seconds` între navigări succesive,
        user-agent real de desktop.

        Raises:
            ConnectorError: la 403 (blocare anti-bot), timeout persistent
                după retry, sau orice altă eroare neașteptată de
                navigare/parsare. Orchestratorul (Task 7) prinde această
                excepție și continuă cu celelalte surse.
        """
        try:
            return asyncio.run(
                asyncio.wait_for(self._search_async(criterii), timeout=SEARCH_TIMEOUT_SECONDS)
            )
        except ConnectorError:
            raise
        except asyncio.TimeoutError as e:
            # Constrângere din spec: ≤30s per portal, indiferent de câte
            # retry-uri tenacity ar mai fi rămas de făcut la mijlocul lor.
            raise ConnectorError(
                f"olx.ro search a depășit timeout-ul de {SEARCH_TIMEOUT_SECONDS}s",
                connector=self.name,
            ) from e
        except Exception as e:  # plasă de siguranță — nu lăsăm nimic necontrolat să scape
            raise ConnectorError(f"olx.ro search failed: {e}", connector=self.name) from e

    # ---------- orchestrare async ----------

    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Construiește URL-ul, navighează (cu retry, cu fallback de zonă) și parsează."""
        url = self._build_search_url(criterii)
        html = await self._fetch_html_with_retry(url)
        items = self._extract_listing_items(html)

        zona_slug = self._slugify(criterii.zona)
        if not items and zona_slug:
            # Termenul de zonă (căutat full-text via `q-{slug}`) nu are nicio
            # potrivire -> fallback determinist la căutarea pe tot orașul, ca
            # să nu pierdem toate rezultatele din cauza unui termen neacceptat.
            fallback_url = self._build_search_url(criterii, include_zona=False)
            if fallback_url != url:
                html = await self._fetch_html_with_retry(fallback_url)
                items = self._extract_listing_items(html)

        comparabile: list[Comparabila] = []
        for item in items:
            comp = self._normalize_listing_to_comparabila(item, tip=criterii.tip)
            if comp is None:
                continue
            if comp.supr_totala < criterii.supr_min or comp.supr_totala > criterii.supr_max:
                continue
            item_dict = self._as_item_dict(item)
            if item_dict is None or self._extract_camere(item_dict) != criterii.camere:
                continue
            comparabile.append(comp)
        return comparabile

    async def _fetch_html_with_retry(self, url: str) -> str:
        """Navighează cu retry (tenacity) doar pe erori tranzitorii."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_fixed(self.min_delay_seconds),
            retry=retry_if_exception_type(OlxTransientError),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._fetch_html(url)
        raise ConnectorError("olx.ro: eroare necunoscută la fetch", connector=self.name)

    async def _fetch_html(self, url: str) -> str:
        """O singură navigare Playwright, respectând rate limiting-ul politicos."""
        await self._respect_rate_limit()
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                try:
                    context = await browser.new_context(user_agent=USER_AGENT, locale="ro-RO")
                    page = await context.new_page()
                    try:
                        response = await page.goto(
                            url, timeout=self.timeout_ms, wait_until="domcontentloaded"
                        )
                    except PlaywrightTimeoutError as e:
                        raise OlxTransientError(
                            f"olx.ro timeout la navigare: {url}", connector=self.name
                        ) from e

                    if response is not None and response.status == 403:
                        raise ConnectorError(
                            "olx.ro a blocat requestul (403 anti-bot)", connector=self.name
                        )
                    if response is not None and response.status >= 500:
                        raise OlxTransientError(
                            f"olx.ro eroare server ({response.status})", connector=self.name
                        )

                    # Notă: 404 (termen de căutare fără potriviri) NU e tratat
                    # ca eroare aici — pagina se întoarce ca HTML normal, iar
                    # `_extract_listing_items` va găsi 0 anunțuri, ceea ce
                    # declanșează fallback-ul de zonă din `_search_async`.
                    return await page.content()
                finally:
                    await browser.close()
        finally:
            self._last_request_monotonic = time.monotonic()

    async def _respect_rate_limit(self) -> None:
        """Așteaptă până s-a scurs `min_delay_seconds` de la ultima navigare."""
        if self._last_request_monotonic is None:
            return
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.min_delay_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    # ---------- construcție URL ----------

    def _build_search_url(self, criterii: CriteriiCautare, include_zona: bool = True) -> str:
        """
        Construiește URL de căutare pe structura de path a olx.ro:
        /imobiliare/{apartamente-garsoniere-de-vanzare|...-de-inchiriat}/bucuresti/[q-{zona-slug}/]

        Notă: categoria folosită aici (apartamente-garsoniere) nu expune un
        filtru de query pentru număr de camere (vezi nota din modul) — la
        fel ca la storia.ro/imobiliare.ro, filtrarea după suprafață și după
        `criterii.camere` (extras din titlu, via `_extract_camere`) se face
        determinist după parsare, în `_search_async`.
        """
        category_slug = (
            "apartamente-garsoniere-de-vanzare"
            if criterii.tip == "vanzare"
            else "apartamente-garsoniere-de-inchiriat"
        )
        segments = ["imobiliare", category_slug, "bucuresti"]

        if include_zona:
            zona_slug = self._slugify(criterii.zona)
            if zona_slug:
                segments.append(f"q-{zona_slug}")

        return self.base_url + "/" + "/".join(segments) + "/"

    @staticmethod
    def _slugify(text: str) -> str:
        """Transformă text cu diacritice/spații într-un slug de URL (ex: 'Viștei' -> 'vistei')."""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_text = ascii_text.lower().strip()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    # ---------- parsare rezultate (__PRERENDERED_STATE__ JSON) ----------

    _PRERENDERED_STATE_RE = re.compile(
        r"window\.__PRERENDERED_STATE__\s*=\s*(\"(?:[^\"\\]|\\.)*\")\s*;"
    )

    @classmethod
    def _extract_listing_items(cls, html: str) -> list[dict]:
        """
        Extrage lista de anunțuri din ``window.__PRERENDERED_STATE__``.

        Valoarea e un string JSON dublu-encodat (`json.loads` de două ori),
        inserat ca literal string JS într-un ``<script id="olx-init-config">``.
        Defensiv: dacă pagina nu conține JSON-ul așteptat (ex. pagină de
        eroare/captcha, structură schimbată de site), întoarce listă goală
        în loc să propage o excepție — apelantul (`_search_async`) tratează
        asta ca "niciun anunț găsit", nu ca eroare de conector.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            tag = soup.find("script", id="olx-init-config")
            script_text = tag.string if tag is not None else html
            if not script_text:
                return []
            match = cls._PRERENDERED_STATE_RE.search(script_text)
            if match is None:
                return []
            outer = json.loads(match.group(1))
            data = json.loads(outer)
            items = data["listing"]["listing"]["ads"]
            return items if isinstance(items, list) else []
        except (AttributeError, KeyError, TypeError, ValueError):
            return []

    def _normalize_listing_to_comparabila(
        self, listing: dict | str, tip: str = "vanzare"
    ) -> Comparabila | None:
        """
        Convertește un element din ``listing.listing.ads`` (dict JSON, sau un
        string JSON echivalent — util pentru teste izolate) într-un obiect
        Comparabila. Returnează None dacă lipsește suprafața (nu poate
        produce o Comparabila validă) — apelantul sare peste anunț, nu
        prăbușește toată căutarea.

        `tip` (vanzare|chirie) vine din exterior (criterii.tip) — anunțurile
        individuale nu poartă un câmp explicit de tip tranzacție, vezi nota
        din modul.
        """
        item = self._as_item_dict(listing)
        if item is None:
            return None

        params = self._params_by_key(item)

        supr_raw = params.get("m", {}).get("normalizedValue")
        if supr_raw is None:
            return None
        try:
            supr_totala = float(supr_raw)
        except (TypeError, ValueError):
            return None

        pret_eur = None
        price = item.get("price") or {}
        regular_price = price.get("regularPrice") if isinstance(price, dict) else None
        if isinstance(regular_price, dict) and regular_price.get("currencyCode") == "EUR":
            pret_raw = regular_price.get("value")
            if pret_raw not in (None, ""):
                try:
                    pret_eur = float(pret_raw)
                except (TypeError, ValueError):
                    pret_eur = None

        etaj = _FLOOR_MAP.get(params.get("floor", {}).get("normalizedValue"))

        # An de construcție e expus doar ca interval bucket text (ex. "Dupa
        # 2000"), nu ca an exact — vezi nota din modul. Rămâne None.
        an = None

        url = self._extract_url(item)

        dotari = []
        compartimentare = params.get("compartimentare", {}).get("value")
        if compartimentare:
            dotari.append(compartimentare)

        text = " ".join(filter(None, [(item.get("title") or ""), *dotari]))
        stare, stare_incredere = extrage_stare(text)

        return Comparabila(
            sursa=self.name,
            url=url,
            pret_eur=pret_eur,
            supr_totala=supr_totala,
            etaj=etaj,
            an=an,
            dotari=dotari,
            marcaj="activ",
            tip=tip,
            structura=extrage_structura(text),
            incalzire=extrage_incalzire(text),
            stare=stare,
            stare_incredere=stare_incredere,
            parcare_tip=extrage_parcare(text, an),
        )

    @staticmethod
    def _params_by_key(item: dict) -> dict:
        return {
            p.get("key"): p
            for p in (item.get("params") or [])
            if isinstance(p, dict) and p.get("key")
        }

    @staticmethod
    def _extract_camere(item: dict) -> int | None:
        """
        Extrage numărul de camere din titlul anunțului (nu există câmp
        structurat pentru această categorie — vezi nota din modul).

        Un număr explicit ("2 camere", "AP 4 camere") are prioritate; altfel
        "garsonieră"/"studio" se mapează euristic la 1 cameră. Fără nicio
        potrivire -> None (nu se potrivește cu niciun `criterii.camere`).
        """
        title = (item.get("title") or "").lower()
        match = _CAMERE_NUMERIC_RE.search(title)
        if match:
            return int(match.group(1))
        if "garsonier" in title or "studio" in title:
            return 1
        return None

    @staticmethod
    def _as_item_dict(listing: dict | str) -> dict | None:
        if isinstance(listing, dict):
            return listing
        if isinstance(listing, str):
            try:
                parsed = json.loads(listing)
            except ValueError:
                return None
            return parsed if isinstance(parsed, dict) else None
        return None

    def _extract_url(self, item: dict) -> str | None:
        url = item.get("url")
        if url:
            return url
        url_path = item.get("urlPath")
        if url_path:
            return self.base_url + url_path
        return None

    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
