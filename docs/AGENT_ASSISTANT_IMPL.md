# AI 文献助手技术文档

> 最后更新：2026-05-23  
> 范围：本文件记录本轮已实现的 AI 文献助手、DeepSeek tool calling、input 文件夹白名单、文件夹清单扫描、文献库对比、批量精读编排和前端展示层。后续做持久会话、批量导入确认、Agent 工作流升级时优先参考本文。

## 目标

AI 文献助手用于把自然语言请求转换成受控工具调用，让 DeepSeek 在当前用户权限范围内完成文献库检索、精读上下文读取、任务启动、任务状态查询、input 文件夹扫描、主题筛选和文献库对比。

当前实现强调三条边界：

- AI 不直接执行任意 Python 脚本，只能调用后端白名单工具。
- AI 不读取任意磁盘路径，只能扫描用户在设置中保存的 input 文件夹白名单。
- “查看清单”和“启动精读”严格分离，避免用户只想看列表时误启动长任务。

## DeepSeek 能力探测结论

测试模型：`deepseek-v4-flash`

结论：

- 支持 OpenAI 兼容的 `tools` / function calling。
- 使用普通文本、JSON 输出、工具调用时，需要带 `extra_body={"thinking": {"type": "disabled"}}`，否则最小文本或 JSON 请求可能返回空 content。
- 新 Agent 调用统一使用 `extra_body={"thinking": {"type": "disabled"}}`。

## 后端入口

### 路由注册

文件：[backend/main.py](../backend/main.py)

- `app.include_router(agent.router, prefix="/api/agent", tags=["Agent"])`

### Agent Router

文件：[backend/routers/agent.py](../backend/routers/agent.py)

对外接口：

- `GET /api/agent/settings`
  - 函数：`get_agent_settings`
  - 用途：读取当前用户 Agent 设置。

- `PUT /api/agent/settings`
  - 函数：`update_agent_settings`
  - 请求模型：`AgentSettingsRequest`
  - 用途：保存 input 文件夹白名单路径。
  - 路径要求：必须是后端机器可访问的绝对路径；必须存在且为目录；空字符串表示清空。

- `POST /api/agent/chat`
  - 函数：`agent_chat`
  - 请求模型：`AgentChatRequest`
  - 返回：`text/event-stream`
  - SSE 事件：
    - `tool_call`：模型决定调用某个工具。
    - `tool_result`：后端工具执行结果。
    - `answer`：模型最终回答。
    - `done`：一轮结束。
    - `error`：执行错误。

## 后端数据模型使用

本轮没有新增数据库表，也没有新增 migration。

使用已有表：

- `UserSettings.preferences_json`
  - 保存 Agent 设置。
  - 当前结构：

```json
{
  "agent": {
    "input_folder_path": "D:\\papers\\input"
  }
}
```

- `File`
  - 文件夹导入工具会把白名单目录中的 PDF/Markdown 复制到系统上传目录，并创建或复用 `File`。

- `BibEntry`
  - 文件夹导入工具会调用现有精读路由里的 `reading.get_or_create_bib_entry`，创建或绑定最小文献条目。

- `Job` / `JobBibEntry` / `ReadingItem` / `Artifact`
  - 启动精读、查询任务状态、读取精读上下文时复用。

后续如果新增 `agent_sessions` / `agent_messages`，必须同步更新：

- `backend/db/models.py`
- Alembic migration
- `docs/DATABASE_SCHEMA.md`
- `backend/services/data_portability.py`

## 后端模型与辅助函数索引

### Pydantic 模型

- `AgentTurn`
  - 单条前端传入历史消息。
  - 字段：`role`、`content`。

- `AgentChatRequest`
  - `/api/agent/chat` 请求体。
  - 字段：`message`、`api_key`、`history`。

- `AgentSettingsRequest`
  - `/api/agent/settings` 保存请求体。
  - 字段：`input_folder_path`。

### SSE 与通用格式函数

- `sse_event(event, data)`
  - 生成 SSE 格式字符串。

- `_json_list(value)`
  - 安全解析数据库中的 JSON list 字符串。

- `_dt(value)`
  - datetime 转 ISO 字符串。

- `_entry_summary(entry, file_record=None)`
  - 将 `BibEntry` 转成 Agent 工具可返回的摘要对象。

### Agent 设置函数

- `_load_preferences(settings)`
  - 解析 `UserSettings.preferences_json`。

