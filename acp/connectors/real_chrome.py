"""Fetch prin Google Chrome REAL (channel='chrome', headed) — trece Cloudflare pe imobiliare.ro.

imobiliare.ro pune un Cloudflare managed challenge pe search/oferta pe care NICIUN browser
headless nu-l trece (testat exhaustiv: Chromium/Chrome/Firefox/WebKit/patchright — toate
primesc soft-block sau rămân în challenge). Doar Chrome real VIZIBIL (headed) ajunge la
conținut. Profil EFEMER (temp dir per apel) evită flag-uirea profilului; la 1 încărcare/
analiză reputația rămâne curată.
"""
from __future__ import annotations

import asyncio
import shutil
import tempfile

from playwright.async_api import async_playwright

_CHALLENGE_MARKER = "moment"  # titlul paginii de challenge: "Doar un moment..." / "Just a moment..."
_disponibil_cache: bool | None = None


def _in_challenge(title: str | None) -> bool:
    """True dacă titlul paginii e încă pagina de challenge Cloudflare."""
    return _CHALLENGE_MARKER in (title or "").lower()


def chrome_disponibil() -> bool:
    """True dacă Google Chrome (channel='chrome') poate fi lansat. Cache-uit per proces."""
    global _disponibil_cache
    if _disponibil_cache is None:
        async def _probe():
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=True)
                await browser.close()
        try:
            asyncio.run(_probe())
            _disponibil_cache = True
        except Exception:
            _disponibil_cache = False
    return _disponibil_cache


async def fetch_html_async(url: str, user_agent: str, timeout_ms: int = 45000,
                           scroll: int = 6, challenge_sec: int = 15) -> str:
    """Deschide `url` cu Chrome real (headed, profil efemer), trece challenge-ul și
    întoarce HTML-ul. Ridică RuntimeError dacă challenge-ul nu se rezolvă în `challenge_sec`."""
    profil = tempfile.mkdtemp(prefix="acp_chrome_")
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(
            profil,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1366, "height": 900},
            locale="ro-RO",
            user_agent=user_agent,
        )
        try:
            page = await ctx.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            trecut = False
            for _ in range(challenge_sec):
                await page.wait_for_timeout(1000)
                if not _in_challenge(await page.title()):
                    trecut = True
                    break
            if not trecut:
                raise RuntimeError("Cloudflare challenge nerezolvat (profil/IP flag-uit)")
            await page.wait_for_timeout(3000)
            for _ in range(scroll):
                await page.mouse.wheel(0, 4000)
                await page.wait_for_timeout(600)
            return await page.content()
        finally:
            await ctx.close()
            shutil.rmtree(profil, ignore_errors=True)


def fetch_html(url: str, user_agent: str, timeout_ms: int = 45000,
               scroll: int = 6, challenge_sec: int = 15) -> str:
    """Wrapper sincron (pentru scripturi ad-hoc). În connector se folosește fetch_html_async."""
    return asyncio.run(fetch_html_async(url, user_agent, timeout_ms, scroll, challenge_sec))
