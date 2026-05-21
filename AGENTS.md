# AGENTS.md

Deep Reading Agent — 多用户学术论文在线精读工作台。用户上传 PDF/Markdown，系统调用 DeepSeek 完成文献筛选、精读（七步/四步/长文本）、对比综述、参考文献提取，结果存入文献库。

## 快速命令

```powershell
# 后端
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000

# 前端
cd frontend && npm install && npm run dev

# 单测
python -m unittest backend.tests.test_queue_manager

# 全量构建
cd frontend && npm run build
```

部署：`git push origin online` → Webhook 触发服务器自动拉代码重启；数据库迁移需 SSH 手动 `alembic upgrade head`。

## 架构

```
frontend/ (React 19 + Vite + Tailwind + Zustand)
  src/RootApp.tsx       — 路由守卫、登录注册
  src/App.tsx           — 工作台壳（Tab导航、FilterTab/LongTab/QuantTab/QualTab/HistoryTab/PromptsTab/TranslationTab）
  src/LibraryTab.tsx    — 文献库页面
  src/TranslationTab.tsx — 全文翻译（中文重述）页面
  src/components/CompareView.tsx — 对比综述主组件（替代 iframe）
  src/components/compare/ — 对比子组件（AnswerCard/AccordionPanel/PaperSelector/DimNavigation/SynthesisModal）
  src/store/auth.ts     — Zustand 登录态
  src/lib/api-fetch.ts  — 全局鉴权 fetch（自动 refresh token）

backend/ (FastAPI + SQLAlchemy 2.0 async + SQLite)
  main.py               — FastAPI 入口、路由注册、启动初始化
  routers/              — auth|upload|filter|reading|compare|library|history|download|prompts|references|admin|translation
  db/models.py          — ORM 模型（User|File|BibEntry|Job|ReadingItem|Artifact|PromptTemplate）
  db/session.py         — 异步引擎 + get_db 依赖
  prompt_registry.py    — 提示词槽位注册表
  prompt_service.py     — 提示词解析服务（用户覆盖 > 系统默认 > 文件兜底）
  services/queue_manager.py — 任务队列（排队、并发控制、预估等待）
  services/deepseek_refs.py — 参考文献提取（pdfplumber + DeepSeek）
  auth/                 — JWT 鉴权（access/refresh token）
  utils/api_key.py      — 统一 DeepSeek Key 验证
  migrations/           — Alembic 迁移脚本

new_architecture/
  conversation_engine.py — 长文本/七步/四步 LLM 对话引擎

translation_pipeline.py  — 全文翻译流水线（PDF 全文两步 / Markdown 分片六步）
```

## 核心数据流

```
上传 PDF/MD → files 表 → BibEntry 匹配/创建
筛选题录 → Job(filter) → BibEntry + BibFilterLink → Artifact(filter_excel)
精读     → Job(reading_*) → ReadingItem + Artifact(reading_final) → 自动提取参考文献
批量精读 → POST /batch/start → 多个 Job(reading_*, 共享 batch_id) → GET /batch/{batch_id}/status 轮询进度
对比综述 → 从 ReadingItem 聚合 → Job(compare) → Artifact(compare_md/synthesis_md)
AI综述  → /synthesis 或 /synthesis_long → 串行逐维度 deepseek-v4-flash → Artifact(synthesis_md) + GB/T 7714 参考文献
全文翻译 → POST /translation/start → Job(translation) → Artifact(translation_md + translation_glossary) → 关联 BibEntry
文献库   → BibEntry 聚合展示（关联筛选评分、精读结果、时间线产物）
```

关键表：`bib_entries` 是业务枢纽，筛选/精读/对比/文献库围绕它组织。

## 关键约定

- **API Key**：Web 模式下前端传用户自己的 DeepSeek Key，后端不读 .env 兜底。Key 按用户名隔离存 localStorage。
- **认证**：JWT（access + refresh token），401 时前端自动 refresh，失败跳登录页。
- **提示词优先级**：用户覆盖 > 系统默认 > 文件兜底 > 代码硬编码。
- **数据库变更**：必须同步 `backend/db/models.py` + Alembic migration + `docs/DATABASE_SCHEMA.md`。
- **用户数据表变更**：凡是新增/修改与用户数据相关的表，必须同步检查 `backend/services/data_portability.py`：
  - `CURRENT_SCHEMA_VERSION` 必须与最新 migration 编号一致；
  - 新增用户数据表必须加入 `.dra` 导出/导入顺序，或在代码/文档中明确说明为什么排除；
  - 涉及自增主键或跨表引用时，必须补充导入时的 id remap 逻辑。
