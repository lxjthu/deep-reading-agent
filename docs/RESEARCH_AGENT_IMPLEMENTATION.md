# Research Agent 技术实现文档

> 最后更新：2026-05-31（Sprint 1 完成）
> 对应分支：`codex/deepreading-empty-postgres-deploy`
> 线上地址：http://8.162.14.154:18080/
> 设计方案：[`RESEARCH_AGENT_UPGRADE_PLAN.md`](RESEARCH_AGENT_UPGRADE_PLAN.md)

## 1. 概述

本项目已将原有的 AI 文献助手升级为 **数据库驱动的研究 Agent**。核心思路是：

- **不使用向量嵌入**，采用结构化 SQL + ILIKE 词汇匹配 + 分层评分
- **证据分 P0/P1/P2/P3 四级**，按权威性排序后返回给 LLM
- **工具注册表统一管理**，19 个工具通过 OpenAI-compatible function calling 调用
- **写操作必须走 proposal**，LLM 不能直接执行写库或启动任务
- **Runtime 开始接管跨轮承接**，已具备 TaskFrame、工作记忆、工具预算与批量分析缓存复用能力

## 2. 代码文件清单

| 文件 | 职责 | 行数 |
|------|------|------|
| `backend/services/agent_tool_registry.py` | 工具注册表：AgentTool 数据类、19 个工具定义、OpenAI schema 生成 | 327 |
| `backend/services/research_retrieval.py` | 分层检索引擎：查询解析、多表搜索、证据收集、评分排序、分页全量 | 725 |
| `backend/services/agent_external_retrieval.py` | 外部检索工具：CNKI URL 生成、英文全文候选查找（只读不写库） | 156 |
| `backend/services/research_agent_runtime.py` | Runtime 规划层：TaskFrame、Continuation Resolver、预算治理、工作记忆摘要 | 1200+ |
| `backend/services/agent_errors.py` | 错误枚举体系：AgentErrorCode(17) + RuntimeNoticeCode(13) + payload 工厂 | 99 |
| `backend/services/reading_candidate_analysis.py` | 大集合批量分析、期刊层级排序、结构化工作笔记、analysis_cache 子集过滤 | 790 |
| `backend/services/journal_quality_kb.py` | 顶刊名录知识库与期刊质量打分 | 150+ |
| `backend/routers/agent.py` | Agent 路由：会话管理、消息持久化、工具分发、runtime 接线、SSE 流式对话 | 2300+ |
| `backend/tests/test_agent_tool_registry.py` | 工具注册表单测 | 65+ |
| `backend/tests/test_research_retrieval.py` | 分层检索单测 | 247 |
| `backend/tests/test_research_agent_runtime.py` | Runtime 规划层单测 | 500+ |
| `backend/tests/test_reading_candidate_analysis.py` | 批量分析与 analysis_cache 单测 | 180+ |

## 3. 工具注册表 — `agent_tool_registry.py`

### 3.1 核心数据结构

#### `AgentTool` dataclass（第 8-18 行）

```python
@dataclass(frozen=True, slots=True)
class AgentTool:
    name: str                    # 工具名称，LLM 调用时的 function name
    description: str             # 工具描述，LLM 决策参考
    permission: str              # 权限等级：read_local / propose_write / external_read
    schema: dict                 # OpenAI function calling 的 parameters schema
    consent_required: bool       # 是否需要用户联网授权（external_read 类工具）
    proposal_required: bool      # 是否必须创建 proposal 才能执行
    writes_database: bool        # 是否会写数据库
    uses_internet: bool          # 是否访问互联网
    handler: str | None          # 对应 execute_tool 中的分发 key
```

#### 方法

| 方法 | 位置 | 作用 |
|------|------|------|
| `AgentTool.as_openai_schema()` | 第 20-28 行 | 转为 OpenAI function calling 格式 `{"type":"function","function":{...}}` |
| `AgentTool.as_capability()` | 第 30-39 行 | 转为管理/调试用的元数据（不含 handler） |
| `get_tool(name)` | 第 280-284 行 | 按名称查找工具，不存在抛 KeyError |
| `list_tool_capabilities()` | 第 287-288 行 | 返回所有工具的 capability 列表（供 admin API） |

### 3.2 已注册工具一览（16 个）

#### 只读本地工具（`permission="read_local"`）

