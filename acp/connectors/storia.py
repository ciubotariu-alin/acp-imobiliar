"""Connector pentru storia.ro (Playwright politicos).

Spre deosebire de imobiliare.ro, storia.ro (aplicație Next.js server-side
rendered) nu are protecție Cloudflare agresivă — un `curl` simplu cu un
user-agent de desktop primește 200 direct. Păstrăm totuși Playwright pentru
consistență arhitecturală cu ImobiliareConnector (politețe, retry, timeout
dur per navigare) și ca plasă de siguranță dacă site-ul adaugă protecție
anti-bot pe viitor.

Parsing: paginile de rezultate storia.ro NU expun anunțurile ca atribute
``data-*`` pe elemente HTML (markup-ul e CSS-in-JS, foarte greu de parsat
robust din text vizibil). În schimb, Next.js inserează un
``<script id="__NEXT_DATA__" type="application/json">`` cu întreg
state-ul paginii, inclusiv ``props.pageProps.data.searchAds.items`` — o
listă de obiecte JSON structurate (preț, suprafață, etaj, cameră, tip
tranzacție etc.) per anunț. Extragem acest JSON și normalizăm fiecare
element la ``Comparabila``, în loc să parsăm text/CSS.

Etajul e expus ca enum text (``GROUND``, ``FIRST``, ..., ``TENTH``,
``ABOVE_TENTH``) — ``GROUND`` (parter) se mapează la ``etaj=0`` (nu None,
aceeași lecție învățată la imobiliare.ro: parterul nu e "etaj necunoscut").
``ABOVE_TENTH`` nu are un număr exact, deci rămâne None.

Zona: taxonomia de locații a storia.ro e pe sector/cartier, nu pe stradă —
un zona liber precum „Viștei" nu are de regulă un slug de locație valid și
produce 404. De aceea, dacă URL-ul cu segmentul de zonă nu întoarce niciun
anunț parsabil, facem fallback determinist la căutarea la nivel de oraș
(București, fără zonă), ca să nu pierdem toate rezultatele din cauza unui
slug de zonă neacceptat.
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

# Mapare enum textual storia.ro -> etaj numeric. GROUND (parter) = 0, la fel
# ca la imobiliare.ro (vezi nota din modul). ABOVE_TENTH nu are un număr
# exact expus, deci nu poate fi mapat (None = necunoscut).
_FLOOR_MAP = {
    "GROUND": 0,
    "FIRST": 1,
    "SECOND": 2,
    "THIRD": 3,
    "FOURTH": 4,
    "FIFTH": 5,
    "SIXTH": 6,
    "SEVENTH": 7,
    "EIGHTH": 8,
    "NINTH": 9,
    "TENTH": 10,
}

# Mapare enum textual storia.ro -> număr de camere. Câmpul JSON `roomsNumber`
# (ex. "ONE", "TWO", "THREE", ...) nu poate fi filtrat fiabil din URL (vezi
# nota din `_build_search_url`), așa că filtrarea se face determinist după
# parsare, în `_search_async` — la fel ca la `supr_min`/`supr_max`.
_ROOMS_MAP = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
    "NINE": 9,
    "TEN": 10,
}


class StoriaTransientError(ConnectorError):
    """Eroare tranzitorie (timeout, 5xx) — poate fi reîncercată cu tenacity."""


class StoriaConnector(ConnectorBase):
    """Connector pentru storia.ro cu Playwright politicos."""

    def __init__(
        self,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        min_delay_seconds: float = MIN_DELAY_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        super().__init__(name="storia.ro")
        self.base_url = "https://www.storia.ro"
        self.timeout_ms = timeout_ms
        self.min_delay_seconds = min_delay_seconds
        self.max_retries = max_retries
        self._last_request_monotonic: float | None = None

    # ---------- API public ----------

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută pe storia.ro cu Playwright.

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
                f"storia.ro search a depășit timeout-ul de {SEARCH_TIMEOUT_SECONDS}s",
                connector=self.name,
            ) from e
        except Exception as e:  # plasă de siguranță — nu lăsăm nimic necontrolat să scape
            raise ConnectorError(f"storia.ro search failed: {e}", connector=self.name) from e

    # ---------- orchestrare async ----------

    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Construiește URL-ul, navighează (cu retry, cu fallback de zonă) și parsează."""
        url = self._build_search_url(criterii)
        html = await self._fetch_html_with_retry(url)
        items = self._extract_listing_items(html)

        zona_slug = self._slugify(criterii.zona)
        if not items and zona_slug:
            # Zona (ex. o stradă) nu corespunde taxonomiei sector/cartier a
            # storia.ro -> fallback determinist la căutarea pe tot orașul,
            # ca să nu întoarcem o listă goală doar din cauza unui slug
            # de locație neacceptat.
            fallback_url = self._build_search_url(criterii, include_zona=False)
            if fallback_url != url:
                html = await self._fetch_html_with_retry(fallback_url)
                items = self._extract_listing_items(html)

        comparabile: list[Comparabila] = []
        for item in items:
            comp = self._normalize_listing_to_comparabila(item)
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
            retry=retry_if_exception_type(StoriaTransientError),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._fetch_html(url)
        raise ConnectorError("storia.ro: eroare necunoscută la fetch", connector=self.name)

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
                        raise StoriaTransientError(
                            f"storia.ro timeout la navigare: {url}", connector=self.name
                        ) from e

                    if response is not None and response.status == 403:
                        raise ConnectorError(
                            "storia.ro a blocat requestul (403 anti-bot)", connector=self.name
                        )
                    if response is not None and response.status >= 500:
                        raise StoriaTransientError(
                            f"storia.ro eroare server ({response.status})", connector=self.name
                        )

                    # Notă: 404 (zonă/locație inexistentă în taxonomia storia.ro)
                    # NU e tratat ca eroare aici — pagina 404 se întoarce ca HTML
                    # normal, iar `_extract_listing_items` va găsi 0 anunțuri,
                    # ceea ce declanșează fallback-ul de zonă din `_search_async`.
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
        Construiește URL de căutare pe structura de path a storia.ro:
        /ro/rezultate/{vanzare|inchiriere}/apartament/bucuresti[/{zona-slug}]

        Notă: nu am găsit un parametru de query fiabil pentru filtrul de
        număr de camere (parametrii încercați empiric — ``roomsNumber``,
        ``roomsNumber[list][0]``, ``roomsNumber[0]`` — sunt ignorați silențios
        de server). La fel ca la imobiliare.ro, filtrarea după suprafață
        (supr_min/supr_max) și după număr de camere (`criterii.camere`, via
        `_extract_camere`/`roomsNumber`) se face determinist după parsare,
        în `_search_async`, indiferent de comportamentul filtrelor din URL.
        """
        tip_segment = "vanzare" if criterii.tip == "vanzare" else "inchiriere"
        segments = ["ro", "rezultate", tip_segment, "apartament", "bucuresti"]

        if include_zona:
            zona_slug = self._slugify(criterii.zona)
            if zona_slug:
                segments.append(zona_slug)

        return self.base_url + "/" + "/".join(segments)

    @staticmethod
    def _slugify(text: str) -> str:
        """Transformă text cu diacritice/spații într-un slug de URL (ex: 'Viștei' -> 'vistei')."""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_text = ascii_text.lower().strip()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    # ---------- parsare rezultate (__NEXT_DATA__ JSON) ----------

    @staticmethod
    def _extract_listing_items(html: str) -> list[dict]:
        """
        Extrage lista de anunțuri din ``<script id="__NEXT_DATA__">``.

        Defensiv: dacă pagina nu conține JSON-ul așteptat (ex. pagină de
        eroare, structură schimbată de site), întoarce listă goală în loc
        să propage o excepție — apelantul (`_search_async`) tratează asta
        ca "niciun anunț găsit", nu ca eroare de conector.
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            tag = soup.find("script", id="__NEXT_DATA__")
            if tag is None or not tag.string:
                return []
            data = json.loads(tag.string)
            items = data["props"]["pageProps"]["data"]["searchAds"]["items"]
            return items if isinstance(items, list) else []
        except (AttributeError, KeyError, TypeError, ValueError):
            return []

    def _normalize_listing_to_comparabila(self, listing: dict | str) -> Comparabila | None:
        """
        Convertește un element din ``searchAds.items`` (dict JSON, sau un
        string JSON echivalent — util pentru teste izolate) într-un obiect
        Comparabila. Returnează None dacă lipsește suprafața (nu poate
        produce o Comparabila validă) — apelantul sare peste anunț, nu
        prăbușește toată căutarea.
        """
        item = self._as_item_dict(listing)
        if item is None:
            return None

        supr_raw = item.get("areaInSquareMeters")
        if supr_raw is None:
            return None
        try:
            supr_totala = float(supr_raw)
        except (TypeError, ValueError):
            return None

        pret_eur = None
        total_price = item.get("totalPrice") or {}
        pret_raw = total_price.get("value") if isinstance(total_price, dict) else None
        if pret_raw not in (None, ""):
            try:
                pret_eur = float(pret_raw)
            except (TypeError, ValueError):
                pret_eur = None

        etaj = _FLOOR_MAP.get(item.get("floorNumber"))

        # An de construcție nu e expus în JSON-ul de căutare al storia.ro
        # (spre deosebire de imobiliare.ro, care are `data-year`, chiar dacă
        # deseori 0/necunoscut). Rămâne None — Comparabila.an e opțional.
        an = None

        transaction = (item.get("transaction") or "").upper()
        # Vocabularul intern (Comparabila.tip) e "vanzare" | "chirie" — vezi acp.modele.
        tip = "chirie" if transaction == "RENT" else "vanzare"

        url = self._extract_url(item)

        dotari = [
            tag.get("value")
            for tag in (item.get("tags") or [])
            if isinstance(tag, dict) and tag.get("value")
        ]

        slug_text = (item.get("slug") or "").replace("-", " ")
        text = " ".join([slug_text, *dotari])
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
    def _extract_camere(item: dict) -> int | None:
        """
        Mapează enum-ul textual `roomsNumber` (ex. "ONE", "TWO", "THREE", ...)
        la un număr întreg de camere, folosind `_ROOMS_MAP`. Valoare
        necunoscută/lipsă -> None (nu se potrivește cu niciun `criterii.camere`).
        """
        return _ROOMS_MAP.get(item.get("roomsNumber"))

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
        slug = item.get("slug")
        if not slug:
            return None
        return f"{self.base_url}/ro/oferta/{slug}"

    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