- `get_agent_preferences(db, user)`
  - 读取当前用户 Agent 设置。

- `save_agent_preferences(db, user, agent_prefs)`
  - 保存 Agent 设置。

- `_normalize_input_folder(raw_path)`
  - 校验 input 文件夹路径。
  - 规则：去除首尾空白和引号；必须为绝对路径；必须存在；必须为目录。

### 文献库工具函数

- `_owned_entries(db, user, entry_ids)`
  - 按 `entry_ids` 读取当前用户拥有的 `BibEntry`，并保持输入顺序。

- `tool_search_library(db, user, query="", reading_status="", limit=20)`
  - 工具名：`search_library`
  - 用途：按标题、摘要、期刊、关键词、标签检索当前用户文献库。

- `tool_get_entry_detail(db, user, entry_id)`
  - 工具名：`get_entry_detail`
  - 用途：获取单篇文献详情、源文件、最近工作流 timeline。

- `tool_get_reading_context(db, user, entry_ids, mode="", max_chars_per_item=2500)`
  - 工具名：`get_reading_context`
  - 用途：读取结构化精读结果，供 AI 做对比、综述和追问。

### 精读任务工具函数

- `tool_start_reading(db, user, api_key, mode, file_id="", entry_id="", ...)`
  - 工具名：`start_reading`
  - 用途：启动单篇长文本、七步法或四步法精读。
  - 内部复用：
    - `reading.start_long_context`
    - `reading.start_quant`
    - `reading.start_qual`
  - 注意：捕获 `HTTPException` 并返回结构化错误，避免 SSE 直接中断。

- `tool_start_batch_reading(db, user, api_key, mode, file_ids, ...)`
  - 工具名：`start_batch_reading`
  - 用途：启动多文件批量精读。
  - 内部复用：`reading.start_batch_reading`

- `tool_get_job_status(db, user, job_id)`
  - 工具名：`get_job_status`
  - 用途：查询任务状态和产物列表。

### 文件夹扫描与导入函数

- `_file_md5_and_sample(path)`
  - 读取文件 MD5、大小和前 4096 字节 sample。

- `_extract_preview(path, file_type, max_chars=2200)`
  - 为主题筛选提取短预览。
  - Markdown：直接读取文本。
  - PDF：使用 `pdfplumber` 读取前两页文本；失败时返回空字符串。

- `_collect_folder_files(input_folder, recursive, max_files)`
  - 扫描 input 白名单目录下的 PDF/Markdown 文件。
  - 支持递归。
  - 最大限制 100 个文件。

- `_classify_relevance(api_key, topic, candidates)`
  - 使用 DeepSeek 判断候选文献是否与主题相关。
  - 返回 `entry_id`、`relevant`、`confidence`、`reason`。

- `_is_all_topic(topic)`
  - 判断主题是否为全选通配符。
  - 当前支持：`*`、`all`、`全部`、`所有`、`全选`、`全部文献`、`所有文献`。
  - 语义：跳过主题筛选，所有候选都纳入。

- `tool_scan_input_folder(db, user, api_key, topic="*", recursive=False, max_files=50, confidence_threshold=0.55)`
  - 工具名：`scan_input_folder`
  - 用途：只读扫描 input 文件夹，按主题筛选，并与现有文献库对比。
  - 不导入文件。
  - 不启动精读。
  - 返回重点字段：
    - `papers`
    - `library_counts`
    - `skipped`
    - `note`

- `_import_source_file(db, user, source_path)`
  - 将白名单目录中的 PDF/Markdown 复制进系统上传目录。
  - 按 MD5 去重。
  - 创建或复用 `File`。
  - 调用 `reading.get_or_create_bib_entry` 创建或绑定 `BibEntry`。

- `tool_import_folder_and_start_reading(db, user, api_key, topic, mode, ...)`
  - 工具名：`import_folder_and_start_reading`
  - 用途：扫描 input 文件夹，导入文件，按主题筛选，然后启动批量精读。
  - 仅应在用户明确要求“启动 / 开始 / 精读 / 批量精读 / 七步法 / 四步法 / 长文本精读”时使用。

## 工具注册表

文件：[backend/routers/agent.py](../backend/routers/agent.py)

变量：`TOOL_SCHEMAS`

当前注册工具：

