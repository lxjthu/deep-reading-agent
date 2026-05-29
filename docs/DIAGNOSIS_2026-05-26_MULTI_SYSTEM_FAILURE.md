# 诊断报告：多系统故障（2026-05-26）

> **⚠️ 状态更新（2026-05-27）**：本文档中的 `asyncio.run()` 问题（根因 A）已修复——所有后台线程入口改为 `asyncio.new_event_loop()` + `loop.run_until_complete()`，不再创建多个事件循环。项目已迁移到 PostgreSQL，SQLite 相关内容仅作历史参考。

## 症状总览

| # | 症状 | 严重程度 |
|---|------|----------|
| 1 | 上传 27 篇 PDF，文献库只看到 2 篇 | 高 |
| 2 | AI 文献助手完全看不见精读任务 | 高 |
| 3 | 参考文献梳理报错 `Task attached to a different loop` | 高 |
| 4 | 文献库 AI 助手提问按钮无响应 | 中 |

**核心结论：以上四个症状共享两个根因——(A) `asyncio.run()` 在后台线程中的错误用法；(B) Nginx 代理缺少 SSE 缓冲禁用配置。**

---

## 根因 A：`asyncio.run()` 在后台线程中多次调用导致事件循环冲突

### 错误机制

```
uvicorn 主事件循环（线程 A）
  └── /api/reading/long/start [async endpoint]
       ├── get_or_create_bib_entry() → 创建 BibEntry ✅ 提交到 DB
       ├── create_reading_job()       → 创建 Job     ✅ 提交到 DB
       └── threading.Thread(target=run_long_context_task)  [线程 B，无事件循环]
            ├── asyncio.run(sync_job_and_bib_start)  ← 创建 loop-1，用完全局引擎连接池，关闭 loop-1
            ├── asyncio.run(_load_custom_dims)       ← 创建 loop-2，引擎连接池仍绑定 loop-1 → 💥
            ├── asyncio.run(_query_prev_reading_jobs) ← 同上 💥
            └── asyncio.run(finalize_reading_success) ← 同上 💥
```

**原理**：`AsyncSessionLocal` 是绑定到全局 `AsyncEngine` 的 `async_sessionmaker`（`db/session.py:47-52`）。`aiosqlite` 驱动创建的连接/Future 绑定到创建时的事件循环。当 `asyncio.run()` 第二次调用创建新循环时，旧连接的 Future 仍指向已关闭的 loop-1，触发 `got Future attached to a different loop`。

### 受影响的文件和调用点

| 文件 | 行号 | 函数 | `asyncio.run()` 调用次数 |
|------|------|------|--------------------------|
| `routers/references.py` | 719, 754, 782 | `run_reference_trace_task` | 3 次 |
| `routers/reading.py` | 1066, 1145, 1154, 1156, 1301, 1341, 1360 | `run_long_context_task` | 7 次 |
| `routers/reading.py` | 1377, 1497, 1529, 1549 | `run_quant_task` | 4 次 |
| `routers/reading.py` | 1566, 1686, 1718, 1738 | `run_qual_task` | 4 次 |
| `routers/reading.py` | 877, 900 | `_auto_ref_trace` | 2 次 |
| `routers/translation.py` | 103, 109, 119, 131, 166, 170, 207, 214 | `_run_translation_task` | 8 次 |
| `routers/library.py` | 1089 | `_run_translate_task` | 1 次（单次调用不会报错，但模式脆弱） |
| `routers/filter.py` | 653 | 后台筛选线程 | 可能有多次调用 |

### 如何解释症状 1/2/3

**症状 3（参考文献报错）**：`references.py:719` 首次 `asyncio.run(mark_trace_started)` 成功（新线程首次调用没问题），后续调用立即崩溃。错误信息正是 `mark_trace_started() running at references.py:450`。