- **任务类型**：filter / reading_long / reading_quant / reading_qual / compare / synthesis / reference / translation。
- **产物类型**：filter_excel / reading_final / compare_md / synthesis_md / references_excel / translation_md / translation_glossary 等。
- **角色**：admin / vip / normal，normal 用户数据 24h 过期自动清理。
- **LLM**：精读用 deepseek-reasoner，分类/筛选/对比/AI综述/翻译用 deepseek-v4-flash，参考文献用 deepseek-v4-flash。
- **文本上限**：150k 字符（超出中间截断）。
- **PDF 提取**：PaddleOCR 优先（需远程 API），自动回退 pdfplumber。
- **输出 Markdown**：含 YAML frontmatter，兼容 Obsidian Dataview。

## 本地开发与验证

**一键启动**：`.\start-dev.ps1` — 自动在新窗口启动后端(8000)和前端(5173)并打开浏览器。

手动启动：
1. 激活 venv → `pip install -r requirements.txt`
2. 启动后端 `uvicorn backend.main:app --reload --port 8000`
3. 启动前端 `cd frontend && npm run dev`
4. 前端 dev server 默认 5173，Vite proxy 转发 `/api` 到后端 8000
5. 注册/登录 → 设置 API Key → 上传 PDF → 选精读模式 → 查看结果

## 质量检查

```powershell
cd frontend && npm run lint && npm run build   # 前端检查
python -m unittest backend.tests.test_queue_manager  # 后端单测
```

推送前确保：lint 通过、构建通过、本地功能正常。自动部署直接上线，无 staging 环境。

## 开发工作流约束

- 用户要求“先分析/先规划”时，必须先输出分析与实施规划，不得直接改代码。
- 涉及数据库、导入导出、分支回灌、核心业务流程的改动，默认先规划，等用户确认后再实施。
- 代码改完后先只做验证和简要说明；必须等用户本地测试成功后，才写技术文档、经验教训总结。
- 技术文档、复盘、经验教训统一存放到 `docs/`，并同步更新 `docs/README.md` 或项目 README 的文档导航。
- 不要在功能未验证前把文档写成“已完成”。

**⚠️ 编辑大文件时（尤其 FastAPI router），替换完务必检查路由注册是否完整**：用 `python -c "from routers.xxx import router; [print(r.path) for r in router.routes]"` 验证所有端点都在。曾有替换 `apply_match` 时误将 `match_online` 路由定义连带删掉的事故。

**⚠️ 新增独立 CSS 文件时，严禁使用全局选择器**：
- 禁止 `*, *::before, *::after { margin: 0; ... }` 等 CSS reset（会清零整个应用的 Tailwind 排版）
- 禁止 `:root { --var: ... }` 声明（会污染全局 CSS 变量）
- 禁止不带作用域的 `.btn`、`.action-bar` 等通用类名（会与其他页面冲突）
- **必须**用一个顶层 class（如 `.compare-root`）包裹所有样式，写成 `.compare-root .btn { ... }`
- 所有 keyframes 也加前缀（如 `compare-spin`）避免冲突
- 历史事故：`compare.css` 的全局 reset 导致整个前端排版崩溃（2026-05-14）

## 改代码优先看的文件

| 改什么 | 先看 |
|--------|------|
| 登录/注册/权限 | `RootApp.tsx` `auth.ts` `api-fetch.ts` `routers/auth.py` |
| 上传/文件绑定 | `routers/upload.py` `db/utils.py` |
| 题录筛选 | `routers/filter.py` `App.tsx FilterTab` |
| 精读 | `routers/reading.py` `conversation_engine.py` `App.tsx *Tab` |
| 批量精读 | `routers/reading.py`（`start_batch_reading` / `get_batch_status`） `App.tsx`（`useBatchReadingTracker`） |
| 对比综述 | `CompareView.tsx` `compare/` 子组件 `compare.css` `routers/compare.py` |
| AI综述 | `routers/compare.py`（synthesize_dimensions/synthesize_long_dimensions） |
| 文献库 | `routers/library.py` `LibraryTab.tsx` |
| 提示词 | `prompt_registry.py` `prompt_service.py` `routers/prompts.py` |
| 参考文献 | `services/deepseek_refs.py` `routers/references.py` |
| 任务队列 | `services/queue_manager.py` |
| 全文翻译 | `routers/translation.py` `translation_pipeline.py` `TranslationTab.tsx` |

## 文档导航

| 文档 | 内容 |
|------|------|
| `docs/TECHNICAL_OVERVIEW.md` | 系统功能、代码结构、数据模型、修改记录（最全面） |
| `docs/STATE_AND_API_MAP.md` | 前端状态↔API↔数据库全链路映射 |
| `docs/FUNCTION_INDEX.md` | 按文件列关键函数索引 + 常见问题速查 |
| `docs/DATABASE_SCHEMA.md` | 数据库 ER 图、表结构、字段定义 |
| `docs/DEPLOYMENT_ARCHITECTURE.md` | 本地→GitHub→服务器部署链路 |
| `docs/OPS_HEALTHCHECK_GUIDE.md` | 服务器健康检查与自动恢复 |
| `docs/PENDING_PLANS.md` | 未实施的方案与待办 |
| `docs/TRANSLATION_INTEGRATION_PLAN.md` | 全文翻译功能集成规划 |