| 工具名 | 对应函数 | 是否只读 | 用途 |
|---|---|---:|---|
| `search_library` | `tool_search_library` | 是 | 检索当前用户文献库 |
| `get_entry_detail` | `tool_get_entry_detail` | 是 | 获取单篇文献详情和 timeline |
| `get_reading_context` | `tool_get_reading_context` | 是 | 获取结构化精读结果 |
| `start_reading` | `tool_start_reading` | 否 | 启动单篇精读 |
| `start_batch_reading` | `tool_start_batch_reading` | 否 | 启动批量精读 |
| `scan_input_folder` | `tool_scan_input_folder` | 是 | 只读扫描 input 文件夹并对比文献库 |
| `import_folder_and_start_reading` | `tool_import_folder_and_start_reading` | 否 | 导入 input 文件夹相关文献并启动精读 |
| `get_job_status` | `tool_get_job_status` | 是 | 查询任务状态和产物 |

工具执行分发函数：

- `execute_tool(name, args, db, user, api_key)`

Agent 消息构建函数：

- `build_messages(req)`

其中包含关键行为约束：

- “看看 / 列出 / 扫描 / 有哪些 / 列个表 / 筛出相关文献”只能调用 `scan_input_folder`。
- “启动 / 开始 / 执行 / 精读 / 批量精读 / 用七步法 / 用四步法 / 长文本精读”才允许调用会启动任务的工具。
- `topic="*"` 表示全部文献，不是某个研究主题。

## input 文件夹与文献库对比

`scan_input_folder` 返回的每篇文献包含：

```json
{
  "title": "文件名去扩展名",
  "filename": "paper.pdf",
  "relative_path": "paper.pdf",
  "extension": ".pdf",
  "size_bytes": 123456,
  "relevant": true,
  "confidence": 1.0,
  "reason": "topic=*，全部列出。",
  "library_match": {
    "status": "in_library",
    "method": "file_md5",
    "score": 1.0,
    "entry_id": "...",
    "library_title": "...",
    "file_id": "...",
    "reading_status": "read"
  }
}
```

`library_match.status`：

- `in_library`
  - 文件 MD5 命中现有 `File`，并且该文件已绑定 `BibEntry`。

- `file_exists_no_bib_entry`
  - 文件 MD5 命中现有 `File`，但没有绑定 `BibEntry`。

- `possible_match`
  - 文件未按 MD5 命中，但文件名标题和文献库标题相似度 `>= 0.72`。

- `not_in_library`
  - MD5 和标题都未匹配到可靠文献库记录。

汇总字段：

```json
{
  "library_counts": {
    "in_library": 0,
    "possible_match": 0,
    "not_in_library": 0,
    "file_exists_no_bib_entry": 0
  }
}
```

## 前端入口与组件

文件：[frontend/src/App.tsx](../frontend/src/App.tsx)

### 隐藏式 AI 助手标签

- `AGENT_TAB`
  - AI 助手标签定义。

- `agentTabVisible`
  - 控制 AI 助手 tab 是否显示。

- `visibleTabs`
  - `useMemo` 计算实际显示的 tab。
  - 默认不显示 `AGENT_TAB`。

- `handleOpenAgent`
  - 从右上角用户菜单或设置面板唤起 AI 助手。
  - 设置 `agentTabVisible=true` 并切换到 `tab=agent`。

### Agent 设置 UI

- `inputFolderPath`
  - 后端已保存的白名单路径。

- `inputFolderDraft`
  - 输入框草稿。

- `inputFolderStatus`
  - 保存状态与错误信息。

- `handleSaveInputFolder`
  - 调用 `PUT /api/agent/settings` 保存 input 文件夹路径。

### Agent 页面

- `AgentTab({ apiKey })`
  - AI 助手主页面。
  - 发送请求到 `/api/agent/chat`。
  - 解析 SSE 并渲染工具调用、工具结果和最终回答。

数据类型：

- `AgentChatEvent`
  - 字段：`id`、`type`、`title`、`body`、`payload`

- `AgentChatTurn`
  - 字段：`role`、`content`

### JSON 实时 HTML 渲染

- `tryParseJson(text)`
  - 尝试把字符串解析成 JSON。

- `formatJsonScalar(value)`
  - 格式化标量值。

- `isRecord(value)`
  - 判断是否为普通对象。

- `JsonHtmlView({ value, depth })`
  - 递归渲染 JSON。
  - 数组渲染为卡片列表。
  - 对象渲染为键值块。
  - 数字、布尔值、文本分别使用不同样式。

