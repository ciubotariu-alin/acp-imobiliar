"""Fetch text + URL-uri poze dintr-o pagină de detaliu (Playwright).

Izolat de motorul pur acp/detalii.py și de dedup-ul de poze. O singură navigare
întoarce atât textul body-ului, cât și URL-urile de galerie (evită două page-load).
"""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright


def extrage_poze_din_srcs(srcs: list[str], max_poze: int = 4) -> list[str]:
    """Filtrează sursele `<img>` la primele `max_poze` URL-uri de galerie.

    Exclude thumbnail-urile (`gallery-thumb`/`thumb`), sursele non-http
    (`data:`, căi relative) și `.svg` (logo-uri/iconițe). Elimină duplicatele
    păstrând ordinea.
    """
    rezultat: list[str] = []
    for s in srcs:
        if not s or not s.startswith("http"):
            continue
        low = s.lower()
        if "thumb" in low or low.endswith(".svg"):
            continue
        if s in rezultat:
            continue
        rezultat.append(s)
        if len(rezultat) >= max_poze:
            break
    return rezultat


async def _extrage_pagina(url: str, user_agent: str, timeout_ms: int) -> tuple[str, list[str]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=user_agent, locale="ro-RO")
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # lasă Cloudflare/JS să se așeze
            text = await page.inner_text("body")
            srcs = await page.eval_on_selector_all(
                "img",
                "els => els.map(e => e.currentSrc || e.src || e.getAttribute('data-src') || '')",
            )
            return text, extrage_poze_din_srcs(srcs)
        finally:
            await browser.close()


def fetch_detaliu(url: str, user_agent: str, timeout_ms: int = 30000,
                  retries: int = 1) -> tuple[str | None, list[str]]:
    """Deschide pagina de detaliu și întoarce (text_body, poze_urls), sau (None, []) la eșec."""
    for tentativa in range(retries + 1):
        try:
            return asyncio.run(_extrage_pagina(url, user_agent, timeout_ms))
        except Exception:
            if tentativa >= retries:
                return None, []
    return None, []


def fetch_detaliu_text(url: str, user_agent: str, timeout_ms: int = 30000,
                       retries: int = 1) -> str | None:
    """Wrapper compatibil: întoarce doar textul body-ului (sau None la eșec)."""
    return fetch_detaliu(url, user_agent, timeout_ms, retries)[0]
