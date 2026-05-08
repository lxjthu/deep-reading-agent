# 服务器报错排查记录

> 适用项目：`deep-reading-agent`  
> 记录日期：2026-05-03  
> 服务器环境：Ubuntu, Nginx, Cloudflare Tunnel, FastAPI (uvicorn)

---

## 问题 1：文献筛选时报错 `MultipleResultsFound`

### 错误现象

前端上传文献后，点击筛选/分析时返回：

```
❌ Unexpected token 'I', "Internal S"... is not valid JSON
```

实际是服务器返回了 `500 Internal Server Error`，前端无法解析为 JSON。

### 排查过程

查看服务器日志：

```bash
tail -100 /tmp/fastapi.log
```

发现关键错误：

```
sqlalchemy.exc.MultipleResultsFound: Multiple rows were found when one or none was required
```

错误堆栈指向：

```
File "backend/routers/filter.py", line 490, in start_filter
    prompt_template = await get_effective_prompt_text(...)
File "backend/prompt_service.py", line 84, in _get_template_row
    ).scalar_one_or_none()
```

### 根因分析

`prompt_templates` 表中存在重复记录，`_get_template_row` 函数使用 `scalar_one_or_none()` 期望返回 1 行，但实际返回了多行。

**为什么本地正常**：本地数据库可能没有重复记录，或者使用了不同的用户/配置。

### 解决方案

在服务器上执行以下步骤：

#### 1. 创建修复脚本

```bash
cat > /tmp/fix_prompt.py << 'EOF'
import sqlite3

conn = sqlite3.connect('/root/.openclaw/workspace/deep-reading-agent/db/app.sqlite')
cursor = conn.cursor()

# 查看重复记录
cursor.execute("""
    SELECT prompt_type, prompt_key, scope, owner_user_id, COUNT(*) as cnt
    FROM prompt_templates
    GROUP BY prompt_type, prompt_key, scope, owner_user_id
    HAVING cnt > 1
""")
rows = cursor.fetchall()
print(f"发现 {len(rows)} 组重复记录")
for row in rows:
    print(f"  {row}")

# 删除重复记录（保留 id 最小的那条）
cursor.execute("""
    DELETE FROM prompt_templates 
    WHERE id NOT IN (
        SELECT MIN(id) 
        FROM prompt_templates 
        GROUP BY prompt_type, prompt_key, scope, owner_user_id
    )
""")
print(f"删除了 {cursor.rowcount} 条重复记录")

conn.commit()
conn.close()
print("修复完成！")
EOF
```

#### 2. 执行脚本

```bash
python3 /tmp/fix_prompt.py
```

#### 3. 重启服务

```bash
cd /root/.openclaw/workspace/deep-reading-agent
bash start.sh
```

---

## 问题 2：上传文献时报错 "文件过大"

### 错误现象

修复问题 1 后，上传文献时前端报错"文件过大"，但实际文件不到 2MB。

### 排查过程

#### 1. 检查是否有 Nginx

```bash
grep -r "client_max_body_size" /etc/nginx/
```

结果为空，说明没有显式配置 `client_max_body_size`。

#### 2. 检查端口监听

```bash
ss -tlnp | grep ':80'
```

输出：

```
LISTEN 0  511  0.0.0.0:80  0.0.0.0:*  users:(("nginx",pid=3154757,fd=5),...)
```

发现 **Nginx 正在监听 80 端口**。

#### 3. 检查架构链路

```bash
cat /root/.cloudflared/config.yml
```

输出：

```
ingress:
  - hostname: deepreading.qzz.io
    service: http://127.0.0.1:80
```

确认架构：

```
Cloudflare Tunnel → Nginx (80) → FastAPI (8000)
```

### 根因分析

Nginx 的 `client_max_body_size` 默认值为 **1MB**，超过此大小的文件上传会被 Nginx 直接拒绝，返回 413 错误。

### 解决方案

#### 1. 找到 Nginx 配置文件

```bash
nginx -t
```

输出会显示配置文件路径，通常是 `/etc/nginx/nginx.conf`。

#### 2. 添加文件大小限制配置

```bash
vi /etc/nginx/nginx.conf
```

在 `http` 块中添加：

```
http {
    client_max_body_size 50m;
    ...
}
```

#### 3. 测试并重启 Nginx

```bash
nginx -t          # 测试配置语法
nginx -s reload   # 重新加载配置
```

---

## 问题 3：参考文献梳理时报错 `401 Authentication Fails`

### 错误现象

参考文献梳理功能报错：

```
❌ Error code: 401 - {'error': {'message': 'Authentication Fails, Your api key: ****5b25 is invalid', ...}}
```

用户已在前端配置了自己的 DeepSeek API Key，但系统仍使用服务器环境变量中的旧 Key（以 `5b25` 结尾）。