| 工具名 | handler | 描述 | Schema 关键参数 |
|--------|---------|------|----------------|
| `research_search` | `research_search` | 分层检索文献库（metadata + 摘要 + 笔记 + 注释 + 参考文献 + 原文窗口） | `question`(必填), `entry_ids`, `keywords`, `include_source_text/user_notes/ai_notes`, `limit_entries`(0=全部), `limit_evidence_per_entry` |
| `get_evidence_pack` | `get_evidence_pack` | 返回 P0/P1/P2 证据包，含评分和冲突标记 | 同上 |
| `get_source_windows` | `get_source_windows` | 获取 Markdown 原文文本窗口（关键词命中片段 + 标题路径） | `entry_ids`(必填), `question`, `max_windows_per_entry` |
| `search_library` | `search_library` | 按标题/摘要/期刊/关键词/标签搜索文献库 | `query`, `reading_status`, `limit` |
| `count_library` | `count_library` | 直接统计文献总数，避免把当前页误当总量 | `query`, `reading_status` |
| `analyze_reading_candidates` | `analyze_reading_candidates` | 大集合分批分类、优先精读排序、写入工作笔记 | `topic`(必填), `query`, `reading_status`, `batch_size`, `max_entries` |
| `filter_analysis_cache` | `filter_analysis_cache` | 在当前会话上一轮论文级标注缓存上继续筛选，不重新扫全库 | `topic`(必填), `journal_tier_labels`, `cluster_labels`, `require_fulltext`, `reading_status`, `max_entries` |
| `get_entry_detail` | `get_entry_detail` | 获取单篇文献元数据、笔记、工作流时间线 | `entry_id`(必填) |
| `get_reading_context` | `get_reading_context` | 获取精读结构化内容（按 mode 过滤） | `entry_ids`(必填), `mode`, `max_chars_per_item` |
| `scan_input_folder` | `scan_input_folder` | 只读扫描已上传的 inbox 批次，与文献库比对 | `topic`, `recursive`, `max_files`, `confidence_threshold` |
| `get_job_status` | `get_job_status` | 查询任务状态和产物链接 | `job_id`(必填) |


### Economics/Management Idea Lab Tools

The research agent includes read-only tools for economics and management research ideation. These tools are designed for local evidence synthesis and do not run code, modify the database, or perform external search.

| Tool | Permission | Purpose |
|---|---|---|
| `extract_research_constructs` | `read_local` | Extract theoretical constructs, mechanisms, variables, empirical-design hints, and source-backed evidence from selected literature. |
| `diagnose_research_gaps` | `read_local` | Identify theory, mechanism, measurement, context, and causal-identification gaps from extracted constructs. |
| `generate_research_ideas` | `read_local` | Generate structured research idea candidates with question, hypotheses, data strategy, contribution, risks, and evidence references. |

Evidence discipline:

- P0 evidence remains the strongest source: original text windows, title, abstract, DOI, metadata, and exact source evidence.
- P1 evidence includes user notes, edits, annotations, and card notes.
- P2 AI-generated reading notes may guide synthesis but cannot override P0/P1.
- If a proposed idea depends on missing evidence, the tool must report it as a gap or risk.

The idea-lab workflow is inspired by AI-Researcher's concept-decomposition pattern but is adapted to economics and management research. It does not import AI-Researcher's Docker execution, ML code agents, or ChromaDB memory.
#### 写操作工具（`permission="propose_write"`，必须创建 proposal）

| 工具名 | handler | 描述 | Schema 关键参数 |
|--------|---------|------|----------------|
| `start_reading` | `start_reading` | 启动单篇精读（long/quant/qual） | `mode`(必填), `file_id`, `entry_id`, `conflict_resolution` |
| `start_batch_reading` | `start_batch_reading` | 启动批量精读 | `mode`(必填), `file_ids`(必填) |
| `import_folder_and_start_reading` | `import_folder_and_start_reading` | 扫描 inbox + 筛选 + 启动批量精读 | `topic`(必填), `mode`(必填), `confidence_threshold` |

#### 外部检索工具（`permission="external_read"`，需用户授权）

