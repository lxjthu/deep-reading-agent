"""WoS (Web of Science) search via Playwright browser automation."""
from __future__ import annotations

import asyncio
import logging

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

WOS_ADVANCED_SEARCH_URL = "https://webofscience.clarivate.cn/wos/woscc/advanced-search"

# Limit concurrent Playwright instances to avoid OOM on the server.
_semaphore = asyncio.Semaphore(3)


async def search_wos_by_title(title: str) -> str:
    """Open WoS advanced search, fill the title query, click Search, return result URL.

    Uses a semaphore to cap concurrent browser instances at 3.
    """
    async with _semaphore:
        return await _do_search(title)


async def _do_search(title: str) -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            logger.info("WoS search: navigating to advanced search page")
            await page.goto(WOS_ADVANCED_SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(5000)

            # Dismiss OneTrust cookie banner if present.
            accept_btn = await page.query_selector("#onetrust-accept-btn-handler")
            if accept_btn and await accept_btn.is_visible():
                await accept_btn.click()
                await page.wait_for_timeout(1000)

            # Set the search textarea value via native setter (Angular reactive forms).
            query = f'TI="{title}"'
            await page.evaluate(
                """
                (query) => {
                    const ta = document.querySelector("textarea[name='search']");
                    if (!ta) return;
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLTextAreaElement.prototype, 'value'
                    ).set;
                    setter.call(ta, query);
                    ta.dispatchEvent(new Event('input', { bubbles: true }));
                    ta.dispatchEvent(new Event('change', { bubbles: true }));
                }
                """,
                query,
            )
            await page.wait_for_timeout(1000)

            # Click the "Search" button.
            search_btns = await page.query_selector_all("button:has-text('Search')")
            for btn in search_btns:
                txt = (await btn.text_content() or "").strip()
                if txt == "Search":
                    await btn.click()
                    break

            # Wait for navigation to the results summary page.
            try:
                await page.wait_for_url("**/summary/**", timeout=20000)
            except Exception:
                # Even if the URL pattern doesn't match, give the page a moment
                # and return whatever URL we ended up on.
                await page.wait_for_timeout(5000)

            result_url = page.url
            logger.info("WoS search: result URL = %s", result_url)
            return result_url
        finally:
            await browser.close()
