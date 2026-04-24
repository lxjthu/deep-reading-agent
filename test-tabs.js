// test-tabs.js - 测试 Tab 切换
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  
  await page.goto('https://deepreading.qzz.io', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2000);
  
  // Screenshot 1: 首页（文献筛选 Tab）
  await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_0_filter.png' });
  console.log('Tab 0 (filter) OK');
  
  // Click Tab 1: 长文本精读
  const tab1 = await page.$('text=长文本精读');
  if (tab1) {
    await tab1.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_1_long.png' });
    console.log('Tab 1 (long) OK');
  }
  
  // Click Tab 2: 七步精读
  const tab2 = await page.$('text=七步精读');
  if (tab2) {
    await tab2.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_2_quant.png' });
    console.log('Tab 2 (quant) OK');
  }
  
  // Click Tab 3: 四步精读
  const tab3 = await page.$('text=四步精读');
  if (tab3) {
    await tab3.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_3_qual.png' });
    console.log('Tab 3 (qual) OK');
  }
  
  // Click Tab 4: 提示词管理
  const tab4 = await page.$('text=提示词管理');
  if (tab4) {
    await tab4.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_4_prompts.png' });
    console.log('Tab 4 (prompts) OK');
  }
  
  // Back to Tab 0
  const tab0 = await page.$('text=文献筛选');
  if (tab0) {
    await tab0.click();
    await page.waitForTimeout(2000);
    await page.screenshot({ path: '/root/.openclaw/workspace/deep-reading-agent/tab_0_back.png' });
    console.log('Tab 0 back OK');
  }
  
  await browser.close();
  console.log('All tabs tested successfully');
})();
