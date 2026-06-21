# docs 目录索引

> 本文档列出 `docs/` 下所有文档及其用途，方便快速查找。
> 最后更新：2026-06-20

---

## 核心文档（必看）

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md) | 技术总览 | 系统架构、代码结构、核心数据流、文件索引、修改记录 | **入门首选**：了解系统全貌，定位改代码先看哪些文件 |
| [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) | 数据库设计 | 表结构、字段定义、SQLAlchemy 模型、迁移脚本索引、查询示例 | 新增/修改数据库字段、排查数据问题 |
| [FUNCTION_INDEX.md](FUNCTION_INDEX.md) | 函数索引 | 按文件列出关键函数和常见问题速查 | 快速定位某个功能在哪实现 |
| [CHANGELOG.md](../CHANGELOG.md) | 变更日志 | 版本发布记录、功能更新、bug 修复 | 了解最近的改动 |

---

## 方案设计文档

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [CUSTOM_DIMENSION_PLAN.md](CUSTOM_DIMENSION_PLAN.md) | 方案 | 用户自定义精读维度集合（P8） | 理解 dimension_sets/items 的设计 |
| [CUSTOM_DIMENSION_PHASE1_IMPL.md](CUSTOM_DIMENSION_PHASE1_IMPL.md) | 实现 | 维度功能 Phase 1 实现细节 | 查看已完成的维度功能实现 |
| [CUSTOM_DIMENSION_PHASE2_DESIGN.md](CUSTOM_DIMENSION_PHASE2_DESIGN.md) | 设计 | 维度功能 Phase 2 原始设计（子 Tab 方案，已被内联方案替代） | 查看原始设计思路 |
| [CUSTOM_DIMENSION_PHASE2_IMPL.md](CUSTOM_DIMENSION_PHASE2_IMPL.md) | 实现 | 维度功能 Phase 2 实际实施记录（LongTab 内联编辑 + 拖拽排序） | 查看维度前端最终实现 |
| [CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md](CUSTOM_DIMENSION_EXPORT_IMPORT_FIX.md) | 修复 | 维度表导入导出遗漏修复 | 维度数据导出/导入问题排查 |
| [PENDING_PLANS.md](PENDING_PLANS.md) | 待办 | 所有未实施的功能规划（P1-P8） | 了解接下来做什么 |
| [MULTI_USER_PLAN.md](MULTI_USER_PLAN.md) | 方案 | 多用户系统整体规划 | 理解用户/角色/隔离设计 |
| [MULTIUSER_PROGRESS.md](MULTIUSER_PROGRESS.md) | 进度 | 多用户功能实施进度 | 查看已完成的里程碑 |
| [ADMIN_USAGE_FEEDBACK_PLAN.md](ADMIN_USAGE_FEEDBACK_PLAN.md) | 方案 | 管理员用户洞察与反馈后台设计 | 设计后台用量统计、用户详情、反馈闭环时 |
| [PROMPT_MANAGEMENT_PLAN.md](PROMPT_MANAGEMENT_PLAN.md) | 方案 | 提示词中心设计 | 理解 prompt_templates 的设计 |
| [PDF_METADATA_MATCH_PLAN.md](PDF_METADATA_MATCH_PLAN.md) | 方案 | PDF 元数据在线匹配 | 理解 match_online/apply_match 的设计 |
| [SYNTHESIS_PROMPT_PLAN.md](SYNTHESIS_PROMPT_PLAN.md) | 方案 | 综述提示词改进 | 综述相关规划 |
| [REFERENCE_CITATION_TAB_PLAN.md](REFERENCE_CITATION_TAB_PLAN.md) | 方案 | 参考文献梳理标签页 | 引用追踪相关规划 |
| [LIBRARY_SOURCE_TRANSLATION_PLAN.md](LIBRARY_SOURCE_TRANSLATION_PLAN.md) | 方案 | 文献库原文预览下载、语言标注与全文翻译联动 | 文献库原文与英文翻译入口改造时 |
| [TRANSLATION_FULLTEXT_PDF_RESTATE_PLAN.md](TRANSLATION_FULLTEXT_PDF_RESTATE_PLAN.md) | 方案 | PDF 全文不分片中文重述翻译改造计划 | 调整全文翻译提示词与 PDF 翻译管线时 |
| [CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md](CNKI_PARSER_AND_REVERSE_MATCH_DESIGN.md) | 设计 | CNKI/WoS 解析与反向匹配 | 理解题录解析和文件绑定逻辑 |
| [SYNTHESIS_CURRENT_DESIGN.md](SYNTHESIS_CURRENT_DESIGN.md) | 设计 | 当前综述实现设计 | 了解对比综述的当前实现 |
| [POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md](POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md) | 方案 | PostgreSQL 导向的 `.dra` 导入导出重构方案（覆盖/追加、旧 SQLite 包兼容） | 重构用户数据导入导出、排查 `.dra` 兼容与冲突策略时 |