| 工具名 | handler | 描述 | consent | internet |
|--------|---------|------|---------|----------|
| `search_cnki` | `tool_search_cnki` | 生成 CNKI 题名检索 URL，返回 `open_urls` 供前端批量打开 | ✅ | ✅ |
| `lookup_english_fulltext` | `tool_lookup_english_fulltext` | 查询 OpenAlex/Unpaywall/Semantic Scholar 全文候选（只返回候选，不自动下载） | ✅ | ✅ |

## 4. 分层检索引擎 — `research_retrieval.py`

### 4.1 证据分层模型

```
P0（原文/元数据）  — 权威最高，出现冲突时以 P0 为准
  ├── bib_entries.title / abstract / abstract_cn / doi / journal / keywords
  ├── bib_references（参考文献原文）
  ├── bib_reference_citations（引用原文）
  └── source_window（Markdown 原文关键词命中片段）

P1（用户/人工编辑笔记） — 第二权威
  ├── bib_entries.user_note
  ├── reading_item_edits（人工编辑后的精读条目）
  ├── annotations（is_ai_generated=0 的批注）
  └── card_notes（卡片笔记）

P2（AI 生成笔记） — 有用但不覆盖 P0/P1
  ├── reading_items（AI 精读条目）
  └── annotations（is_ai_generated=1 的批注）

P3（临时联网结果） — 不自动写入数据库
  └── CNKI / 英文全文候选 / 网页检索结果
```

### 4.2 评分体系

| 常量 | 值 | 位置 |
|------|---|------|
| `TIER_ORDER` | `{"P0": 0, "P1": 1, "P2": 2, "P3": 3}` | 第 25 行 |
| `TIER_BASE_SCORE` | `{"P0": 100.0, "P1": 70.0, "P2": 45.0, "P3": 25.0}` | 第 26 行 |
| `FIELD_WEIGHTS` | doi:30, title:22, source_window:18, citation:18, abstract:15, user_note:15, reference:14, edited_reading_item:13, annotation:11, card_note:10, reading_item:7 | 第 27-39 行 |

最终分数 = `TIER_BASE_SCORE + FIELD_WEIGHTS + coverage * 10`

排序逻辑（`_sort_evidence`，第 157-165 行）：先按 tier（P0→P1→P2→P3），再按 score 降序。

### 4.3 查询解析

#### `_terms(query)` — 第 64-74 行

从 `query.question` 和 `query.keywords` 中提取中文/英文词汇（正则 `[\w\u4e00-\u9fff.-]+`），去重、过滤长度 <2 的词。

#### `ResearchQuery` dataclass — 第 42-51 行

```python
@dataclass(slots=True)
class ResearchQuery:
    question: str                         # 用户问题
    entry_ids: list[str]                  # 指定文献 ID（空=搜索全部）
    keywords: list[str]                   # 额外关键词
    include_source_text: bool = True      # 是否包含原文窗口
    include_user_notes: bool = True       # 是否包含用户笔记
    include_ai_notes: bool = True         # 是否包含 AI 笔记
    limit_entries: int = 10               # 最大文献数，0=搜索全部
    limit_evidence_per_entry: int = 8     # 每篇文献最大证据条数
```

### 4.4 文献加载

#### `_base_entry_stmt(owner_user_id, query, terms)` — 第 293-312 行

构建 bib_entries 基础 SQL：按 owner_user_id 过滤 + 按 entry_ids 或 terms（title/abstract/journal/doi/keywords/tags/user_note 的 ILIKE）过滤。被 `_load_entries` 和 `_load_all_entries` 共用。

#### `_load_entries(db, owner_user_id, query, terms)` — 第 168-287 行

有界加载（`limit_entries > 0` 时）：
1. 按 `_base_entry_stmt` 查询 bib_entries，LIMIT limit_entries
2. 扩展候选集：通过 reading_items、reading_item_edits、annotations、card_notes、bib_references、bib_reference_citations 的内容匹配找到关联文献
3. 按 coverage 排序，返回前 limit 条

#### `_load_all_entries(db, owner_user_id, query, terms)` — 第 315-336 行

全量加载（`limit_entries == 0` 时）：
1. COUNT 统计匹配总数
2. 总数 ≤ 100 → 一次加载
3. 总数 > 100 → 分批加载（每批 `BATCH_SIZE=100`，用 OFFSET 分页）
4. 最终通过 `_rank_entries` 按 coverage 排序

#### `_rank_entries(entries, terms)` — 第 339-348 行

按 `title + abstract + user_note` 的 coverage 降序排列。