### 排查过程

#### 1. 检查服务器代码是否更新

```bash
cd /root/.openclaw/workspace/deep-reading-agent
git log --oneline -3
```

确认代码已是最新版本。

#### 2. 分析 API Key 传递链路

检查后端代码发现，API Key 传递链路在 `_try_extract_references` 处断裂：

```
前端用户 Key
    ↓
run_quant_task(api_key) / run_qual_task(api_key)
    ↓
_try_extract_references() ← 没有接收 api_key 参数 ❌
    ↓
extract_references_deepseek()
    ↓
call_deepseek_json() → os.getenv("DEEPSEEK_API_KEY") ← 使用环境变量 ❌
```

#### 3. 检查前端代码

发现 `ReferenceTraceTab` 组件没有接收和传递 `apiKey` 参数：

```javascript
// App.tsx
<ReferenceTraceTab />  // ← 没有传递 apiKey

// ReferenceTraceTab.tsx
body: JSON.stringify({})  // ← 没有包含 api_key
```

### 根因分析

问题有两层：

1. **后端**：`deepseek_refs.py` 中的 `call_deepseek_json` 直接使用 `os.getenv("DEEPSEEK_API_KEY")`，没有接受用户提供的 Key
2. **前端**：`ReferenceTraceTab` 组件没有接收父组件传递的 `apiKey`，也没有在请求中发送 `api_key`

### 解决方案

#### 1. 后端修复

修改 `backend/services/deepseek_refs.py`：

```python
# 修改前
def call_deepseek_json(messages, *, max_tokens, temperature):
    api_key = os.getenv("DEEPSEEK_API_KEY")

# 修改后
def call_deepseek_json(messages, *, max_tokens, temperature, api_key=None):
    if not api_key or not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY")  # 回退到环境变量
```

同时修改 `extract_references_deepseek` 和 `trace_citations_deepseek` 函数，接收并传递 `api_key` 参数。

修改 `backend/routers/reading.py` 中的 `_try_extract_references` 函数，接收并传递 `api_key` 参数。

修改 `backend/routers/references.py` 中的 `run_reference_trace_task` 函数，接收并传递 `api_key` 参数。

#### 2. 前端修复

修改 `frontend/src/App.tsx`：

```jsx
// 修改前
<ReferenceTraceTab />

// 修改后
<ReferenceTraceTab apiKey={apiKey} />
```

修改 `frontend/src/ReferenceTraceTab.tsx`：

```tsx
// 修改前
export default function ReferenceTraceTab() {
  // ...
  body: JSON.stringify({})

// 修改后
export default function ReferenceTraceTab({ apiKey }: { apiKey: string }) {
  // ...
  body: JSON.stringify({ ...(apiKey ? { api_key: apiKey } : {}) })
```

#### 3. 提交并推送

```bash
git add backend/services/deepseek_refs.py backend/routers/reading.py backend/routers/references.py
git commit -m "fix: use user-provided API key for reference extraction"

git add frontend/src/App.tsx frontend/src/ReferenceTraceTab.tsx
git commit -m "fix: pass user API key to reference trace from frontend"

git push origin online
```

---

## 问题 4：文献库页面返回 500 Internal Server Error（`DESC DESC` SQL 语法错误）

### 错误现象

前端打开"我的文献库"标签页时，`GET /api/library/entries` 返回 `500 Internal Server Error`，页面空白无数据。其他接口（`/api/auth/me`、`/api/history/`、`/api/prompts/catalog`）均正常。

### 排查过程

#### 1. 确认数据库和连接正常

```python
# 检查数据库文件和表
import sqlite3
conn = sqlite3.connect('db/app.sqlite')
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
# → 15 张表全部存在，alembic_version = 005_add_reference_trace_tables

# 检查用户数据
cur.execute("SELECT id, username, role FROM users")
# → (1, 'admin', 'admin'), (2, 'usercheck001', 'normal'), (3, 'lxj', 'normal')
```

数据库迁移完整，用户数据完好。

#### 2. 确认前后端通信正常

```
Frontend (localhost:5173) → Vite proxy /api → Backend (localhost:8000) ✅
Backend /health → 200 OK ✅
Backend /api/auth/login → 200 OK ✅
Backend /api/auth/me → 200 OK ✅
Backend /api/library/entries → 500 Internal Server Error ❌
```

#### 3. 定位 SQL 错误

直接用 Python 复现 `list_entries` 查询，捕获完整 traceback：

```
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) near "DESC": syntax error
[SQL: ... ORDER BY bib_entries.is_pinned DESC DESC, bib_entries.updated_at DESC, ...]
```

关键发现：**`DESC DESC`** —— 双重降序关键字，SQLite 无法解析。

### 根因分析

`backend/routers/library.py` 的 `list_entries` 函数中，排序逻辑存在 bug：