---

## 运维与部署文档

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md) | 部署 | 本地→GitHub→服务器部署链路（PostgreSQL + systemd） | 部署流程、服务器配置 |
| [NEW_SERVER_SQL_MAINTENANCE.md](NEW_SERVER_SQL_MAINTENANCE.md) | 部署/运维 | 新服务器 `8.162.14.154:18080`、SQL 数据库、专用分支和手动部署维护指南 | 维护新服务器、部署本分支、排查 SQL 数据库和日志路径 |
| [MANUAL_DEPLOY_AFTER_CODE_CHANGES.md](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) | 部署/运维 | 每次改完代码后，上传到 `8.162.14.154:18080`、迁移、重启和验证的手动 Runbook | 手动上线代码、前端构建、迁移和排查重启问题 |
| [PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md](PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md) | 清单/运维 | 上线前手动部署与数据库验证 checklist，聚焦 PostgreSQL 目标库、systemd、静态资源与业务验收 | 真正上线前逐项勾选，避免 Alembic 跑错库、前端未覆盖、业务接口假阳性 |
| [DATABASE_DEPLOY_AND_MIGRATION_GUIDE.md](DATABASE_DEPLOY_AND_MIGRATION_GUIDE.md) | 部署 | 数据库部署与迁移指南（当前以 SQLite 本地开发为主描述，生产已迁移至 PostgreSQL） | 服务器数据库迁移 |
| [OPS_HEALTHCHECK_GUIDE.md](OPS_HEALTHCHECK_GUIDE.md) | 运维 | 服务器健康检查与自动恢复 | 线上故障排查 |
| [TROUBLESHOOTING_SERVER_ERRORS.md](TROUBLESHOOTING_SERVER_ERRORS.md) | 排错 | 服务器报错排查记录（含修复方案） | **线上报错排查首选**：500错误、401错误、SQL错误等 |
| [JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md](JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md) | 复盘/经验教训 | AI 助手顶刊名录改动引发的迁移与部署踩坑总结 + 双 routers/ 目录陷阱 | 新增 prompt type、CHECK 约束、前端 `dist` 覆盖、Alembic/SQLite/PostgreSQL 环境错配排查、`sys.path[0]` 导致旧模块被加载 |
| [PACKAGING_DOWNLOAD_FILTER_REPORT_BUG.md](PACKAGING_DOWNLOAD_FILTER_REPORT_BUG.md) | 排错/修复 | 打包版产物下载、参考文献引用详情、模板市场 AI 生成等问题记录 | 排查 Windows 打包版和模板市场生成链路问题 |
| [TWO_COLUMN_PDF_FIX.md](TWO_COLUMN_PDF_FIX.md) | 修复 | 双栏 PDF 参考文献提取修复（列感知文本提取） | 双栏论文参考文献提取不全 |
| [MIGRATION_PLAN_10PLUS_USERS.md](MIGRATION_PLAN_10PLUS_USERS.md) | 方案 | 10+ 并发用户迁移方案（含 SQLite → PostgreSQL 迁移 Runbook） | 并发扩容规划、后端数据库迁移 |
| [CONCURRENCY_ANALYSIS.md](CONCURRENCY_ANALYSIS.md) | 分析 | 多用户并发分析 | 性能瓶颈分析 |