### 4.5 证据收集

#### `_collect_entry_evidence(db, owner_user_id, entry, query, terms)` — 第 445-663 行

对单篇文献收集所有层级的证据：

| 证据来源 | 层级 | source_kind | 表 | 行号 |
|----------|------|-------------|---|------|
| title | P0 | `title` | bib_entries | 454-475 |
| abstract / abstract_cn | P0 | `abstract` | bib_entries | 456-457 |
| doi | P0 | `doi` | bib_entries | 458 |
| journal | P0 | `abstract` | bib_entries | 459 |
| keywords_json | P0 | `abstract` | bib_entries | 460 |
| user_note | P1 | `user_note` | bib_entries | 477-489 |
| reading_item_edits | P1 | `edited_reading_item` | reading_item_edits | 491-516 |
| annotations（人工） | P1 | `annotation` | annotations | 518-546 |
| annotations（AI） | P2 | `annotation` | annotations | 529 |
| card_notes | P1 | `card_note` | card_notes | 548-570 |
| reading_items | P2 | `reading_item` | reading_items | 572-594 |
| bib_references | P0 | `reference` | bib_references | 596-616 |
| bib_reference_citations | P0 | `citation` | bib_reference_citations | 618-639 |
| source_window（Markdown） | P0 | `source_window` | files | 641-661 |

#### `_evidence(...)` — 第 128-154 行

构造单条证据记录的工厂函数，包含 `entry_id`、`source_tier`、`source_kind`、`table`、`row_id`、`quote`（关键词命中片段）、`score` 等字段。

### 4.6 原文窗口检索

#### `get_source_windows(db, owner_user_id, entry_ids, question, max_windows_per_entry)` — 第 351-397 行

- 仅支持 Markdown 文件（PDF 需先绑定 Markdown 或运行精读/翻译）
- 读取文件内容 → `_strip_frontmatter` 去除 YAML 头 → `_source_hits` 找关键词位置 → 返回上下文窗口
- 每个窗口包含 `heading_path`（标题路径，如 "2. 方法 / 2.1 数据来源"）、`char_start`/`char_end`、`quote`

#### `_strip_frontmatter(text)` — 第 400-405 行

去除 `---` 开头的 YAML frontmatter。

#### `_heading_path(text, offset)` — 第 408-419 行

根据字符偏移位置，向上扫描找到所有 `#` 标题层级，返回 `" / "` 连接的路径。

#### `_source_hits(text, terms, limit)` — 第 422-442 行

在原文中找关键词命中位置，返回每个命中点的 ±260/520 字符窗口。

### 4.7 顶层入口

#### `get_evidence_pack(db, owner_user_id, query)` — 第 666-710 行

1. 根据 `limit_entries` 选择 `_load_all_entries`（=0）或 `_load_entries`（>0）
2. 逐篇收集证据
3. 按最高 score 排序
4. 返回 `{question, entries: [{...entry_summary, evidence, conflicts}], external_evidence, limitations}`

#### `research_search(db, owner_user_id, query)` — 第 713-725 行

`get_evidence_pack` 的薄包装，返回 `{question, count, entries, limitations}`。

## 5. 外部检索工具 — `agent_external_retrieval.py`

### 5.1 CNKI 检索

#### `build_cnki_title_search_url(title)` — 第 14-17 行

构建 CNKI 题名检索 URL：`https://kns.cnki.net/kns8s/defaultresult/index?kw=...&korder=TI`

#### `tool_search_cnki(db, user, entry_ids, titles, max_items)` — 第 47-100 行

- 从 bib_entries 获取文献标题
- 为每个标题生成 CNKI 搜索 URL
- 返回 `{status:"ready_to_open", open_urls:[...], items:[...], note:"..."}` 
- `open_urls` 由前端批量打开新标签页
- **不写数据库**，结果为 P3 临时线索

### 5.2 英文全文检索

#### `tool_lookup_english_fulltext(db, user, entry_ids, max_entries)` — 第 114-156 行

- 调用已有的 `services/fulltext_lookup.lookup_fulltext()` 
- 查询 OpenAlex、Unpaywall、Semantic Scholar、Google PDF、working-paper 搜索
- 返回每个文献的 `pdf_candidates`、`landing_pages`、`working_paper_searches`
- 收集所有 URL 到 `open_urls` 供前端打开
- **不自动下载 PDF**，不写数据库

