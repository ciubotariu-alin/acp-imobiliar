"""Rulare live ACP — Colentina, tinta 45 zile — cu Google Chrome REAL (trece Cloudflare).

imobiliare.ro pune un Cloudflare managed challenge pe /oferta/ + search, pe care
Chromium-ul din Playwright (headless SAU headed) nu-l trece. Chrome real
(channel='chrome') cu profil persistent il trece. Folosim asta pentru imobiliare
(search + subiect + poze candidati). olx merge normal prin conectorul lui.

Reteaua (Chrome real, secvential) e strict separata de motorul PUR de dedup:
descarcam pozele candidatilor sus, apoi confirma_si_dedup primeste un fetch_poze
care doar citeste dictionarul precalculat (fara retea) — exact ca in teste.
"""
import asyncio
import os
from pathlib import Path

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

from acp.connectors.imobiliare import ImobiliareConnector
from acp.connectors.olx import OlxConnector
from acp.connectors.detaliu_fetch import extrage_poze_din_srcs
from acp.modele import Subiect, CriteriiCautare
from acp.filtrare import filtreaza, dedup
from acp.dedup_poze import (
    confirma_si_dedup, potrivire_metadata_subiect, sunt_candidat_duplicat,
)
from acp.imagini import dhash
from acp.analiza import analizeaza
from acp.raport.render import scrie_pdf

PROFILE = os.path.expanduser("~/.acp_pw_profile")
SUBIECT_URL = "https://www.imobiliare.ro/oferta/apartament-de-vanzare-sector-2-colentina-mobilat-2-camere-275238880"

subiect = Subiect(
    pret_eur=108000, supr_totala=59, supr_utila=54, camere=2,
    etaj=2, etaje_total=8, an=1980,
    structura="panou", incalzire="termoficare", stare="bun",
    dotari=["mobilat", "utilat"],
    locatie="Sector 2, Colentina", zona_reala="Colentina",
    tip_vanzator="agentie", url=SUBIECT_URL,
)
criterii = CriteriiCautare(camere=2, supr_min=47, supr_max=71, zona="colentina", raza_km=1.5)


class RealChrome:
    async def __aenter__(self):
        self._p = await async_playwright().start()
        self.ctx = await self._p.chromium.launch_persistent_context(
            PROFILE, channel="chrome", headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1366, "height": 900}, locale="ro-RO",
        )
        self.page = await self.ctx.new_page()
        return self

    async def __aexit__(self, *a):
        await self.ctx.close()
        await self._p.stop()

    async def _clear_challenge(self):
        for _ in range(25):
            await self.page.wait_for_timeout(1000)
            if "moment" not in (await self.page.title()).lower():
                return True
        return False

    async def get_html(self, url, scroll=0):
        await self.page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await self._clear_challenge()
        for _ in range(scroll):
            await self.page.mouse.wheel(0, 4000)
            await self.page.wait_for_timeout(600)
        return await self.page.content()

    async def get_poze(self, url):
        await self.page.goto(url, timeout=60000, wait_until="domcontentloaded")
        await self._clear_challenge()
        srcs = await self.page.eval_on_selector_all(
            "img", "els => els.map(e => e.currentSrc || e.src || e.getAttribute('data-src') || '')")
        return extrage_poze_din_srcs(srcs)

    async def fetch_bytes(self, url):
        try:
            r = await self.ctx.request.get(url, timeout=20000)
            return await r.body() if r.ok else None
        except Exception:
            return None

    async def hashuri(self, url):
        poze = await self.get_poze(url)
        out = []
        for u in poze:
            b = await self.fetch_bytes(u)
            if b:
                h = dhash(b)
                if h is not None:
                    out.append(h)
        return out


def id_din_url(u):
    return u.split("-")[-1] if u else "?"