**症状 2（AI 助手看不见精读任务）**：`reading.py` 的后台线程在首次 `asyncio.run(sync_job_and_bib_start)` 之后崩溃。`sync_job_and_bib_start` 把 Job 状态设为 `running`、BibEntry 状态设为 `reading`（`reading.py:594`），但后续的 `ReadingItem` 创建、`finalize_reading_success` 都不会执行。因此：
- `ReadingItem` 表为空 → `tool_get_reading_context`（`agent.py:823`）返回空列表
- Job 状态卡在 `running`（永远不到 `success`）
- AI 助手查询时找不到任何精读数据

**症状 1（27 篇只看到 2 篇）**：需要区分两种场景——

- **场景 A**：用户只是上传了 PDF，没有启动精读 → 上传接口（`upload.py:162-258`）只创建 `File` 记录，**不创建** `BibEntry`。文献库查询的是 `BibEntry` 表（`library.py:571`），所以未精读的 PDF 不在文献库里。
- **场景 B**：用户对 27 篇都启动了精读 → `get_or_create_bib_entry`（`reading.py:308-383`）在 endpoint 层（主线程）创建 BibEntry 并 commit，**早于**后台线程启动。即使线程崩溃，BibEntry 也应该存在。

  如果确实启动了 27 次精读但只看到 2 篇，最可能的原因是：部分精读请求通过 AI 助手的 `import_folder_and_start_reading`（`agent.py:1358`）批量发起，而 AI 助手本身受 SSE 缓冲问题影响（根因 B），请求未到达后端。

**建议**：在服务器上执行 `psql -h localhost -U postgres -d deepreading -c "SELECT COUNT(*) FROM bib_entries;"` 和 `psql -h localhost -U postgres -d deepreading -c "SELECT COUNT(*) FROM files;"` 确认两张表的实际记录数。

### 修复方案

**方案一（推荐，改动最小）**：在所有后台线程入口处创建单一事件循环并复用

```python
# 改前
def run_long_context_task(...):
    asyncio.run(sync_job_and_bib_start(...))  # 创建 loop-1，关闭 loop-1
    ...
    asyncio.run(finalize_reading_success(...)) # 创建 loop-2 → 💥

# 改后
def run_long_context_task(...):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(sync_job_and_bib_start(...))
        ...
        loop.run_until_complete(finalize_reading_success(...))
    except Exception as e:
        loop.run_until_complete(finalize_reading_failure(...))
    finally:
        loop.close()
```

需要修改的函数（每个函数的改法相同）：
- `routers/references.py` → `run_reference_trace_task`
- `routers/reading.py` → `run_long_context_task`、`run_quant_task`、`run_qual_task`、`_auto_ref_trace`
- `routers/translation.py` → `_run_translation_task`
- `routers/library.py` → `_run_translate_task`
- `routers/filter.py` → 后台筛选线程（如有）

**方案二（更彻底）**：为后台线程创建独立的 AsyncEngine

在 `db/session.py` 中新增线程局部的 session 工厂，避免复用主引擎的连接池。改动较大但更健壮。

**方案三（最彻底）**：使用同步数据库驱动

`session.py:27` 已定义 `SYNC_DATABASE_URL`。在后台线程中用 `sqlite3` 直接操作数据库，完全绕过 asyncio。但需要为每个操作写同步版本的 CRUD。

---

## 根因 B：Nginx 代理缺少 SSE 缓冲禁用配置

### 问题定位

当前 Nginx 配置（`/etc/nginx/conf.d/deepreading-18080.conf`）：

```nginx
location / {
    proxy_pass http://127.0.0.1:18000;
    proxy_http_version 1.1;
    # ... 其他 proxy_set_header ...
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
    # ❌ 缺少 proxy_buffering off
}
```

**默认行为**：Nginx 开启 `proxy_buffering`（默认 on），会缓冲上游响应直到缓冲区满或响应结束才发给客户端。SSE（Server-Sent Events）依赖实时流式传输，缓冲会导致前端 `response.body.getReader()` 收不到任何数据块。

### 受影响的 SSE 端点