```python
# 旧代码（有 BUG）
order_cols = []
if sort_by == "score":
    order_cols.append(func.coalesce(score_subq.c.max_score, 0))
elif sort_by == "year":
    order_cols.append(BibEntry.year)
elif sort_by == "journal":
    order_cols.append(func.coalesce(BibEntry.journal, ""))
else:
    order_cols.append(BibEntry.is_pinned.desc())  # ← 已经调用了 .desc()
    order_cols.append(BibEntry.updated_at)

direction = desc if sort_order == "desc" else asc
stmt = stmt.order_by(*(direction(c) for c in order_cols), ...)  # ← 又包了一层 desc()
```

当 `sort_by == "updated"`（默认值）且 `sort_order == "desc"`（默认值）时：

1. `BibEntry.is_pinned.desc()` 已经返回一个 `DESC` 列对象
2. `direction(c)` 即 `desc(c)` 再次对它调用 `desc()`，产生 `DESC DESC`

SQLite 不支持 `DESC DESC` 语法，直接报错。

**影响范围**：只要 `sort_by` 为默认值 `"updated"`（即进入 `else` 分支），必然触发此 bug。这是文献库的默认排序参数，所以用户每次打开文献库都会 500。

### 解决方案

将排序逻辑改为显式的 `if/else` 分支，每种 `sort_by` 单独处理排序方向：

```python
# 新代码（已修复）
if sort_by == "score":
    if sort_order == "desc":
        stmt = stmt.order_by(desc(func.coalesce(score_subq.c.max_score, 0)), BibEntry.created_at.desc())
    else:
        stmt = stmt.order_by(asc(func.coalesce(score_subq.c.max_score, 0)), BibEntry.created_at.desc())
elif sort_by == "year":
    if sort_order == "desc":
        stmt = stmt.order_by(desc(BibEntry.year), BibEntry.created_at.desc())
    else:
        stmt = stmt.order_by(asc(BibEntry.year), BibEntry.created_at.desc())
elif sort_by == "journal":
    if sort_order == "desc":
        stmt = stmt.order_by(desc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
    else:
        stmt = stmt.order_by(asc(func.coalesce(BibEntry.journal, "")), BibEntry.created_at.desc())
else:
    # 默认排序：置顶优先 → 更新时间倒序 → 创建时间倒序
    stmt = stmt.order_by(BibEntry.is_pinned.desc(), BibEntry.updated_at.desc(), BibEntry.created_at.desc())
```

修改文件：`backend/routers/library.py`

### 验证

```python
# 本地直接查询验证
async with AsyncSessionLocal() as db:
    rows = (await db.execute(stmt)).all()
    # → 338 rows, 无报错
```

### 经验总结

- SQLAlchemy 的 `.desc()` 方法返回的是**已标记方向的列对象**，不应再用 `desc()` / `asc()` 二次包装
- `order_cols` 列表混用原始列和 `.desc()` 列对象，再用 generator 统一包装方向，是错误的模式
- 排序逻辑应显式处理，避免隐式的双重方向调用

---

## 服务器架构总结

