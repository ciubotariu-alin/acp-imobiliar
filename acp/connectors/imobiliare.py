"""Connector pentru imobiliare.ro (Playwright politicos).

imobiliare.ro are protecție anti-bot puternică (Cloudflare). Strategia:
- browser Chromium headless real (nu httpx/requests — challenge-ul JS blochează cereri simple)
- user-agent real de desktop, locale ro-RO
- rate limiting: minim `min_delay_seconds` între navigări succesive (implicit 2s)
- retry cu tenacity doar pe erori tranzitorii (timeout, 5xx) — nu pe 403 (blocare fermă)
- timeout dur per navigare — dacă expiră, ridicăm ConnectorError ca orchestratorul
  să poată continua cu celelalte surse (vezi acp.connectors.base.ConnectorError)

Parsing: fiecare rezultat de căutare e un ``<article data-listing-id="...">`` cu
atribute ``data-*`` (preț, suprafață, an, oraș, zonă, status) direct pe element —
mult mai robust decât parsarea textului vizibil. Etajul nu e expus ca atribut,
așa că e extras din cele 4 span-uri ``.listing-attribute`` (camere/suprafață/etaj/an).
"""
from __future__ import annotations

import asyncio
import re
import time
import unicodedata

from bs4 import BeautifulSoup
from bs4.element import Tag
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

_FLOOR_RE = re.compile(r"etaj\s+(\d+)", re.IGNORECASE)
_FLOOR_PARTER_RE = re.compile(r"\bparter\b", re.IGNORECASE)


class ImobiliareTransientError(ConnectorError):
    """Eroare tranzitorie (timeout, 5xx) — poate fi reîncercată cu tenacity."""