## 6. Agent 路由 — `routers/agent.py`

### 6.1 会话管理

| 函数 | 位置 | 作用 |
|------|------|------|
| `_ensure_session(db, user, req)` | 第 150-165 行 | 查找或创建 AgentSession |
| `_next_message_order(db, session_id)` | 第 168-176 行 | 获取下一条消息序号 |
| `_save_agent_message(db, user, session, ...)` | 第 179-205 行 | 持久化 AgentMessage（含 tool_call/tool_result/proposal/message） |
| `_update_session_state(db, session, key, value)` | 第 221-232 行 | 更新 session.last_state_json |
| `get_agent_preferences(db, user)` | 第 300-327 行 | 获取用户 Agent 偏好（inbox batch 等） |
| `save_agent_preferences(db, user, agent_prefs)` | 第 330-343 行 | 保存用户 Agent 偏好 |

### 6.2 Proposal 流程

| 函数 | 位置 | 作用 |
|------|------|------|
| `_create_proposal(db, user, session, action_type, arguments, preview)` | 第 235-273 行 | 创建 AgentActionProposal（pending 状态），发送 proposal SSE 事件 |
| `_proposal_payload(proposal)` | 第 276-287 行 | 将 proposal 转为 API 返回格式 |
| `_execute_proposal_action(db, user, proposal, api_key)` | 第 625-638 行 | 根据 action_type 分发执行（start_reading / start_batch_reading / import_folder_and_start_reading） |

#### API 端点

| 方法 | 路径 | 位置 | 作用 |
|------|------|------|------|
| POST | `/api/agent/proposals/{id}/confirm` | 第 641-695 行 | 确认 proposal → 执行 → 保存结果 |
| POST | `/api/agent/proposals/{id}/reject` | 第 698-731 行 | 拒绝 proposal |

### 6.3 原有工具实现（写在 router 内）

| 函数 | 位置 | 工具名 | 权限 |
|------|------|--------|------|
| `tool_search_library(db, user, query, reading_status, limit)` | 第 767-798 行 | `search_library` | read_local |
| `tool_get_entry_detail(db, user, entry_id)` | 第 801-834 行 | `get_entry_detail` | read_local |
| `tool_get_reading_context(db, user, entry_ids, mode, max_chars_per_item)` | 第 837-873 行 | `get_reading_context` | read_local |
| `tool_start_reading(db, user, api_key, mode, ...)` | 第 876-924 行 | `start_reading` | propose_write |
| `tool_start_batch_reading(db, user, api_key, mode, file_ids, ...)` | 第 927-953 行 | `start_batch_reading` | propose_write |
| `tool_get_job_status(db, user, job_id)` | 第 956-986 行 | `get_job_status` | read_local |
| `tool_scan_input_folder(db, user, api_key, topic, ...)` | 第 1165-1381 行 | `scan_input_folder` | read_local |
| `tool_import_folder_and_start_reading(db, user, ...)` | 第 1384-1436 行 | `import_folder_and_start_reading` | propose_write |

### 6.4 工具分发器

#### `execute_tool(name, args, db, user, api_key, session)` — 第 1455-1530 行

统一的工具分发入口。根据 `name` 路由到对应实现：

- `research_search` / `get_evidence_pack` / `get_source_windows` → `research_retrieval.py`
- `search_cnki` / `lookup_english_fulltext` → `agent_external_retrieval.py`
- `search_library` / `get_entry_detail` / `get_reading_context` / `get_job_status` → router 内函数（直接执行）
- `start_reading` / `start_batch_reading` / `import_folder_and_start_reading` → `_create_proposal`（创建 proposal，不直接执行）

#### `_research_query_from_args(args)` — 第 1439-1450 行

将 LLM 工具调用参数转为 `ResearchQuery` 对象。`limit_entries=0` 表示搜索全部。

### 6.5 System Prompt — `build_messages(req)` — 第 1533-1579 行

三段系统提示：

1. **基础角色**（第 1537-1547 行）：工具使用规则、不要编造数据、inbox 来源说明
2. **查看 vs 执行**（第 1553-1558 行）：严格区分只读扫描和启动任务
3. **证据规则**（第 1564-1572 行）：P0/P1/P2/P3 分层、冲突处理、联网需授权、limit_entries=0 搜索全部

