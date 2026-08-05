"""Fetch textul unei pagini de detaliu (Playwright). Izolat de motorul pur acp/detalii.py."""
from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright


async def _extrage_text_pagina(url: str, user_agent: str, timeout_ms: int) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(user_agent=user_agent, locale="ro-RO")
            page = await context.new_page()
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)  # lasă Cloudflare/JS să se așeze
            return await page.inner_text("body")
        finally:
            await browser.close()


def fetch_detaliu_text(url: str, user_agent: str, timeout_ms: int = 30000,
                       retries: int = 1) -> str | None:
    """Deschide pagina de detaliu și întoarce textul body-ului, sau None la eșec."""
    for tentativa in range(retries + 1):
        try:
            return asyncio.run(_extrage_text_pagina(url, user_agent, timeout_ms))
        except Exception:
            if tentativa >= retries:
                return None
    return None
