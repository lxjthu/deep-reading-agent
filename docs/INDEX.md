# docs 索引规范

> 最后更新：2026-06-13
>
> 本文件定义 `docs/` 的阅读入口、归档规则和维护规范。查“当前系统到底是什么状态”时，先看
> [`CURRENT_STATE.md`](CURRENT_STATE.md)；查“有哪些文档、该放到哪里”时，看本文。

## 1. 文档分层

`docs/` 里的 Markdown 不应被当成同一类材料。后续维护时按下面五层判断：

| 层级 | 用途 | 典型文档 | 维护规则 |
|---|---|---|---|
| 当前状态 | 告诉后来者现在应相信什么 | [`CURRENT_STATE.md`](CURRENT_STATE.md) | 保持短、事实化；只写已验证状态和当前约束 |
| 长期入口 | 帮人快速理解系统、定位代码 | [`TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md)、[`FUNCTION_INDEX.md`](FUNCTION_INDEX.md)、[`STATE_AND_API_MAP.md`](STATE_AND_API_MAP.md)、[`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) | 与代码结构、数据库、API 变化同步 |
| 运维 Runbook | 指导线上部署、迁移、排障 | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md)、[`DEPLOYMENT_ARCHITECTURE.md`](DEPLOYMENT_ARCHITECTURE.md)、[`OPS_HEALTHCHECK_GUIDE.md`](OPS_HEALTHCHECK_GUIDE.md)、[`TROUBLESHOOTING_SERVER_ERRORS.md`](TROUBLESHOOTING_SERVER_ERRORS.md) | 必须贴近真实生产环境，不写猜测步骤 |
| 活跃路线图 | 指导下一步实施 | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md)、[`PENDING_PLANS.md`](PENDING_PLANS.md)、`docs/superpowers/plans/` | 明确“已完成 / 待实施 / 已废弃或被替代” |
| 历史记录 | 保存方案、复盘、事故、实现记录 | 各类 `*_PLAN.md`、`*_IMPL.md`、`FIX_*.md`、`INCIDENT_*.md`、日期命名文档 | 不强求随代码实时更新；必须避免冒充当前事实 |

## 2. 推荐阅读顺序

新接手任务时不要从所有文件里随机搜索。按任务类型选择入口：