### 6.6 SSE 流式对话 — `agent_chat(req)` — 第 1582-1693 行

主循环逻辑：

1. 验证 API Key → 创建 LLM client
2. 确保 session → 保存用户消息 → 构建 messages
3. **最多 MAX_TOOL_ROUNDS=8 轮**：
   - 调用 LLM（deepseek-v4-flash）
   - 无 tool_calls → 返回 answer，结束
   - 有 tool_calls → 逐个执行 → 发送 tool_call/tool_result/proposal SSE 事件 → 追加到 messages → 继续下一轮
4. 超过 8 轮 → 返回"工具调用轮次已达上限"

SSE 事件类型：`session` / `tool_call` / `tool_result` / `proposal` / `answer` / `error` / `done`

## 7. API 端点清单

| 方法 | 路径 | Handler | Agent 可调 |
|------|------|---------|-----------|
| GET | `/api/agent/settings` | `get_agent_settings` | 直接 |
| PUT | `/api/agent/settings` | `update_agent_settings` | proposal |
| GET | `/api/agent/tool-capabilities` | `get_agent_tool_capabilities` | admin only |
| GET | `/api/agent/sessions` | `list_agent_sessions` | 直接 |
| POST | `/api/agent/sessions` | `create_agent_session` | 直接 |
| GET | `/api/agent/sessions/{id}` | `get_agent_session` | 直接 |
| PATCH | `/api/agent/sessions/{id}/archive` | `archive_agent_session` | 直接 |
| POST | `/api/agent/proposals/{id}/confirm` | `confirm_agent_proposal` | 用户操作 |
| POST | `/api/agent/proposals/{id}/reject` | `reject_agent_proposal` | 用户操作 |
| POST | `/api/agent/chat` | `agent_chat` | 主入口 |
| POST | `/api/agent/inbox/upload-folder` | `upload_agent_inbox_folder` | proposal |

## 8. 数据库依赖

Agent 读取以下表（全部按 `owner_user_id` 过滤）：

| 表 | Agent 用途 | 层级 |
|----|-----------|------|
| `bib_entries` | 元数据、摘要、DOI、关键词、用户笔记 | P0/P1 |
| `reading_items` | AI 精读条目 | P2 |
| `reading_item_edits` | 人工编辑后的精读条目 | P1 |
| `annotations` | 批注（人工 P1 / AI P2） | P1/P2 |
| `card_notes` | 卡片笔记 | P1 |
| `bib_references` | 参考文献原文 | P0 |
| `bib_reference_citations` | 引用原文 | P0 |
| `files` | 原文文件（Markdown 窗口检索） | P0 |
| `agent_sessions` | Agent 会话 | 会话数据 |
| `agent_messages` | Agent 消息历史 | 会话数据 |
| `agent_action_proposals` | Agent 操作提案 | 会话数据 |
| `jobs` | 任务状态 | 直接查询 |
| `artifacts` | 产物链接 | 直接查询 |

## 9. 测试覆盖

### `test_agent_tool_registry.py`

| 测试 | 验证内容 |
|------|---------|
| `test_registry_exposes_permission_metadata` | research_search 是 read_local、start_reading 是 propose_write 且 writes_database |
| `test_openai_tool_schemas_include_research_tools` | TOOL_SCHEMAS 包含 research_search、get_evidence_pack、get_source_windows、search_cnki、lookup_english_fulltext |
| `test_external_tools_are_marked_as_internet_reads` | search_cnki 和 lookup_english_fulltext 是 external_read + consent_required + uses_internet |
| `test_capability_matrix_is_serializable` | list_tool_capabilities() 可序列化且不含 handler |

### `test_research_retrieval.py`

| 测试 | 验证内容 |
|------|---------|
| `test_research_search_ranks_source_tiers_and_keeps_user_data_isolated` | P0 排在 P1 前面；其他用户数据不泄露 |
| `test_get_evidence_pack_prefers_edited_notes_over_ai_reading_items` | P1 edited_reading_item 排在 P2 reading_item 前面 |

## 10. 当前限制与后续规划

### 已知限制