- `AgentEventBody({ event })`
  - 如果 `event.payload` 或 `event.body` 是 JSON，则渲染为 HTML 卡片；否则渲染为文本。

## 当前使用示例

### 只看 input 文件夹全部文献

用户：

```text
看看 input 文件夹里有哪些文献，主题是 *，列个表给我。
```

预期工具：

- `scan_input_folder`

预期行为：

- 不导入文件。
- 不启动精读。
- 返回全部 PDF/Markdown 清单。

### 看 input 文件夹并对比文献库

用户：

```text
看看 input 文件夹里有哪些文献，主题是 *，并和我的文献库对比，哪些已经在库里，哪些不在。
```

预期工具：

- `scan_input_folder`

预期行为：

- 返回 `library_match` 和 `library_counts`。
- 不启动精读。

### 启动七步法批量精读

用户：

```text
扫描 input 文件夹，找出和数字治理相关的文献，用七步法批量精读，跳过已精读的。
```

预期工具：

- `import_folder_and_start_reading`

预期行为：

- 扫描白名单目录。
- 导入候选文件。
- DeepSeek 判断主题相关性。
- 调用现有批量精读。
- 返回 `batch_id` 和任务列表。

### 查询任务状态

用户：

```text
查一下刚才那个 batch 的进度。
```

当前限制：

- 同页短上下文下可能可用。
- 刷新后不可靠，因为还没有持久 Agent 会话。

## 当前限制

- 没有持久化 Agent 会话。
  - 刷新页面后对话和工具结果不保留。
  - “刚才那些不在库里的文献”这类指代依赖短 history，不够可靠。

- 没有用户确认步骤。
  - 对执行型工具，目前依赖提示词区分“查看”和“启动”。
  - 后续建议加入前端确认弹窗：导入 N 篇、启动 M 个任务前必须确认。

- 文件夹扫描只支持 PDF / Markdown。
  - `.docx`、`.txt` 当前没有纳入 input 文件夹 Agent 扫描。

- PDF 预览只读取前两页。
  - 主题筛选可能受论文首页信息质量影响。

- 主题筛选结果依赖 DeepSeek。
  - `topic="*"` 已特殊处理为全选，跳过 DeepSeek 主题筛选。

- 文献库对比策略为启发式。
  - 优先 MD5 精确匹配。
  - 然后标题相似度匹配，阈值 `0.72`。
  - 标题相似度匹配只标记为 `possible_match`，不应自动覆盖或删除。

## 后续升级建议

### 持久会话

建议新增：

- `agent_sessions`
- `agent_messages`

保存：

- 用户消息
- assistant 回复
- `tool_call`
- `tool_result`
- 关键结构化状态，例如 `papers`、`selected`、`library_match`、`batch_id`

这样可以可靠支持：

- “只导入刚才不在库里的那些”
- “疑似匹配的先别导入”
- “继续查上一个 batch”
- “把上一轮结果导出成表”

### 执行前确认

建议为这些工具加确认机制：

- `start_reading`
- `start_batch_reading`
- `import_folder_and_start_reading`

交互建议：

1. 工具先返回 proposal。
2. 前端展示将导入/精读的文献列表。
3. 用户确认后再执行真正任务。

### 文献库对比增强

可加入：

- DOI 识别与匹配。
- PDF 元数据抽取后匹配。
- 标题规范化结果展示。
- `possible_match` 人工确认并绑定。

### 工具结果表格优化

前端 `JsonHtmlView` 当前是通用 JSON 卡片。

后续可针对字段做专用表格：

- `papers` 渲染成文献表。
- `library_counts` 渲染成统计条。
- `batch.tasks` 渲染成任务进度表。

## 验证记录

本轮实现中已运行过：

```powershell
python -m py_compile backend\routers\agent.py
python -m unittest backend.tests.test_queue_manager
cd frontend && npm run build
```

注意：文档记录的是当前已实现能力和设计约束。由于尚未加入持久会话和确认弹窗，后续升级时不要把自然语言执行请求直接扩大到更多破坏性操作。

## 2026-05-23 更新：持久会话与执行确认

新增后端表和迁移：

- `AgentSession` / `agent_sessions`
- `AgentMessage` / `agent_messages`
- `AgentActionProposal` / `agent_action_proposals`
- migration：`backend/migrations/versions/019_add_agent_sessions.py`
- `.dra` schema version：`019`

新增后端接口：