---

## 故障与事件记录

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [INCIDENT_2026-05-06_LIBRARY_502.md](INCIDENT_2026-05-06_LIBRARY_502.md) | 事件 | 文献库 502 故障复盘 | 了解历史故障及修复过程 |
| [API_KEY_FLOW_FIX.md](API_KEY_FLOW_FIX.md) | 修复 | API Key 传递链路修复 | 理解 API Key 如何从前端传到后端 |
| [FIX_LIBRARY_CHAT_SAVE_500.md](FIX_LIBRARY_CHAT_SAVE_500.md) | 修复 | 文献助手保存历史记录远端 500 错误（SQLite CHECK 约束 migration 静默失败） | SQLite migration CHECK 约束修改不生效的排查参考 |
| [FIX_PG_FLUSH_ORDER_500.md](FIX_PG_FLUSH_ORDER_500.md) | 修复 | PostgreSQL 下文献助手保存历史 500 错误（SQLAlchemy flush 顺序导致 FK 违反） | PostgreSQL 同 session 多表 INSERT 顺序问题排查 |
| [MARKDOWN_MOUNT_REFRESH_FIX_2026-06-01.md](MARKDOWN_MOUNT_REFRESH_FIX_2026-06-01.md) | 修复/复盘 | Markdown 原文挂载后被列表刷新误清空的根因与修复 | 文献库 Markdown 原文挂载、列表刷新、`sanitize_entry_source_files`、`files`/md5 去重问题排查 |
| [2026-06-01-bib-attachments-design.md](2026-06-01-bib-attachments-design.md) | 设计/实现 | 文献库多 Markdown 附件、reader attachment view 与制卡联动 | 维护文献库附件、MarkdownReader 多版本阅读、`bib_attachments` 迁移时 |

---