```
┌─────────────────────────────────────────────────────────────────┐
│                         请求链路                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户浏览器                                                      │
│       │                                                         │
│       ▼                                                         │
│   Cloudflare Tunnel (HTTPS, 100MB 限制)                         │
│       │                                                         │
│       ▼                                                         │
│   Nginx (端口 80, 默认 1MB 限制)                                 │
│       │                                                         │
│       ▼                                                         │
│   FastAPI/Uvicorn (端口 8000)                                   │
│       │                                                         │
│       ▼                                                         │
│   SQLite 数据库                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 常用排查命令

| 目的 | 命令 |
|------|------|
| 查看后端日志 | `tail -100 /tmp/fastapi.log` |
| 查看前端日志 | `tail -100 /tmp/vite.log` |
| 检查服务进程 | `ps aux \| grep -E "uvicorn\|vite\|cloudflared\|nginx"` |
| 检查端口监听 | `ss -tlnp` |
| 测试 Nginx 配置 | `nginx -t` |
| 重启 Nginx | `nginx -s reload` |
| 检查数据库重复记录 | 见问题 1 的修复脚本 |
| 查看错误日志 | `grep -i "error\|401\|authentication\|failed" /tmp/fastapi.log \| tail -20` |

---

## 问题 5：前端报错 `Cannot construct a Request with a Request object that has already been used`

### 错误现象

远端部署后，用户操作（如保存提示词、上传文件）时前端控制台报错：

```
Failed to execute 'fetch' on 'Window': Cannot construct a Request with a Request object that has already been used.
```

本地开发环境难以复现。

### 排查过程

#### 1. 确认报错位置

查看 `frontend/src/lib/api-fetch.ts`：

```typescript
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const request = new Request(input, init)
  // ... 自动附加 token ...
  let response = await nativeFetch(request, { headers })
  if (response.status !== 401) return response
  // ... refresh token ...
  response = await nativeFetch(request, { headers: retryHeaders })  // ← 复用了同一个 request
}
```

#### 2. 分析触发条件

- `apiFetch` 第 36 行用 `new Request(input, init)` 创建了一个 Request 对象
- 第 43 行第一次 `nativeFetch(request, ...)` 已经消费了 request 的 body（如果有）
- 第 57 行 token refresh 后再次 `nativeFetch(request, ...)` 复用同一个对象
- **Request 对象的 body 只能被消费一次**，第二次使用时报错

### 根因分析

**为什么本地没事，远端必现？**

- 本地开发时 token 通常未过期，请求直接成功，不会走到 401 → refresh → retry 分支
- 远端 session 更短，或 CDN/代理导致更容易触发 token 刷新
- 只有 POST/PUT 请求带有 body 时才会触发此错误；GET 请求无 body，不会报错

### 解决方案

修改 `frontend/src/lib/api-fetch.ts`，retry 时重新创建 Request：

```typescript
export async function apiFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  // 保存 init 快照，用于 retry 时重新创建 Request
  const initSnapshot = init ? { ...init } : {}
  const request = new Request(input, initSnapshot)
  // ... 首次请求 ...

  if (response.status !== 401 || isAuthEndpoint(input)) {
    return response
  }

  // ... refresh token ...

  // retry 时创建新 Request，而不是复用已消费的旧 request
  const retryRequest = new Request(input, initSnapshot)
  const retryHeaders = new Headers(retryRequest.headers)
  retryHeaders.set('Authorization', `Bearer ${refreshedToken}`)
  response = await nativeFetch(retryRequest, { headers: retryHeaders })
  // ...
}
```

修改文件：`frontend/src/lib/api-fetch.ts`

### 验证

1. 本地可强制触发 retry：在浏览器 DevTools 手动清除 accessToken，刷新页面后立即发起 POST 请求
2. 观察 Network 面板：第一次请求 401，第二次请求成功（200），无控制台报错

### 经验总结

- `fetch()` 消费 Request body 后，该 Request 对象**不可复用**
- 任何需要 retry 的请求包装层，都必须保存原始 `input` 和 `init`，在 retry 时重新 `new Request(input, init)`
- GET 请求无 body，复用 Request 对象不会报错，因此这个 bug 在纯 GET 场景下是隐性的

---

## 服务器架构总结

```
┌─────────────────────────────────────────────────────────────────┐
│                         请求链路                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户浏览器                                                      │
│       │                                                         │
│       ▼                                                         │
│   Cloudflare Tunnel (HTTPS, 100MB 限制)                         │
│       │                                                         │
│       ▼                                                         │
│   Nginx (端口 80, 默认 1MB 限制)                                 │
│       │                                                         │
│       ▼                                                         │
│   FastAPI/Uvicorn (端口 8000)                                   │
│       │                                                         │
│       ▼                                                         │
│   SQLite 数据库                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 常用排查命令

| 目的 | 命令 |
|------|------|
| 查看后端日志 | `tail -100 /tmp/fastapi.log` |
| 查看前端日志 | `tail -100 /tmp/vite.log` |
| 检查服务进程 | `ps aux \| grep -E "uvicorn\|vite\|cloudflared\|nginx"` |
| 检查端口监听 | `ss -tlnp` |
| 测试 Nginx 配置 | `nginx -t` |
| 重启 Nginx | `nginx -s reload` |
| 检查数据库重复记录 | 见问题 1 的修复脚本 |
| 查看错误日志 | `grep -i "error\|401\|authentication\|failed" /tmp/fastapi.log \| tail -20` |

---

## 预防措施

1. **数据库层面**：在 `prompt_templates` 表上添加唯一约束，防止重复记录
2. **Nginx 层面**：部署时确保配置 `client_max_body_size` 为合理值
3. **代码层面**：查询时使用 `LIMIT 1` 或 `first()` 代替 `scalar_one_or_none()`，避免多行结果导致异常
4. **API Key 层面**：所有使用 API Key 的模块都应优先使用用户提供的 Key，环境变量仅作为回退选项
5. **前端层面**：所有需要 API Key 的页面组件都应接收并传递 `apiKey` 参数
6. **SQLAlchemy 排序层面**：不要对已调用 `.desc()` / `.asc()` 的列对象再用 `desc()` / `asc()` 二次包装；排序逻辑应显式处理每种 `sort_by` 分支，避免混用原始列和方向化列对象后统一包装
7. **前端 fetch 层面**：任何需要 retry 的请求包装层，retry 时必须重新 `new Request(input, init)`，禁止复用已消费的 Request 对象