- `GET /api/agent/sessions`
- `POST /api/agent/sessions`
- `GET /api/agent/sessions/{session_id}`
- `POST /api/agent/proposals/{proposal_id}/confirm`
- `POST /api/agent/proposals/{proposal_id}/reject`

`POST /api/agent/chat` 现在支持 `session_id`，并通过 SSE 返回 `session` 事件。每轮会保存：

- user message
- tool_call
- tool_result
- proposal
- assistant answer

执行型工具现在采用 proposal-first：

- `start_reading`
- `start_batch_reading`
- `import_folder_and_start_reading`

这些工具在 chat 阶段只创建 `AgentActionProposal`，不直接启动任务。前端确认后调用 `/api/agent/proposals/{proposal_id}/confirm`，后端才真正执行对应任务。

前端更新：

- `AgentTab` 会恢复最近会话。
- 执行提案会显示确认面板。
- 用户可确认或取消提案。
- `scan_input_folder` 的结果使用业务表格展示 `library_counts` 和 `papers`，不再只展示递归 JSON。

## 2026-05-23 更新：UI 增强（输入框下移、Markdown 渲染、工具折叠、会话归档、导出对话）

### 1. 输入框移至 AI 回答下方

原来输入框在页面顶部，现在移到 events 列表下方、`sticky bottom-0` 吸附在可视区域底部。每次 events 更新或出现 proposal 时自动 scroll 到底部锚点。顶部只保留标题栏和操作按钮。

### 2. AI 回答 Markdown 渲染

新增 `AgentMdContent` 组件（`frontend/src/App.tsx`）：

- 使用 `marked` 解析 markdown 为 HTML
- 复用对比综述的数学公式渲染（`renderMathInElement`，KaTeX）
- 表格自动包裹 `<div class="agent-md-table-wrap">` 横向滚动
- 样式定义在 `frontend/src/index.css` 的 `.agent-md-content` 作用域下，不影响其他页面

`AgentEventBody` 判断 `type === 'answer' && title === 'AI 助手'` 的纯文本走 `AgentMdContent`，其他（用户消息、错误、工具结果）仍用 `<pre>` 纯文本。

### 3. 工具调用中间态折叠

新增 `groupEvents()` 将连续的 `tool_call` / `tool_result` 事件归组为 `ToolGroup`，`answer` 和 `error` 保持独立。

`AgentToolGroup` 使用 `<details>/<summary>` 实现可折叠块：

- 默认折叠，标题行显示工具调用链名称（如 `scan_input_folder → get_reading_data`）+ 步数
- 点击展开查看详细参数和结果
- 选择模式下切换为整组 checkbox（支持 indeterminate 半选状态）

### 4. 会话归档（清空上下文）

新增后端端点：

- `PATCH /api/agent/sessions/{session_id}/archive`
  - 将 session 的 `status` 从 `active` 改为 `archived`
  - 数据不动（`agent_messages`、`agent_action_proposals` 全保留），为将来记忆系统留基础
  - `GET /sessions` 只查 `status=active`，归档后不再出现在会话列表

前端「清空会话」按钮改为：先捕获当前 `sessionId`，清完 state 后异步调归档 API（fire-and-forget）。效果：

- LLM 上下文从零开始（`history=[]`）
- 刷新页面不恢复旧对话（旧 session 已 archived）
- 旧数据留在 DB 供将来记忆系统使用

无需新建 migration（`AgentSession.status` 已有 `archived` 状态）。

### 5. 导出对话为 Markdown

新增「导出对话」按钮，点击进入选择模式：

- 默认全选所有事件
- 「全选 / 取消全选」切换
- 单个事件 checkbox 勾选/取消
- 工具组支持整组 checkbox（半选 indeterminate）
- 「导出 (N)」按钮：将选中事件转为 Markdown 并触发浏览器下载

导出格式：

- 用户消息：`## 👤 你`
- AI 回答：`## 🤖 AI 助手`（原文 Markdown）
- 工具调用/结果/提案：`<details><summary>🔧 标题</summary>` + JSON 代码块
- 错误：`> ❌ 错误: 内容`（blockquote）
- 文件名：`AI文献助手_2026-05-23.md`

### 6. 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/routers/agent.py` | 新增 `PATCH /sessions/{id}/archive` |
| `frontend/src/App.tsx` | `AgentMdContent` 组件、`AgentToolGroup` 折叠、`AgentEventList` 选择模式、导出逻辑、输入框下移 |
| `frontend/src/index.css` | `.agent-md-content` 作用域样式 |