## 专项功能文档

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md](REFERENCE_EXTRACTION_TWO_COLUMN_FIX_PLAN.md) | 方案 | 双栏 PDF 参考文献提取修复 | 理解 pdfplumber + use_text_flow 方案 |
| [REFERENCE_CITATION_DEEPSEEK_FLASH_PLAN.md](REFERENCE_CITATION_DEEPSEEK_FLASH_PLAN.md) | 方案 | DeepSeek Flash 模型用于引用追踪 | 引用追踪模型选型 |
| [COMPARE_SYNTHESIS_SELECTION_PLAN.md](COMPARE_SYNTHESIS_SELECTION_PLAN.md) | 方案 | 对比综述选择交互改进 | 对比页多选交互设计 |
| [COMPARE_CARD_ACTIONS_IMPL.md](COMPARE_CARD_ACTIONS_IMPL.md) | 实现 | 对比页 AnswerCard 三按钮（编辑/点评/AI总结）实施记录 | 理解对比页卡片操作功能的数据库、API、前端实现 |
| [CHUNKED_DATA_IMPORT_IMPL.md](CHUNKED_DATA_IMPORT_IMPL.md) | 实现 | 分片上传导入（.dra 大文件分片上传协议） | 理解分片导入三阶段流程、API 设计和前端实现 |
| [LIBRARY_AI_CHAT_IMPL.md](LIBRARY_AI_CHAT_IMPL.md) | 实现 | 文献库 AI 多轮查询、标签确认写库、标签搜索筛选和逐篇 AI 点评 | 维护文献库 AI 助手、结果联动和点评链路 |
| [AGENT_ASSISTANT_IMPL.md](AGENT_ASSISTANT_IMPL.md) | 实现 | AI 文献助手 tool calling、input 文件夹白名单、文件夹扫描、文献库对比、批量精读编排和前端 JSON HTML 展示 | 升级 AI 助手、Agent 工具、文件夹导入、持久会话和执行确认时 |
| [RESEARCH_AGENT_UPGRADE_PLAN.md](RESEARCH_AGENT_UPGRADE_PLAN.md) | 方案 | 研究助手智能体整改总方案（重写版）：以 runtime-first 为核心，覆盖 Task Frame、状态机、Sufficiency、结构化工作记忆、预算治理、联网授权与分期路线图 | 规划下一代数据库驱动研究智能体、修复 AI 助手“听不懂/幻觉/空转/联网失控”等问题时 |
| [RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) | 路线图 | Research Agent Runtime 新路线图：以 Sufficiency Engine、显式状态机、联网授权票据、Result Set UI 和工具覆盖扩展为后续主线 | 继续实施 AI 助手 runtime-first 改造、判断哪些能力已做和下一步先做什么时 |
| [RESEARCH_AGENT_EVIDENCE_STYLE_IDEA_ROADMAP_2026_06_20.md](RESEARCH_AGENT_EVIDENCE_STYLE_IDEA_ROADMAP_2026_06_20.md) | 路线图 | Research Agent evidence 排序、原文写作风格分析与经济管理 Idea Lab 的收口和后续路线图 | 判断 2026-06-12 写作风格计划与 2026-06-20 Idea Lab 计划的先后顺序、共享边界和下一步实施范围时 |
| [RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md](RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md) | 方案/任务清单 | Research Agent 整改实施任务拆解：按 P0/P1/P2、文件、模块、测试与验收标准组织的执行清单 | 准备真正开工实施 Research Agent 整改、拆分任务和排期时 |
| [AGENT_SESSION_CONFIRMATION_UI_PLAN.md](AGENT_SESSION_CONFIRMATION_UI_PLAN.md) | 方案 | AI 文献助手持久会话、agent_sessions/agent_messages、执行前确认、导入/精读确认弹窗和结果 UI 改造规划 | 实施可靠多轮对话、执行确认和 JSON 页面美化前 |
| [TESTSET_AND_P2_PLAN.md](TESTSET_AND_P2_PLAN.md) | 方案 | 测试集与 P2 规划 | 测试相关规划 |

---

## 优化与修复文档

| 文档 | 类型 | 内容 | 何时查阅 |
|------|------|------|----------|
| [BATCH_AND_COMPARE_IMPROVEMENTS.md](BATCH_AND_COMPARE_IMPROVEMENTS.md) | 优化 | 批量精读冲突预检、进度恢复、元数据去重、对比维度聚合 | 理解 2026-05-17 批次优化的全貌 |
| [SKIP_DUPLICATE_EXTRACTION.md](SKIP_DUPLICATE_EXTRACTION.md) | 优化 | 元数据提取去重 + 参考文献跳过已有记录 | 理解精读 LLM 调用优化 |
| [BATCH_CONFLICT_CHECK_PLAN.md](BATCH_CONFLICT_CHECK_PLAN.md) | 方案 | 批量精读冲突预检方案设计 | 理解批量冲突检测的接口和交互设计 |

---

## 设计文档子目录（superpowers）

### specs/（规格设计）

| 文档 | 内容 | 何时查阅 |
|------|------|----------|
| [superpowers/specs/2026-05-06-user-data-export-import-design.md](superpowers/specs/2026-05-06-user-data-export-import-design.md) | 用户数据导入导出设计（.dra 格式） | 理解导出/导入包格式和流程 |
| [superpowers/specs/2026-05-03-pdf-metadata-match-design.md](superpowers/specs/2026-05-03-pdf-metadata-match-design.md) | PDF 元数据匹配设计 | 理解在线匹配的技术方案 |

### plans/（实施计划）

