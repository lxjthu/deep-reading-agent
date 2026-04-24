import asyncio
from playwright.async_api import async_playwright

async def test_tabs():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        
        await page.goto("https://deepreading.qzz.io", wait_until="networkidle")
        await page.wait_for_timeout(2000)
        
        # Tab 0: 文献筛选 (already active)
        await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_0_filter.png")
        print("Tab 0 (filter) OK")
        
        # Tab 1: 长文本精读
        tab1 = await page.get_by_text("长文本精读").first
        if tab1:
            await tab1.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_1_long.png")
            print("Tab 1 (long) OK")
        
        # Tab 2: 七步精读
        tab2 = await page.get_by_text("七步精读").first
        if tab2:
            await tab2.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_2_quant.png")
            print("Tab 2 (quant) OK")
        
        # Tab 3: 四步精读
        tab3 = await page.get_by_text("四步精读").first
        if tab3:
            await tab3.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_3_qual.png")
            print("Tab 3 (qual) OK")
        
        # Tab 4: 提示词管理
        tab4 = await page.get_by_text("提示词管理").first
        if tab4:
            await tab4.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_4_prompts.png")
            print("Tab 4 (prompts) OK")
        
        # Back to Tab 0
        tab0 = await page.get_by_text("文献筛选").first
        if tab0:
            await tab0.click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path="/root/.openclaw/workspace/deep-reading-agent/tab_0_back.png")
            print("Tab 0 back OK")
        
        await browser.close()
        print("All tabs tested successfully")

asyncio.run(test_tabs())