- **联网授权仍未完成真正票据化**：search_cnki / lookup_english_fulltext 已有 runtime 提示与拦截，但还没有独立 `external_consent_ticket`
- **Runtime 仍是轻量编排，不是完整状态机**：已有 TaskFrame、Continuation Resolver、Budget Policy、Stop Summary，但尚未实现完整的 understand → retrieve_local → assess_sufficiency → consent → synthesize 状态机
- **API 工具覆盖仍不全**：compare/synthesis、reference trace、translation、cards、annotations、dimensions 等端点尚未全部包装为 agent 工具
- **证据分层 UI 仍待增强**：前端已有工作记忆、工作笔记、工具轨迹、analysis_cache 摘要，但还没有完整 tier badge 与 evidence pack table

### 后续 Phase（见设计方案）

| Phase | 内容 | 状态 |
|-------|------|------|
| Phase 2 | Agent 规划层（research_agent_runtime.py） | 部分完成 |
| Phase 3 | 全量 API 工具覆盖 | ⬜ |
| Phase 4 完整 | 运行时 consent 拦截 + save_external_note | ⬜ |
| Phase 5 | 前端 UI（tier badges / 联网确认 / 证据表格） | 部分完成 |
| Phase 6 | source_text_chunks 表 + FTS5（按需） | ⬜ |

## 11. 2026-05-28 增量实现

### 11.1 Runtime 规划层

- `backend/services/research_agent_runtime.py` 已接入 `TaskFrame`、`Continuation Resolver`、`Budget Policy`、`Runtime Notice`、`Stop Summary`。
- 已支持数量类问题优先走 `count_library`，避免枚举标题。
- 已支持大集合分类问题优先走 `analyze_reading_candidates`，并在 SSE 中流式返回 `analysis_progress`。
- 已支持把结构化 `working_notes`、`last_analysis_summary`、`last_result_set`、`analysis_cache` 写回 `AgentSession.last_state_json`。

### 11.2 批量分析与分析缓存

- `backend/services/reading_candidate_analysis.py` 现在会对文献生成论文级标注结果，包含：
  - `cluster_labels`
  - `priority_score`
  - `journal_quality`
  - `local_rule_reasons`
- 新增 `analysis_cache` 概念：一次全量或子集分析完成后，把论文级标注结果持久化到会话状态，供下一轮继续复用。
- 新增 `filter_analysis_cache` 工具：支持按期刊层级、主题聚类、全文可用性、`reading_status` 在上一轮缓存上继续筛选，不重新扫描全库。
- 当前 continuation 语义已扩展到“专注看 / 只看 / 聚焦 / 顶刊 / UTD 24 / Top 5”等子集追问。

### 11.3 期刊质量与主题聚类

- `backend/services/journal_quality_kb.py` 已把提示词中的顶刊名录沉淀为运行时知识库。
- 批量分析排序不再只看题名，而是综合：
  - 期刊质量命中
  - 元数据完整度
  - 是否有全文
  - 被引次数
  - 年份新近性
- 主题分类已从“首词聚类”升级为规则词典 + 同义词归并，能合并 `GenAI / Generative AI`、`Climate Change / climate change`、`LLM / ChatGPT` 等变体。

### 11.4 前端会话态展示

- `frontend/src/App.tsx` 已展示：
  - 最近一次批量分析
  - 最近工作笔记
  - 最近工具轨迹
  - 当前工作记忆
  - 当前分析缓存摘要（cache_id、source_scope、父缓存/复用来源）
- 这使用户能直接看到当前回答是否基于上一轮缓存继续收窄，而不是只能依赖后台日志判断。

### 11.5 新增回归测试

- `backend/tests/test_research_agent_runtime.py`
  - 覆盖 `analyze_cached_collection` intent
  - 覆盖 `filter_analysis_cache` 参数归一化
  - 覆盖 `prefer_analysis_cache_filter` 与 `analysis_cache_required`
  - 覆盖 `analysis_cache_summary` UI 摘要写回
- `backend/tests/test_reading_candidate_analysis.py`
  - 覆盖 analysis_cache 子集过滤
  - 覆盖 `max_entries` 截断
- `backend/tests/test_agent_tool_registry.py`
  - 校验 `filter_analysis_cache` 已进入工具 schema

---

## 12. Sprint 1 实施记录（2026-05-31）

### 12.1 错误枚举体系