| 文档 | 内容 | 何时查阅 |
|------|------|----------|
| [superpowers/plans/2026-05-06-simplify-reference-extraction.md](superpowers/plans/2026-05-06-simplify-reference-extraction.md) | 简化参考文献提取计划 | 参考文献功能简化方案 |
| [superpowers/plans/2026-05-06-remove-env-api-key-fallback.md](superpowers/plans/2026-05-06-remove-env-api-key-fallback.md) | 移除环境变量 API Key 兜底 | API Key 策略变更 |
| [superpowers/plans/2026-05-06-queue-integration-plan.md](superpowers/plans/2026-05-06-queue-integration-plan.md) | 任务队列接入计划 | 队列管理器集成方案 |
| [superpowers/plans/2026-05-03-pdf-metadata-match.md](superpowers/plans/2026-05-03-pdf-metadata-match.md) | PDF 元数据匹配实施计划 | 匹配功能实施步骤 |
| [superpowers/plans/2026-05-03-windows-executable-packaging.md](superpowers/plans/2026-05-03-windows-executable-packaging.md) | Windows 可执行文件打包计划 | PyInstaller 打包方案 |
| [superpowers/plans/2026-05-26-batch-reading-concurrency-and-asyncpg.md](superpowers/plans/2026-05-26-batch-reading-concurrency-and-asyncpg.md) | 批量精读并发与 asyncpg 稳定性修复计划 | 新 PostgreSQL 服务器批量长文本精读进度 500、连接池跨 event loop 和并发限流问题 |
| [superpowers/plans/2026-05-26-quant-qual-concurrency-reuse-long-fix.md](superpowers/plans/2026-05-26-quant-qual-concurrency-reuse-long-fix.md) | 七步/四步精读并发复用长文本修复计划 | 为七步和四步精读增加显式内层并发配置，复用新服务器稳定并发方案 |
| [superpowers/plans/2026-05-26-library-existing-files-start-reading.md](superpowers/plans/2026-05-26-library-existing-files-start-reading.md) | 文献库已有文件直接发起精读计划 | 从文献库多选已有 PDF/Markdown 文献并直接启动长文本/七步/四步精读，含 AI 助手入口 |
| [superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md](superpowers/plans/2026-06-12-agent-evidence-ranking-and-writing-style-analysis.md) | AI 助手 evidence 排序与原文写作风格分析计划 | 调整 evidence pack 排序，新增作者/期刊引言写作风格、理论推导风格的原文片段检索与蒸馏工具 |
| [superpowers/plans/2026-06-20-econ-management-idea-lab.md](superpowers/plans/2026-06-20-econ-management-idea-lab.md) | 经济管理研究 Idea Lab 计划 | 基于本地文献证据提取理论构念、机制、研究缺口、假设和选题候选 |

---

## 按主题快速查找

### 我要排查线上报错
→ [TROUBLESHOOTING_SERVER_ERRORS.md](TROUBLESHOOTING_SERVER_ERRORS.md)

### 我要了解系统整体架构
→ [TECHNICAL_OVERVIEW.md](TECHNICAL_OVERVIEW.md)

### 我要改数据库
→ [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md)

### 我要部署或重启服务
→ [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md)
→ [OPS_HEALTHCHECK_GUIDE.md](OPS_HEALTHCHECK_GUIDE.md)

### 我要了解某个功能的设计思路
→ 在上方「方案设计文档」中按名称查找

### 我要了解接下来做什么
→ [PENDING_PLANS.md](PENDING_PLANS.md)

### 我要快速定位某个函数
→ [FUNCTION_INDEX.md](FUNCTION_INDEX.md)

---

## 维护建议

开发与文档节奏：

1. 用户要求“先分析/先规划”时，先输出分析与实施规划，确认后再改代码。
2. 涉及数据库、导入导出、分支回灌、核心业务流程的改动，默认先规划再实施。
3. 代码改完后先做验证和简要说明，等用户本地测试成功后再写技术文档、复盘或经验教训。
4. 技术文档、复盘、经验教训统一放入 `docs/`，并同步更新本文档索引。
5. 功能未验证前，不把文档写成“已完成”。

新增文档时：
1. 在此索引中按类别添加条目
2. 更新「最后更新」日期
3. 如果文档很重要，考虑加入「核心文档」或「必看」分类