| 任务 | 先读 | 再读 |
|---|---|---|
| 了解当前分支和线上约束 | [`CURRENT_STATE.md`](CURRENT_STATE.md) | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md)、[`DEPLOYMENT_ARCHITECTURE.md`](DEPLOYMENT_ARCHITECTURE.md) |
| 定位功能代码 | [`TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md) | [`FUNCTION_INDEX.md`](FUNCTION_INDEX.md)、[`STATE_AND_API_MAP.md`](STATE_AND_API_MAP.md) |
| 改数据库或导入导出 | [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) | [`POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md`](POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md)、相关 migration |
| 改 AI 文献助手 / Research Agent | [`RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md`](RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md) | [`RESEARCH_AGENT_IMPLEMENTATION.md`](RESEARCH_AGENT_IMPLEMENTATION.md)、[`RESEARCH_AGENT_UPGRADE_PLAN.md`](RESEARCH_AGENT_UPGRADE_PLAN.md)、相关 `docs/superpowers/plans/` |
| 上线代码 | [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) | [`PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md`](PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md)、[`JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md`](JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md) |
| 排查线上 500 / 502 / 迁移问题 | [`TROUBLESHOOTING_SERVER_ERRORS.md`](TROUBLESHOOTING_SERVER_ERRORS.md) | [`FIX_PG_FLUSH_ORDER_500.md`](FIX_PG_FLUSH_ORDER_500.md)、[`FIX_LIBRARY_CHAT_SAVE_500.md`](FIX_LIBRARY_CHAT_SAVE_500.md)、相关事故复盘 |
| 找待办和已规划事项 | [`PENDING_PLANS.md`](PENDING_PLANS.md) | 对应专题方案或 `docs/superpowers/plans/` |

## 3. 命名规范

新增文档优先使用可检索、可归类的英文文件名：

| 类型 | 命名建议 | 示例 |
|---|---|---|
| 当前状态入口 | 固定名称 | `CURRENT_STATE.md` |
| 总索引或导航 | 固定名称 | `INDEX.md`、`README.md` |
| 活跃路线图 | `FEATURE_ROADMAP_YYYY_MM_DD.md` | `RESEARCH_AGENT_RUNTIME_ROADMAP_2026_06_02.md` |
| 实施计划 | `FEATURE_PLAN.md` 或 `YYYY-MM-DD-feature-plan.md` | `POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md` |
| 实现记录 | `FEATURE_IMPL.md` | `AGENT_ASSISTANT_IMPL.md` |
| 修复记录 | `FIX_SHORT_PROBLEM.md` | `FIX_PG_FLUSH_ORDER_500.md` |
| 事故复盘 | `INCIDENT_YYYY-MM-DD_SHORT_NAME.md` | `INCIDENT_2026-05-06_LIBRARY_502.md` |
| 运维手册 | `*_GUIDE.md`、`*_CHECKLIST.md` | `OPS_HEALTHCHECK_GUIDE.md` |

中文文件名可以保留，但新增文档除非有明确展示目的，优先用英文文件名，方便脚本、搜索和跨平台处理。

## 4. 文档头部约定

新文档建议在标题后给出最小元信息：

```markdown
# 标题

> 状态：draft / active / implemented / historical / superseded
> 最后更新：YYYY-MM-DD
> 适用范围：本地开发 / 生产分支 / 打包版 / 某个功能模块
> 相关文档：`A.md`、`B.md`
```

状态含义：

| 状态 | 含义 |
|---|---|
| `draft` | 草案，尚未确认，不应用作执行依据 |
| `active` | 当前有效，可作为规划或操作依据 |
| `implemented` | 已实现记录，代码可能继续演进，必要时需复核 |
| `historical` | 历史背景或复盘，不代表当前实现 |
| `superseded` | 已被新方案替代，必须链接到替代文档 |

## 5. 分类规范

新增文档时，先判断它属于哪一类：

| 分类 | 放置位置 | 说明 |
|---|---|---|
| 长期入口 | `docs/` 根目录 | 只有少数稳定入口，避免膨胀 |
| 运维部署 | `docs/` 根目录 | 生产部署相关必须显眼 |
| 活跃实施计划 | `docs/superpowers/plans/` 或 `docs/` 根目录 | 计划必须写验收标准和验证命令 |
| 规格设计 | `docs/superpowers/specs/` 或 `docs/` 根目录 | 用于较大功能设计 |
| 复盘/事故 | `docs/` 根目录 | 文件名带日期或明确问题 |
| 临时想法 | 先进入 [`PENDING_PLANS.md`](PENDING_PLANS.md) | 不要为一句想法新增独立长文档 |

## 6. 维护规则

1. 不要把未验证功能写成“已完成”。
2. 代码改完后，先验证功能；用户确认本地测试成功后，再补技术文档或复盘。
3. 改数据库时，同步检查 [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md)、Alembic migration 和 `backend/services/data_portability.py`。
4. 改生产部署方式时，同步更新 [`MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`](MANUAL_DEPLOY_AFTER_CODE_CHANGES.md) 和 [`DEPLOYMENT_ARCHITECTURE.md`](DEPLOYMENT_ARCHITECTURE.md)。
5. 新增重要文档时，把它加入合适入口：本文、[`README.md`](README.md)、[`CURRENT_STATE.md`](CURRENT_STATE.md) 或 [`PENDING_PLANS.md`](PENDING_PLANS.md)。
6. 如果旧方案被替代，不要删除历史文档；在旧文档头部标注 `superseded` 并链接新文档。
7. PowerShell 读取或写入中文 Markdown 时显式使用 UTF-8，避免把终端乱码误判为文件损坏。

## 7. 当前建议保留的入口

| 入口 | 角色 |
|---|---|
| [`CURRENT_STATE.md`](CURRENT_STATE.md) | 当前分支、线上环境、已实现/未完成边界 |
| [`README.md`](README.md) | 旧版全量目录，保留作为大清单 |
| [`INDEX.md`](INDEX.md) | 文档治理规范和推荐阅读路径 |
| [`TECHNICAL_OVERVIEW.md`](TECHNICAL_OVERVIEW.md) | 系统总览 |
| [`FUNCTION_INDEX.md`](FUNCTION_INDEX.md) | 代码定位 |
| [`STATE_AND_API_MAP.md`](STATE_AND_API_MAP.md) | 前端状态、API、数据库链路 |
| [`DATABASE_SCHEMA.md`](DATABASE_SCHEMA.md) | 数据库事实入口 |
| [`PENDING_PLANS.md`](PENDING_PLANS.md) | 待实施计划池 |

## 8. 快速判断：这份文档还能不能信？

读任何旧文档前先看三件事：

1. 文件状态：是否标明 active、implemented、historical 或 superseded。
2. 更新时间：是否早于相关代码大改或生产迁移。
3. 证据来源：是否引用当前代码、测试、部署记录或用户验证。

如果文档和代码冲突，优先相信当前代码和最近验证；然后把冲突记录到对应入口或待办里。