- 新建 `backend/services/agent_errors.py`：
  - `AgentErrorCode`：17 种错误码（LLM 6 种 + 工具/运行时 4 种 + 业务 7 种）
  - `ErrorStage`：7 个阶段枚举
  - `RuntimeNoticeCode`：13 种 runtime 通知子码
  - `RUNTIME_NOTICE_TO_ERROR_CATEGORY`：子码 → 父类别映射表
  - `make_agent_error_payload()`：统一 payload 工厂函数
- 改造 `routers/agent.py`：
  - `_structured_agent_error` 委托给 `make_agent_error_payload`
  - `classify_agent_exception` 全部 14 处硬编码替换为 `AgentErrorCode` 枚举
  - `filter_analysis_cache` 内部错误替换为 `RuntimeNoticeCode` 枚举
- 改造 `research_agent_runtime.py`：
  - `enforce_tool_policy` 全部 10 处硬编码替换为 `RuntimeNoticeCode` 枚举
  - 枚举 `.value` 与原字符串完全一致，零破坏性变更

### 12.2 前端错误差异化展示

- `getAgentErrorStyle()`：按错误类型返回图标 + 差异化颜色
  - 红：auth/key 错误 → 🔑
  - 橙：connection/timeout/tool → 🔌⏱️🔧
  - 黄：rate_limit/budget → 🚦🔋
  - 蓝：consent → 🔐
- `AgentErrorCard` 增强：图标 + 颜色差异化 + 新错误码标题
- `AgentRuntimeNoticeCard` 改为 `<details>` 可折叠（warning 默认折叠，error 默认展开）

### 12.3 Tool Trace 摘要增强

- `AgentToolTraceCard` 新增统计行：N 次命中 / M 次空结果 / K 次被策略拦截
- `getRuntimeNoticeTitle` 补充 4 个 runtime notice code 的中文标题

### 12.4 AI 助手 MD 渲染修复与增强

- 修复：`AgentEventBody` 中 answer 类型检查提前到 JSON 解析之前，避免被 `tryParseJson` 兜底拦截
- 样式增强（`index.css` `.agent-md-content`）：
  - h1：深绿色 + 底部渐变线
  - h2：深绿色 + 左侧竖线
  - strong：紫红色 `#9f1239`
  - em：紫色 `#7c3aed`
  - code：暖黄底 + 琥珀色字
  - table：绿色渐变表头 + 斑马纹 + hover 高亮 + 圆角
  - blockquote：渐变绿底 + 斜体
  - a：虚线下划线 + hover 变实线

### 12.5 验证结果

- 后端编译通过，39 项单测全绿
- 前端 TypeScript 编译 + Vite 构建通过
- 已部署到 http://8.162.14.154:18080/ 并验证首页 200、runtime 200

## 13. 2026-06-02 上传文件夹入口线上修复

### 13.1 故障现象

- AI 助手「上传文件夹」请求 `/api/agent/inbox/upload-folder` 在线上返回 500。
- 前端只显示“上传失败 connection”，但后台日志显示真实原因在数据库 flush 顺序和参数类型。

### 13.2 根因

- `_persist_inbox_upload()` 调用 `bind_uploaded_file_to_existing_bib()` 时传入了 `User` ORM 对象；该函数实际需要 `user_id: int`。
- `upload_agent_inbox_folder()` 创建 `UploadBatch` 后未先 flush，PostgreSQL 插入 `files.batch_id` 时可能找不到父批次。
- `File` 记录未先 flush 就更新匹配到的 `BibEntry.source_file_id` / `markdown_source_file_id`，PostgreSQL 会检查到目标 `files.id` 尚不存在。

### 13.3 修复

- `backend/routers/agent.py`
  - 创建 `UploadBatch` 后立即 `await db.flush()`。
  - `_persist_inbox_upload()` 里先 `db.add(record)` + `await db.flush()`，再绑定已有文献。
  - 绑定文献库时调用 `bind_uploaded_file_to_existing_bib(db, user.id, record)`。
- `backend/tests/test_library.py`
  - 新增上传文件夹回归测试，断言 batch、file、匹配 BibEntry 绑定都成功。

### 13.4 验证

- `python -m py_compile backend\routers\agent.py backend\routers\upload.py backend\tests\test_library.py`
- `python -m unittest backend.tests.test_library`
- 已手动 SCP 到 `/root/deep-reading-agent/backend/routers/agent.py` 并通过 `systemctl restart deepreading-api` 部署。

