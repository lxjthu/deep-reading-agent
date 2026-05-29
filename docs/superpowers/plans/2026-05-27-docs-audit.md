# Docs 审计结果（2026-05-27）

## 审计完成

3 个子代理并行核查 63 篇文档，已完成。

## 需要更新的文档（共 13 篇）

### 优先级 A — 核心参考文档（误导风险最高）

| # | 文档 | 主要问题 |
|---|------|----------|
| 1 | `DATABASE_SCHEMA.md` | 第11行"SQLite 3"→应注明生产用 PostgreSQL；第17-18行备份策略过时；第1298行 SQLite WAL 仅适用本地；版本号需更新 |
| 2 | `NEW_SERVER_SQL_MAINTENANCE.md` | 第87行 nohup uvicorn → systemctl；缺少 systemd service 路径说明 |
| 3 | `DATABASE_DEPLOY_AND_MIGRATION_GUIDE.md` | 路径 `/root/.openclaw/workspace/` 过时；部署方式仍写 Webhook 自动部署；大量 SQLite 内容需标注范围 |
| 4 | `TECHNICAL_OVERVIEW.md` | job_type 缺 `translate_abstracts/library_chat/ref_format`；artifact_type 缺 `library_chat_md/ref_format_md`；关键模型列表缺新增模型 |
| 5 | `README.md` | 描述需补充 PostgreSQL + systemd 信息 |

### 优先级 B — 运维/故障文档（排查时会用）

| # | 文档 | 主要问题 |
|---|------|----------|
| 6 | `OPS_HEALTHCHECK_GUIDE.md` | **需重写**：整篇基于旧架构（nohup/start.sh/端口5173/Cloudflare Tunnel） |
| 7 | `TROUBLESHOOTING_SERVER_ERRORS.md` | sqlite3 命令、/tmp/fastapi.log、bash start.sh 全部过时 |
| 8 | `DIAGNOSIS_2026-05-26_MULTI_SYSTEM_FAILURE.md` | asyncio.run() 已修复需标注；sqlite3 路径错误；日志路径过时 |
| 9 | `INCIDENT_2026-05-06_LIBRARY_502.md` | /tmp/fastapi.log、bash start.sh、健康检查方案过时 |
| 10 | `CONCURRENCY_ANALYSIS.md` | 全篇基于 SQLite，PostgreSQL 已迁移完成 |
| 11 | `FIX_LIBRARY_CHAT_SAVE_500.md` | 纯 SQLite 修复记录，需加历史标注 |
| 12 | `MULTIUSER_PROGRESS.md` | sqlite3 命令、服务器路径、部署方式过时 |

### 优先级 C — 功能规划文档（3 篇需小改）

| # | 文档 | 主要问题 |
|---|------|----------|
| 13 | `PENDING_PLANS.md` | P9 对比页三按钮已实施但状态未更新 |
| 14 | `SYNTHESIS_PROMPT_PLAN.md` | P3 提示词管理部分状态不清晰 |
| 15 | `MIGRATION_PLAN_10PLUS_USERS.md` | PostgreSQL 已迁移，SQLite 相关内容需标注 |

## 无需更新的文档（共 48 篇）

### P0 核心（2 篇无需改）

- `STATE_AND_API_MAP.md` — 基本准确，小修即可
- `FUNCTION_INDEX.md` — 基本准确

### P1 运维（2 篇无需改）

- `FIX_PG_FLUSH_ORDER_500.md` — 已是 PostgreSQL 视角
- `API_KEY_FLOW_FIX.md` — 修复已落地，引用有效

### P2 功能规划（44 篇无需改，37 篇已完成 + 5 篇待办 + 2 篇小改）

**已完成（37 篇）**：
- CONCURRENT_DIMENSION_READING_PLAN.md
- PACKAGING_GUIDE.md
- CHUNKED_DATA_IMPORT_IMPL.md
- ADMIN_USAGE_FEEDBACK_PLAN.md
- AGENT_SESSION_CONFIRMATION_UI_PLAN.md
- AGENT_ASSISTANT_IMPL.md
- LIBRARY_AI_CHAT_IMPL.md
- 卡片笔记PLAN.md
- TRANSLATION_INTEGRATION_PLAN.md
- TRANSLATION_FULLTEXT_PDF_RESTATE_PLAN.md
- SYNTHESIS_PROMPTS_GUIDE.md
- SYNTHESIS_CURRENT_DESIGN.md
- COMPARE_SYNTHESIS_SELECTION_PLAN.md
- READING_FILTER_PROMPTS_GUIDE.md
- REF_FORMAT_GENERATION_DESIGN.md
- PLAN_TEMPLATE_MARKET_DIM_EDIT.md
- COMPARE_CARD_ACTIONS_IMPL.md
- BATCH_AND_COMPARE_IMPROVEMENTS.md
- BATCH_CONFLICT_CHECK_PLAN.md
- SKIP_DUPLICATE_EXTRACTION.md
- CUSTOM_DIMENSION_PLAN.md / PHASE1 / PHASE2 / PHASE2_DESIGN / PHASE3
- CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md
- CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md
- PDF_METADATA_READING_FIX_PLAN.md
- PDF_METADATA_MATCH_PLAN.md
- REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md
- REFERENCE_CITATION_DEEPSEEK_FLASH_PLAN.md
- REFERENCE_CITATION_TAB_PLAN.md
- TWO_COLUMN_PDF_FIX.md
- TESTSET_AND_P2_PLAN.md
- MULTI_USER_PLAN.md
- PROMPT_MANAGEMENT_PLAN.md
- LIBRARY_SOURCE_TRANSLATION_PLAN.md
- 2026-05-07-bib-dedup-overwrite-design.md
- 2026-05-17-dimension-mode-buttons-design.md
- 2026-05-22-markdown-card-notes-plan.md

**待办（5 篇，内容未过时）**：
- RESEARCH_AGENT_UPGRADE_PLAN.md
- 长文本提示词精进方案.md
- 维度优先的双层知识检索方案.md
- knowledgePLAN.md

## 已更新（本轮跳过）

| 文档 | 更新时间 |
|------|----------|
| `DEPLOYMENT_ARCHITECTURE.md` | 2026-05-27 |
| `MANUAL_DEPLOY_AFTER_CODE_CHANGES.md` | 2026-05-27 |
| `AGENTS.md` | 2026-05-27 |

## 非文档文件（跳过）

- compare-design-spec.md / frontend-design.md — 前端设计稿
- compare-*.html / compare-*.json — 演示/测试数据
- generate_preview.py — 脚本
