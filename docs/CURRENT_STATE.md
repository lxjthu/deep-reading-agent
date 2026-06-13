# 当前状态

> 最后更新：2026-06-13
>
> 本文件是进入项目时的“先相信这个”入口。它只记录当前分支、线上环境、已实现边界和高风险约束；
> 更完整的文档目录与维护规范见 [`INDEX.md`](INDEX.md)。

## 1. 项目定位

Deep Reading Agent 是一个多用户学术论文在线精读工作台。核心流程是：

```text
上传 PDF/Markdown
→ 题录筛选与文献库绑定
→ 长文本 / 七步 / 四步精读
→ 对比综述、AI 综述、参考文献提取、全文翻译
→ 结果沉淀到文献库与历史产物
```

当前线上重点不是单机打包版，而是生产连接分支上的 Web 工作台。

## 2. 当前分支与线上环境

| 项目 | 当前值 |
|---|---|
| 工作分支 | `codex/deepreading-empty-postgres-deploy` |
| 线上地址 | `http://8.162.14.154:18080/` |
| 部署方式 | 手动 SCP 上传改动 + `systemctl restart deepreading-api` |
| 自动部署 | 不走 `online` 分支 Webhook |
| 生产数据库 | PostgreSQL `deepreading` |
| 服务器项目目录 | `/root/deep-reading-agent` |
| 主要部署手册 | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) |

生产服务依赖 systemd 加载 `.env.production`。不要用手动 `nohup uvicorn` 替代 systemd，否则容易丢失 PostgreSQL 配置并回退到错误环境。

## 3. 当前架构事实

| 层 | 当前事实 |
|---|---|
| 前端 | React 19 + Vite + Tailwind + Zustand |
| 后端 | FastAPI + SQLAlchemy 2.0 async |
| 线上数据库 | PostgreSQL |
| 本地/历史文档 | 部分旧文档仍保留 SQLite 或打包版语境，阅读时需核对当前代码 |
| 任务队列 | `backend/services/queue_manager.py` 负责排队、并发控制、状态预估 |
| AI 助手 | 已有持久 session、工具注册、proposal-only 写操作、基础 runtime state 和 evidence/sufficiency 能力 |
| Research Agent 下一步 | 继续 runtime-first 路线，优先显式状态机、证据排序、可解释 sufficiency 和本地证据优先 |

## 4. 已实现主线

| 主线 | 当前状态 | 入口文档 |
|---|---|---|
| 多用户登录、角色、数据隔离 | 已实现，仍需按生产约束维护 | [`MULTIUSER_PROGRESS.md`](MULTIUSER_PROGRESS.md)、[`TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md) |
| 文献库与题录绑定 | 已实现，持续有附件、Markdown 挂载、重复匹配等增强 | [`STATE_AND_API_MAP.md`](STATE_AND_API_MAP.md)、[`MARKDOWN_MOUNT_REFRESH_FIX_2026-06-01.md`](MARKDOWN_MOUNT_REFRESH_FIX_2026-06-01.md) |
| 长文本 / 七步 / 四步精读 | 已实现，批量与并发稳定性持续优化 | [`FUNCTION_INDEX.md`](FUNCTION_INDEX.md)、[`PENDING_PLANS.md`](PENDING_PLANS.md) |
| 对比综述与卡片操作 | 已实现 AnswerCard 编辑、点评、AI 总结等能力 | [`COMPARE_CARD_ACTIONS_IMPL.md`](COMPARE_CARD_ACTIONS_IMPL.md) |
| 参考文献提取与引用追踪 | 主链路已实现，双栏 PDF 和引用追踪仍有历史方案/修复记录 | [`REFERENCE_CITATION_TAB_PLAN.md`](REFERENCE_CITATION_TAB_PLAN.md)、[`REFERENCE_CITATION_DEEPSEEK_FLASH_PLAN.md`](REFERENCE_CITATION_DEEPSEEK_FLASH_PLAN.md) |
| 全文翻译 | 已集成中文重述翻译入口和产物链路 | [`TRANSLATION_INTEGRATION_PLAN.md`](TRANSLATION_INTEGRATION_PLAN.md) |
| 用户数据导出/导入 | 已实现 `.dra`，PostgreSQL 语境下仍有重构计划 | [`POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md`](POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md) |
| Research Agent Phase 1 / 1.5 | 已实现并作为后续路线基础 | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) |

## 5. 当前未完成或高优先级风险

| 事项 | 当前判断 | 入口 |
|---|---|---|
| Research Agent 显式状态机 | 未完成；`agent_chat` 仍主要围绕 LLM tool calls 循环 | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) |
| Evidence pack 排序和写作风格分析工具 | 已有计划，待实施或继续验证 | [`docs/superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md`](superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md) |
| PostgreSQL FTS / `pg_trgm` | 作为生产方向规划；不要把旧 SQLite FTS5 表述当成当前目标 | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) |
| 双 `routers/` 目录 | 生产部署陷阱；改 `backend/routers/filter.py`、`reading.py`、`references.py`、`translation.py` 时必须同步根目录副本 | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) |
| Alembic 跑错库 | 高风险；生产迁移必须确认 PostgreSQL 目标库和 current/head | [`PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md`](PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md) |
| 前端静态资源未覆盖 | 高风险；前端改动需要构建并上传 `frontend/dist` | [`JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md`](JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md) |
| `PENDING_PLANS.md` 中旧条目 | 混有已完成、待实施、历史说明；执行前必须回查代码 | [`PENDING_PLANS.md`](PENDING_PLANS.md) |

## 6. 开发与部署原则

1. 涉及数据库、导入导出、核心业务流、线上部署时，先规划再实施。
2. 简单 UI 或文案修复可以小步直接改，但仍要验证构建或关键路径。
3. 每次改代码后先做验证和简要说明；等用户本地测试成功后，再写技术文档、复盘或经验教训。
4. 线上部署必须走手动部署手册，不要推 `online` 分支期待 Webhook。
5. 改 FastAPI router 后，检查路由注册是否完整，避免误删端点。
6. 新增独立 CSS 文件必须加顶层作用域，禁止全局 reset、`:root` 污染和通用类名污染。
7. PowerShell 处理中文 Markdown 时显式使用 UTF-8。

## 7. 快速入口

| 我要做什么 | 入口 |
|---|---|
| 快速了解系统 | [`TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md) |
| 查函数在哪 | [`FUNCTION_INDEX.md`](FUNCTION_INDEX.md) |
| 查状态/API/数据库链路 | [`STATE_AND_API_MAP.md`](STATE_AND_API_MAP.md) |
| 改数据库 | [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) |
| 部署上线 | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) |
| 上线前逐项检查 | [`PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md`](PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md) |
| 排查线上错误 | [`TROUBLESHOOTING_SERVER_ERRORS.md`](TROUBLESHOOTING_SERVER_ERRORS.md) |
| 继续 Research Agent | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) |
| 查全部文档规范 | [`INDEX.md`](INDEX.md) |
| 查旧全量目录 | [`README.md`](README.md) |

## 8. 使用提醒

`docs/` 里有大量历史方案，它们很有价值，但不一定代表当前系统。执行前请用当前代码、测试、线上部署手册和最近验证记录交叉确认。
