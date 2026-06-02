# WoS 搜索按钮集成规划

> 状态：**已实施，待部署验证**
> 创建时间：2026-05-31
> 实施时间：2026-05-31
> 前置条件：`pip install playwright && playwright install chromium`

## 一、需求

在"我的文献库"详情页，"知网搜索"按钮旁边增加一个"WOS搜索"按钮，点击后在浏览器中展示该论文对应的 WoS 搜索结果页。

## 二、现状分析

### 2.1 知网按钮的实现方式（纯前端）

`frontend/src/LibraryTab.tsx:320-327`：

```javascript
function buildCnkiTitleSearchUrl(title: string) {
  const params = new URLSearchParams({ kw: query, korder: 'TI' })
  return `https://kns.cnki.net/kns8s/defaultresult/index?${params.toString()}`
}
// 调用：window.open(url, '_blank')
```

CNKI 能这样做是因为其搜索结果页是**服务端渲染**，URL 参数直接决定页面内容。

### 2.2 WoS 的核心障碍

WoS 是 Angular SPA（单页应用），搜索流程：

1. 打开 `/wos/woscc/advanced-search` → JS 加载
2. 用户输入查询 → 点击 Search
3. 前端发请求 → 服务端生成 session → 跳转到 `/wos/woscc/summary/{动态session-id}/relevance/1`

**结果页 URL 中的 session-id 是点击 Search 后服务端动态生成的，无法预拼。**

### 2.3 实测验证过的 URL 格式

| URL | 效果 |
|-----|------|
| `/advanced-search?query=TI%3D%22title%22` | 只预填表单，不执行搜索，用户需手动点 Search |
| `/results?query=...` | 页面不存在（SPA 路由，非服务端路由） |
| `/basic-search` + 手动输入回车 | 能搜，但 URL 仍是动态生成 |

### 2.4 结论

**必须用 Playwright（或类似浏览器自动化工具）**，无法纯前端实现。

- `window.open(url)` 只能打开预填查询的高级搜索页，用户还需手动点 Search
- 无法通过 URL 参数直接跳到结果页
- 无法在新标签页里注入 JS 自动点击（跨域限制）

## 三、技术方案

### 3.1 架构

```
用户点击"WOS搜索"
  → 前端 POST /api/library/entries/{id}/wos-search
  → 后端 Playwright 打开 WoS → 填查询 → 点 Search → 拿到结果页 URL
  → 后端返回 { url: "https://.../summary/{session-id}/relevance/1" }
  → 前端 window.open(url) 在用户浏览器打开结果页
  → 后端关闭 Playwright 浏览器实例
```

### 3.2 后端改动

**文件：`backend/routers/library.py`**

新增端点：

```python
@router.post("/entries/{entry_id}/wos-search")
async def wos_search(entry_id: str, db: AsyncSession = Depends(get_db)):
    """用 Playwright 在 WoS 搜索该文献标题，返回结果页 URL。"""
    entry = await db.get(BibEntry, entry_id)
    if not entry:
        raise HTTPException(404, "文献不存在")
    
    url = await search_wos_by_title(entry.title)
    return {"url": url}
```

**新建文件：`backend/services/wos_search.py`**

```python
import asyncio
from playwright.async_api import async_playwright

WOS_URL = "https://webofscience.clarivate.cn/wos/woscc/advanced-search"

async def search_wos_by_title(title: str) -> str:
    """用 Playwright 在 WoS 搜索标题，返回结果页 URL。"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        await page.goto(WOS_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(5000)
        
        # 接受 Cookie 弹窗
        accept = await page.query_selector("#onetrust-accept-btn-handler")
        if accept and await accept.is_visible():
            await accept.click()
            await page.wait_for_timeout(1000)
        
        # 通过 JS 设置查询值（Angular 需要 native setter + 事件）
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
        
        # 点击 Search 按钮
        search_btns = await page.query_selector_all("button:has-text('Search')")
        for btn in search_btns:
            txt = (await btn.text_content() or "").strip()
            if txt == "Search":
                await btn.click()
                break
        
        # 等待跳转到结果页
        try:
            await page.wait_for_url("**/summary/**", timeout=20000)
        except:
            await page.wait_for_timeout(5000)
        
        result_url = page.url
        await browser.close()
        return result_url
```

### 3.3 前端改动

**文件：`frontend/src/LibraryTab.tsx`**

1. 新增状态：

```typescript
const [wosSearching, setWosSearching] = useState(false)
```

2. 新增处理函数：

```typescript
async function handleWosSearch() {
  if (!detail || wosSearching) return
  setWosSearching(true)
  try {
    const response = await fetch(`/api/library/entries/${encodeURIComponent(detail.id)}/wos-search`, {
      method: 'POST',
    })
    const data = await parseJsonOrThrow<{ url: string }>(response)
    window.open(data.url, '_blank', 'noopener,noreferrer')
  } catch (error: unknown) {
    alert(`WOS 搜索失败：${error instanceof Error ? error.message : String(error)}`)
  } finally {
    setWosSearching(false)
  }
}
```

3. 在"知网搜索"按钮旁边添加按钮（约第 1807 行）：

```tsx
<button
  type="button"
  disabled={wosSearching}
  className="rounded-lg border border-blue-200 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
  onClick={() => void handleWosSearch()}
>
  {wosSearching ? '搜索中...' : 'WOS 搜索'}
</button>
```

### 3.4 依赖安装

```bash
pip install playwright
playwright install chromium
```

需更新 `requirements.txt`。

## 四、注意事项

### 4.1 Cookie 弹窗

WoS 首次访问会弹出 OneTrust Cookie 同意弹窗，需用 Playwright 点击接受按钮：
```python
accept = await page.query_selector("#onetrust-accept-btn-handler")
```

### 4.2 Angular 表单值设置

直接 `fill()` 不会触发 Angular 的表单验证，必须用 native setter + 手动 dispatch 事件：
```python
await page.evaluate("""
    const ta = document.querySelector("textarea[name='search']");
    const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype, 'value'
    ).set;
    setter.call(ta, query);
    ta.dispatchEvent(new Event('input', { bubbles: true }));
    ta.dispatchEvent(new Event('change', { bubbles: true }));