async def main(olx):
    print("\n" + "=" * 74)
    print(f"LIVE ACP (Chrome real) — Colentina — subiect {subiect.pret_eur:,.0f}€ / "
          f"{subiect.supr_totala:.0f}mp / etaj {subiect.etaj} — tinta 45 zile")
    print("=" * 74 + "\n")
    print(f">> olx.ro: {len(olx)} comparabile")

    async with RealChrome() as rc:
        # --- imobiliare search prin Chrome real ---
        conn = ImobiliareConnector()
        html = await rc.get_html(conn._build_search_url(criterii), scroll=6)
        soup = BeautifulSoup(html, "html.parser")
        imob = []
        for a in soup.select("article[data-listing-id]"):
            c = conn._normalize_listing_to_comparabila(a)
            if c and criterii.supr_min <= c.supr_totala <= criterii.supr_max:
                c.camere = criterii.camere
                imob.append(c)
        print(f">> imobiliare.ro (Chrome real): {len(imob)} comparabile")
        ids = {id_din_url(c.url) for c in imob}
        print(f"   subiect 275238880 in set? {'275238880' in ids} | "
              f"geaman 275736626 in set? {'275736626' in ids}")

        comparabile = imob + olx
        vanzari = [c for c in comparabile if c.tip == "vanzare"]
        survivors = filtreaza(subiect, dedup(vanzari))
        print(f"\n>> {len(comparabile)} brute -> {len(survivors)} dupa filtrare (supr +/-20%, an +/-5)\n")

        # --- candidati care au nevoie de poze (replic laziness-ul motorului) ---
        nevoie = {}
        for c in survivors:
            if potrivire_metadata_subiect(subiect, c):
                nevoie[id(c)] = c
        for i, a in enumerate(survivors):
            for b in survivors[i + 1:]:
                if sunt_candidat_duplicat(a, b):
                    nevoie[id(a)] = a
                    nevoie[id(b)] = b
        candidati = list(nevoie.values())
        print(f">> {len(candidati)} candidati au nevoie de poze (rest: {len(survivors) - len(candidati)} neatinsi)\n")

        # --- poze subiect + candidati, via Chrome real ---
        print(">> Descarc pozele subiectului...")
        subiect_hashes = await rc.hashuri(subiect.url)
        print(f"   subiect: {len(subiect_hashes)} hash-uri\n")

        hash_map = {}
        for c in candidati:
            if not c.url:
                continue
            # olx-urile au poze pe CDN propriu; Chrome real le ia si pe alea
            hs = await rc.hashuri(c.url)
            hash_map[c.url] = hs
            print(f"   {c.sursa:14} id={id_din_url(c.url):>10} {c.pret_eur or 0:>9,.0f}e "
                  f"{c.supr_totala:.0f}mp etaj{c.etaj}: {len(hs)} poze")

    # --- motor PUR (fara retea): fetch_poze citeste dictionarul ---
    def fetch_poze(c):
        return hash_map.get(c.url, [])

    pastrate, dup_elim, subj_elim = confirma_si_dedup(
        survivors, subiect, subiect_hashes, fetch_poze,
        fallback_metadata_subiect=(subiect.url is None),
    )

    print(f"\n>> DEDUP PE POZE:")
    print(f"   SUBIECT eliminat: {len(subj_elim)}")
    for c in subj_elim:
        print(f"       {c.sursa:14} id={id_din_url(c.url):>10} {c.pret_eur or 0:>9,.0f}e {c.supr_totala:.0f}mp")
    print(f"   DUPLICATE cross-agentie eliminate: {len(dup_elim)}")
    for c in dup_elim:
        print(f"       {c.sursa:14} id={id_din_url(c.url):>10} {c.pret_eur or 0:>9,.0f}e {c.supr_totala:.0f}mp")

    elim = {id(c) for c in dup_elim} | {id(c) for c in subj_elim}
    curate = [c for c in comparabile if id(c) not in elim]
    analiza = analizeaza(subiect, curate, tinta_zile=45, surse=sorted({c.sursa for c in curate}))

    print(f"\n>> ANALIZA (tinta 45 zile):")
    print(f"   Comparabile in analiza: {analiza.stat_ajustat.n}")
    print(f"   Mediana ajustata: {analiza.stat_ajustat.mediana:,.0f} €/mp")
    print(f"   Incadrare: {analiza.incadrare} | pozitionare {analiza.pozitionare_pct:+.1f}%")
    print(f"   Pret listare: {analiza.pret_listare[0]:,.0f}–{analiza.pret_listare[1]:,.0f} €")
    print(f"   Pret tranzactie: {analiza.pret_tranzactie[0]:,.0f}–{analiza.pret_tranzactie[1]:,.0f} €")

    Path("output").mkdir(exist_ok=True)
    pdf = "output/ACP_Colentina_45zile_LIVE.pdf"
    scrie_pdf(analiza, pdf, narativ={"tinta_zile": 45, "strategy": "Vanzare tinta in 45 de zile"})
    print(f"\n>> PDF: {pdf}\n")


if __name__ == "__main__":
    # olx foloseste asyncio.run intern -> il rulam ÎNAINTE de bucla async a lui main()
    olx_comps = OlxConnector().search(criterii)
    asyncio.run(main(olx_comps))
