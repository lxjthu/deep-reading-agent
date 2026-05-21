# 知识库问答与自动综述写作模块

## Summary
- 当前数据库为 Alembic `012_add_dimension_set_reading_availability`，SQLite `3.51.0` 已启用 FTS5，现有核心数据为 `bib_entries`、`files`、`reading_items`、`artifacts`、`bib_references`、`bib_reference_citations`。
- 新模块采用“派生全文索引 + 可追踪探索会话”设计：把全文、精读结果、参考文献、引用命中、注释、历史产物全部切片进入 SQLite FTS5；问答和综述写作通过 LLM 生成结构化查询 DSL，由后端编译为只读 SQL/FTS。
- 递归检索作为主动探索循环：每轮审视已知信息、提出证据缺口、生成新查询、吸收新片段、判断继续或停止。

## Key Changes
- 新增知识索引表：
  - `knowledge_documents`：用户级索引源，关联 `bib_entries/files/artifacts/reading_items/bib_references/bib_reference_citations/annotations`，记录 `source_kind`、标题、hash、状态、是否可作为正式引用。
  - `knowledge_chunks`：可检索片段，含 `document_id`、`bib_entry_id`、`section_path`、`page_label`、`char_start/end`、`content`、`metadata_json`、`content_hash`。
  - `knowledge_chunks_fts`：FTS5 virtual table，使用 `tokenize=trigram`，配套 insert/update/delete triggers，适配中英文混合检索。
- 新增探索持久化表：
  - `knowledge_sessions`：一次问答或综述写作会话，保存问题、模式、范围、最终答案、状态、关联 `job_id`。
  - `knowledge_steps`：每轮递归检索的已知信息、缺口、查询计划、执行摘要、模型判断。
  - `knowledge_evidence`：证据片段引用，保留 `chunk_id` 和快照，导入导出后即使重建索引也能查看历史证据链。
- 扩展现有约束：
  - `jobs.job_type` 增加 `knowledge_index`、`knowledge_qa`、`literature_review`。
  - `artifacts.artifact_type` 增加 `knowledge_answer_md`、`literature_review_md`、`knowledge_trace_json`。
  - `prompt_templates.prompt_type` 增加 `knowledge`。
  - `job_bib_entries.role` 增加 `knowledge_scope_member`，仅记录用户显式选择的范围文献。
- 同步 `backend/db/models.py`、Alembic `013_add_knowledge_fts.py`、`docs/DATABASE_SCHEMA.md`、`backend/services/data_portability.py`；索引缓存表可从源数据重建，`.dra` 默认排除 `knowledge_documents/chunks/fts`，但导出 `sessions/steps/evidence` 及证据快照。

## Retrieval And Writing Flow
- 索引来源覆盖“全文 + 全部产物”：
  - `bib_entries` 元数据、摘要、标签、笔记。
  - 上传 PDF/Markdown/TXT/DOCX 的提取文本；优先复用已有提取产物，缺失时后台补建。
  - `reading_items` 精读结构化结果。
  - `artifacts` 中的 Markdown、JSON、Excel/CSV 可读文本。
  - `bib_references`、`bib_reference_citations`、用户 `annotations`。
- 后端新增 `backend/services/knowledge_indexer.py`、`knowledge_search.py`、`knowledge_agent.py`：
  - 索引器按源 hash 幂等重建，800-1200 字符切片，约 150 字符 overlap，按 `content_hash` 去重。
  - LLM 只输出结构化 DSL：关键词、短语、必须/可选/排除词、来源类型、年份、文献范围、limit、查询目的。
  - 后端强制注入 `owner_user_id`、白名单字段、绑定参数、limit、超时和只读查询；不执行 LLM 原始 SQL。
- 递归检索循环：
  - 默认最多 4 轮，每轮最多 3 个查询、每查询最多 8 个片段。
  - LLM 先输出“已知事实、证据缺口、新查询、是否停止”。
  - 后端执行 FTS/SQL，去重并让 LLM 对新证据标注 `support/refute/background/method/gap`。
  - 若无新证据、缺口已闭合、达到轮数/证据/token 上限或用户取消，则进入最终回答。
- 文献综述写作：
  - 先做主题探索和证据图谱，再生成大纲。
  - 每个章节可再次定向递归检索。
  - 正文只能引用证据 ID；参考文献目录由 `bib_entries/bib_references` 程序化生成，不让 LLM 编造。
  - 历史综述/对比产物可作为线索来源，但默认不可作为正式文献引用。

## API And UI
- 新增 `backend/routers/knowledge.py` 并在 `main.py` 注册 `/api/knowledge`。
- API：
  - `POST /api/knowledge/index/rebuild`：按全部/选中文献/变更源重建索引。
  - `GET /api/knowledge/index/status`：返回已索引、过期、失败、chunk 数。
  - `POST /api/knowledge/search`：调试用只读检索。
  - `POST /api/knowledge/qa/stream`：SSE 输出 round、query、evidence、reflection、final。
  - `POST /api/knowledge/review/stream`：SSE 输出探索、证据图谱、大纲、章节、最终 Markdown。
  - `GET /api/knowledge/sessions`、`GET /api/knowledge/sessions/{id}`：查看历史问答/综述和证据链。
- 前端新增 `KnowledgeTab`：
  - 左侧范围与索引状态，支持全库、选中文献、标签/年份/期刊过滤。
  - 主区支持知识库问答和自动综述写作两个模式。
  - 右侧展示递归探索轨迹：每轮已知信息、缺口、生成查询、命中文献片段。
  - 最终答案中的引用可点击定位到文献、精读项、产物或引用片段。

## Test Plan
- 数据库：
  - 升级现有 `012` 数据库到 `013`，确认新表、FTS virtual table、triggers、CHECK 约束可用。
  - 删除源 `bib_entry/artifact/reading_item` 后，相关 chunks 与 FTS 记录同步清理。
- 索引：
  - 对 `bib_entries`、`reading_items`、Markdown artifact、Excel artifact、参考文献、引用命中分别做幂等索引测试。
  - 修改源内容后只重建过期文档，不重复生成 chunks。
- 检索安全：
  - DSL 编译拒绝未知字段、写 SQL、超大 limit、跨用户 `bib_entry_id`。
  - FTS 查询始终绑定当前用户，不能检索其他用户数据。
- 递归代理：
  - Mock LLM 返回多轮缺口和查询，验证停止条件、去重、证据快照、最终引用校验。
  - Mock 无新证据场景，验证优雅停止并说明证据不足。
- 端到端：
  - `python -m unittest backend.tests.test_queue_manager`。
  - 新增知识库相关 unittest。
  - `cd frontend && npm run lint && npm run build`。
  - 本地手测：全库重建索引 → 多跳问答 → 查看证据链 → 生成综述 Markdown → 文献库历史可见。

## Assumptions
- 首版使用 DeepSeek `deepseek-v4-flash`，沿用前端用户 API Key，不增加后端 `.env` 兜底。
- 首版不引入向量库或 embedding，只用 SQLite FTS5 + 元数据过滤 + LLM 规划/裁判/写作。
- “全部产物”都会进入检索，但只有原文、精读、参考文献、引用命中等一手或结构化证据默认可作为综述正式引用。