""")
```

### 4.3 超时处理

- WoS 页面加载较慢，`goto` 需设 `timeout=60000`，`wait_until="domcontentloaded"`
- 搜索后等待跳转设 `timeout=20000`
- 整个端点应设合理超时（如 90 秒）

### 4.4 并发控制

如果多个用户同时点击，会产生多个 Playwright 实例。建议：
- 用 `asyncio.Semaphore` 限制并发数（如最多 3 个）
- 或用单例浏览器 + 多 Tab 模式

### 4.5 线上部署

服务器需安装 Chromium：
```bash
playwright install --with-deps chromium
```

## 五、文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/services/wos_search.py` | 新建 | Playwright 搜索逻辑 |
| `backend/routers/library.py` | 修改 | 新增 `/entries/{id}/wos-search` 端点 |
| `frontend/src/LibraryTab.tsx` | 修改 | 新增 WOS 搜索按钮 + 处理函数 |
| `requirements.txt` | 修改 | 添加 `playwright` 依赖 |

## 六、备选方案（不推荐）

### 方案 B：纯前端预填 + 手动点击

直接 `window.open(WOS_URL + '?query=TI%3D%22title%22')`，用户在打开的页面手动点 Search。

- 优点：零后端改动，实现最简单
- 缺点：用户体验差，多一步手动操作

### 方案 C：后端定时清理 Playwright 实例

启动时预热一个浏览器实例，搜索时复用，定期清理。

- 优点：响应更快（省去启动时间）
- 缺点：内存占用，实现复杂

## 七、部署注意事项

### 7.1 ⚠️ 校园网限制

**WoS（Web of Science）需要校园网或机构 VPN 才能访问。** 线上服务器（阿里云）不在校园网内，无法访问 WoS，因此该功能**仅限本地打包版使用**，线上版暂不启用。

- 线上版：按钮已注释隐藏
- 本地打包版：取消注释即可使用，前提是运行环境能访问 `webofscience.clarivate.cn`

### 7.2 服务器安装 Playwright + Chromium（本地打包版）

```bash
pip install playwright
playwright install --with-deps chromium
```

`--with-deps` 会自动安装 Chromium 所需的系统库。Alibaba Cloud Linux（RHEL 系）需额外安装：
```bash
dnf install -y at-spi2-atk nss atk cups-libs libXcomposite libXdamage libXrandr mesa-libgbm pango alsa-lib libdrm libxkbcommon
```

### 7.3 本次改动文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/services/wos_search.py` | 新建 | Playwright 搜索逻辑 |
| `backend/routers/library.py` | 修改 | 新增 `/entries/{id}/wos-search` 端点 |
| `frontend/src/LibraryTab.tsx` | 修改 | 新增 WOS 搜索按钮 + 处理函数 |
| `frontend/dist/` | 重新构建 | `npm run build` |
| `backend/requirements.txt` | 修改 | 添加 `playwright` 依赖 |

### 7.4 双 routers/ 目录陷阱

`library.py` 是否受影响取决于根目录 `routers/` 下是否也存在 `library.py`。
本次 `library.py` 只存在于 `backend/routers/`，不受 `sys.path.insert` 影响，无需同步到根目录。

### 7.5 部署后验证

1. `systemctl is-active deepreading-api`
2. 浏览器打开文献库 → 点击某文献详情 → 确认"知网搜索"按钮旁边出现"WOS 搜索"按钮
3. 点击"WOS 搜索" → 应显示"搜索中..." → 约 10-30 秒后弹出 WoS 结果页
4. 检查 `/var/log/deepreading/api-error.log` 无 Playwright 报错