class ImobiliareConnector(ConnectorBase):
    """Connector pentru imobiliare.ro cu Playwright politicos."""

    def __init__(
        self,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        min_delay_seconds: float = MIN_DELAY_SECONDS,
        max_retries: int = MAX_RETRIES,
    ):
        super().__init__(name="imobiliare.ro")
        self.base_url = "https://www.imobiliare.ro"
        self.timeout_ms = timeout_ms
        self.min_delay_seconds = min_delay_seconds
        self.max_retries = max_retries
        self._last_request_monotonic: float | None = None

    # ---------- API public ----------

    def search(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """
        Caută pe imobiliare.ro cu Playwright.

        Politicos: min `min_delay_seconds` între requeste, user-agent real.

        Raises:
            ConnectorError: la 403 (blocare anti-bot), timeout persistent după
                retry, sau orice altă eroare neașteptată de navigare/parsare.
                Orchestratorul (Task 7) prinde această excepție și continuă
                cu celelalte surse.
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
                f"imobiliare.ro search a depășit timeout-ul de {SEARCH_TIMEOUT_SECONDS}s",
                connector=self.name,
            ) from e
        except Exception as e:  # plasă de siguranță — nu lăsăm nimic necontrolat să scape
            raise ConnectorError(f"imobiliare.ro search failed: {e}", connector=self.name) from e

    # ---------- orchestrare async ----------

    async def _search_async(self, criterii: CriteriiCautare) -> list[Comparabila]:
        """Construiește URL-ul, navighează (cu retry) și parsează rezultatele."""
        url = self._build_search_url(criterii)
        html = await self._fetch_html_with_retry(url)

        soup = BeautifulSoup(html, "html.parser")
        listing_elems = soup.select("article[data-listing-id]")

        comparabile: list[Comparabila] = []
        for elem in listing_elems:
            comp = self._normalize_listing_to_comparabila(elem)
            if comp is None:
                continue
            if comp.supr_totala < criterii.supr_min or comp.supr_totala > criterii.supr_max:
                continue
            comparabile.append(comp)
        return comparabile

    async def _fetch_html_with_retry(self, url: str) -> str:
        """Navighează cu retry (tenacity) doar pe erori tranzitorii."""
        retrying = AsyncRetrying(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_fixed(self.min_delay_seconds),
            retry=retry_if_exception_type(ImobiliareTransientError),
            reraise=True,
        )
        async for attempt in retrying:
            with attempt:
                return await self._fetch_html(url)
        raise ConnectorError("imobiliare.ro: eroare necunoscută la fetch", connector=self.name)

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
                        raise ImobiliareTransientError(
                            f"imobiliare.ro timeout la navigare: {url}", connector=self.name
                        ) from e

                    if response is not None and response.status == 403:
                        raise ConnectorError(
                            "imobiliare.ro a blocat requestul (403 anti-bot)", connector=self.name
                        )
                    if response is not None and response.status >= 500:
                        raise ImobiliareTransientError(
                            f"imobiliare.ro eroare server ({response.status})", connector=self.name
                        )

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

    def _build_search_url(self, criterii: CriteriiCautare) -> str:
        """
        Construiește URL de căutare pe structura de path a imobiliare.ro:
        /{tip}-apartamente/bucuresti/{zona-slug}/{N}-camere

        Notă: filtrul de suprafață (supr_min/supr_max) nu are un parametru de
        query fiabil descoperit pe site (formularul de filtre e populat client-side
        prin JS, cheia internă e "usable_surface" dar nu acceptă query string simplu).
        De aceea filtrarea după suprafață se face determinist după parsare,
        în `_search_async`, garantând corectitudinea indiferent de comportamentul
        filtrului din URL.
        """
        tip_segment = "vanzare-apartamente" if criterii.tip == "vanzare" else "inchiriere-apartamente"
        zona_slug = self._slugify(criterii.zona)

        segments = [tip_segment, "bucuresti"]
        if zona_slug:
            segments.append(zona_slug)
        segments.append(f"{criterii.camere}-camere")

        return self.base_url + "/" + "/".join(segments)

    @staticmethod
    def _slugify(text: str) -> str:
        """Transformă text cu diacritice/spații într-un slug de URL (ex: 'Viștei' -> 'vistei')."""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
        ascii_text = ascii_text.lower().strip()
        ascii_text = re.sub(r"[^a-z0-9]+", "-", ascii_text)
        return ascii_text.strip("-")

    # ---------- parsare listare ----------

    def _normalize_listing_to_comparabila(self, listing_html: str | Tag) -> Comparabila | None:
        """
        Convertește un element ``<article data-listing-id>`` (sau un fragment HTML
        echivalent) într-un obiect Comparabila.

        Acceptă fie un ``bs4.Tag`` (calea uzuală din `_search_async`), fie un string
        HTML (util pentru teste izolate). Returnează None dacă elementul nu conține
        date minime utilizabile (suprafață) — apelantul sare peste anunț fără să
        eșueze întreaga căutare.
        """
        elem = self._as_article_tag(listing_html)
        if elem is None:
            return None

        supr_raw = elem.get("data-surface")
        if not supr_raw:
            return None
        try:
            supr_totala = float(supr_raw)
        except (TypeError, ValueError):
            return None

        pret_raw = elem.get("data-item-price")
        pret_eur = None
        if pret_raw not in (None, "", "0"):
            try:
                pret_eur = float(pret_raw)
            except (TypeError, ValueError):
                pret_eur = None

        an_raw = elem.get("data-year")
        an = None
        if an_raw and an_raw != "0":
            try:
                an = int(float(an_raw))
            except (TypeError, ValueError):
                an = None

        etaj = self._extract_etaj(elem)

        status = (elem.get("data-status") or "").lower()
        # Vocabularul intern (Comparabila.tip) e "vanzare" | "chirie" — vezi acp.modele.
        tip = "chirie" if "rent" in status else "vanzare"

        availability = (elem.get("data-availability") or "available").lower()
        marcaj = "activ" if availability in ("available", "") else "listat"

        url = self._extract_url(elem)

        text = elem.get_text(" ", strip=True) if hasattr(elem, "get_text") else ""
        stare, stare_incredere = extrage_stare(text)

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

    @staticmethod
    def _as_article_tag(listing_html: str | Tag) -> Tag | None:
        if isinstance(listing_html, Tag):
            return listing_html
        if isinstance(listing_html, str):
            soup = BeautifulSoup(listing_html, "html.parser")
            article = soup.find("article")
            if article is not None:
                return article
            return soup.find() if soup.contents else None
        return None

    @staticmethod
    def _extract_etaj(elem: Tag) -> int | None:
        for span in elem.select(".listing-attribute"):
            text = span.get_text(strip=True)
            m = _FLOOR_RE.search(text)
            if m:
                return int(m.group(1))
            if _FLOOR_PARTER_RE.search(text):
                return 0
        return None

    def _extract_url(self, elem: Tag) -> str | None:
        link = elem.select_one("a[href^='/oferta/']")
        if link is None:
            link = elem.select_one("a[href]")
        if link is None:
            return None
        href = link.get("href")
        if not href:
            return None
        return href if href.startswith("http") else self.base_url + href

    def fetch_detaliu_text(self, url: str) -> str | None:
        from acp.connectors import detaliu_fetch
        return detaliu_fetch.fetch_detaliu_text(url, USER_AGENT)
