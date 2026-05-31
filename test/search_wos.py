"""Open WoS search results in a real browser via Playwright.

Reads English titles from the local SQLite database, lets the user pick one,
performs the search on WoS, and keeps the browser open for viewing.
"""

import asyncio
import sqlite3
import sys
from playwright.async_api import async_playwright

DB_PATH = "dist-repack/DeepReadingAgent/data/db/app.sqlite"
WOS_URL = "https://webofscience.clarivate.cn/wos/woscc/advanced-search"


def get_english_titles():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, title FROM bib_entries WHERE language='en' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return rows


async def search_wos(title: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        print(f"Opening WoS...")
        await page.goto(WOS_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(6000)

        # Accept cookies
        accept = await page.query_selector("#onetrust-accept-btn-handler")
        if accept and await accept.is_visible():
            await accept.click()
            await page.wait_for_timeout(1000)

        # Set query via JS (Angular needs native setter + events)
        query = f'TI="{title}"'
        await page.evaluate(f"""
            const ta = document.querySelector("textarea[name='search']");
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value'
            ).set;
            setter.call(ta, {repr(query)});
            ta.dispatchEvent(new Event('input', {{ bubbles: true }}));
            ta.dispatchEvent(new Event('change', {{ bubbles: true }}));
        """)
        await page.wait_for_timeout(1000)

        # Click Search button
        search_btns = await page.query_selector_all("button:has-text('Search')")
        for btn in search_btns:
            txt = (await btn.text_content() or "").strip()
            if txt == "Search":
                await btn.click()
                break

        # Wait for results page
        print("Searching...")
        try:
            await page.wait_for_url("**/summary/**", timeout=20000)
            print(f"Results loaded: {page.url}")
        except:
            await page.wait_for_timeout(5000)
            print(f"Current URL: {page.url}")

        print("\nBrowser is open. Close it when done.")
        # Keep browser open until user closes it
        await page.wait_for_event("close", timeout=0)


def main():
    rows = get_english_titles()
    if not rows:
        print("No English entries found.")
        sys.exit(1)

    print(f"\nFound {len(rows)} English entries:\n")
    for i, (_, title) in enumerate(rows, 1):
        short = title[:90] + "..." if len(title) > 90 else title
        print(f"  [{i}] {short}")
    print(f"  [0] Exit")

    while True:
        try:
            choice = int(input(f"\nSelect [0-{len(rows)}]: "))
        except (ValueError, EOFError):
            break
        if choice == 0:
            break
        if 1 <= choice <= len(rows):
            _, title = rows[choice - 1]
            print(f"\nSearching: {title[:80]}...")
            asyncio.run(search_wos(title))
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main()