| 端点 | 文件 | 行号 | 功能 |
|------|------|------|------|
| `POST /api/library/chat` | `library_chat.py` | 547 | 文献库 AI 助手提问 |
| `POST /api/agent/chat` | `agent.py` | ~1720 | AI 文献助手（独立 Tab） |
| `POST /api/translation/start` | `translation.py` | - | 全文翻译进度 |

### 如何解释症状 4（提问按钮无响应）

1. 用户点击"提问" → 前端 `handleChatSubmit()` 设置 `chatLoading=true`，发送 `POST /api/library/chat`
2. 后端开始处理，通过 SSE 流式发送 `event: intent`、`event: results`、`event: report` 等
3. **Nginx 缓冲了 SSE 响应**，前端 `reader.read()` 收不到数据
4. 前端卡在等待状态，用户看到"分析中..."但无任何结果
5. 如果用户刷新页面，`chatLoading` 重置为 `false`，按钮恢复为"提问"
6. 用户再次点击，重复上述流程 → 结论："按钮失效了"

### 修复方案

在 Nginx 配置中为 SSE 端点禁用缓冲：

```nginx
# SSE 流式端点 — 禁用缓冲
location ~ ^/api/(library/chat|agent/chat|translation/start) {
    proxy_pass http://127.0.0.1:18000;
    proxy_http_version 1.1;
    proxy_set_header Host $host:$server_port;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_buffering off;
    proxy_cache off;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}

# 其他所有请求
location / {
    proxy_pass http://127.0.0.1:18000;
    proxy_http_version 1.1;
    proxy_set_header Host $host:$server_port;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 600s;
    proxy_send_timeout 600s;
}
```

> **注意**：SSE location 块必须放在 `location /` 之前，Nginx 按顺序匹配。

---

## 修复优先级和执行顺序

| 步骤 | 修复内容 | 影响范围 | 预计改动量 |
|------|----------|----------|------------|
| **1** | Nginx 添加 SSE `proxy_buffering off` | 症状 4 立即修复 | 改 1 个配置文件 |
| **2** | 修复 `references.py` 的 `run_reference_trace_task` | 症状 3 修复 | ~20 行 |
| **3** | 修复 `reading.py` 的 3 个 `run_*_task` + `_auto_ref_trace` | 症状 2 修复，精读恢复 | ~80 行 |
| **4** | 修复 `translation.py` 的 `_run_translation_task` | 翻译功能恢复 | ~30 行 |
| **5** | 修复 `library.py` / `filter.py` 的后台线程（如有） | 全面修复 | ~20 行 |
| **6** | 确认数据库中 BibEntry / File 记录数，补充缺失数据 | 症状 1 确认 | 视情况 |

步骤 1 只需改 Nginx 配置并 reload，无需重启后端。步骤 2-5 需要修改 Python 代码并重启 uvicorn。步骤 6 需要在服务器上查询数据库。

---

## 附录：快速验证命令

在服务器上执行，确认当前状态：

```bash
# 检查数据库中的记录数（PostgreSQL）
cd /root/deep-reading-agent
source venv/bin/activate
psql -h localhost -U postgres -d deepreading -c "
SELECT 'files' as tbl, COUNT(*) FROM files
UNION ALL SELECT 'bib_entries', COUNT(*) FROM bib_entries
UNION ALL SELECT 'reading_items', COUNT(*) FROM reading_items
UNION ALL SELECT 'jobs', COUNT(*) FROM jobs;
"

# 检查是否有 stuck 在 running 的 Job
psql -h localhost -U postgres -d deepreading -c "
SELECT id, job_type, status, current_stage FROM jobs ORDER BY created_at DESC LIMIT 20;
"

# 检查 Nginx SSE 缓冲配置
grep -r "proxy_buffering" /etc/nginx/

# 检查后端日志中的 asyncio 错误
grep -i "different loop\|attached to" /var/log/deepreading/api.log | tail -20
```
