# 分支改动摘要

> **分支**: `codex/deepreading-empty-postgres-deploy`
> **基准**: `113ea903` (PostgreSQL下文献助手保存历史500修复)
> **统计**: 62 files changed, 4905 insertions(+), 1361 deletions(-)
> **日期**: 2026-05-29

---

## 一、本次会话关键修复 (2026-05-29)

### 1. data_portability.py - .dra 导入修复

**问题**: PostgreSQL 下导入 .dra 包时 FK 约束违反

**修复内容**:

1. **导入顺序调整** (第69-90行):
   - `Job` 移至 `BibEntry` 之前
   - 原因: `bib_entries.source_filter_job_id -> jobs.id` 外键依赖

2. **嵌套事务隔离** (第800-915行):
   - 函数: `_apply_record_import()`
   - 使用 `async with db.begin_nested():` 包裹每条记录
   - 原因: 单条 FK 失败不应污染整个 Session

**变化对比**:
```python
# 修复前
EXPORT_TABLE_ORDER = [..., BibEntry, Job, ...]  # 错误顺序
await db.flush()  # 失败后 Session 污染

# 修复后
EXPORT_TABLE_ORDER = [..., Job, BibEntry, ...]  # 正确顺序
async with db.begin_nested():  # 嵌套事务隔离
    await db.flush([job])
```

### 2. history.py - 文献助手保存修复

**问题**: `save_library_chat_report()` 函数 `NameError: name 'job' is not defined`

**修复内容** (第504-524行):
```python
# 修复前
db.add(Job(...))  # 未赋值给变量
await db.flush([job])  # job 未定义 ❌

# 修复后
job = Job(...)  # 赋值给变量
db.add(job)
await db.flush([job])  # 正确 ✅
```

---

## 二、主要功能变化

### 1. Research Agent / 外部检索 (新增)

**新增文件**:
- `backend/services/agent_external_retrieval.py` - 外部检索服务
- `backend/services/agent_tool_registry.py` - Agent 工具注册表
- `backend/services/research_agent_runtime.py` - Research Agent 运行时
- `backend/services/research_retrieval.py` - 研究检索服务

**新路由** (`backend/routers/agent.py`):
- `POST /api/agent/provider-check` - API 提供商检查
- `GET /api/agent/tool-capabilities` - 工具能力查询

### 2. 期刊质量知识库 (新增)

**新增文件**:
- `backend/services/journal_quality_kb.py` - 期刊质量 KB 服务
- `backend/services/reading_candidate_analysis.py` - 阅读候选分析
- `backend/utils/llm_provider.py` - LLM 提供商工具

**新增迁移**:
- `backend/migrations/versions/024_add_journal_kb_prompt_type.py`

**新增提示词**:
- `prompts/journal_kb/` - 期刊 KB 提示词目录

### 3. 并发维度阅读 (性能优化)

**文件**: `backend/routers/reading.py`

**主要函数变化**:
- `post_reading()` - 添加并发维度阅读逻辑
- `_concurrent_dimension_reading()` - 并发维度读取 (新增)
- `_merge_dimension_results()` - 维度结果合并 (新增)

**性能提升**: 3-8x 加速 (根据文档)

### 4. .dra 导入导出重构

**文件**: `backend/services/data_portability.py`

**新增常量**:
- `IMPORT_MODE_APPEND = "merge_append"`
- `IMPORT_MODE_REPLACE = "merge_replace"`

**新增/重构函数**:
- `_new_uuid_str()` - UUID 生成器
- `_normalize_schema_version()` - Schema 版本规范化
- `_ensure_supported_import_mode()` - 导入模式验证
- `_apply_record_import()` - 单条记录导入 (嵌套事务)
- `_build_row_kwargs()` - 构建记录参数
- `_find_existing_record()` - 查找现有记录
- `_rewrite_*_storage_path()` - 存储路径重写

**删除函数**:
- `_pre_delete_conflicts()` - 旧的冲突预删除逻辑

### 5. 前端功能增强

**文件**: `frontend/src/App.tsx`

**新增功能**:
- API 提供商切换 (`providerKey`)
- 批次 ID 恢复逻辑增强 (`restoreBatchId(kind)`)
- 期刊 KB 交互 (`journal_kb`)
- URL 解析增强 (`parsed.open_urls`)

**文件**: `frontend/src/LibraryTab.tsx`
- 文献助手 UI 调整

### 6. 数据库会话优化

**文件**: `backend/db/session.py`

**主要变化**:
- `get_db_session()` - 会话获取优化
- 添加 PostgreSQL 特定配置

---

## 三、迁移文件变化

| 迁移文件 | 变化内容 |
|---------|---------|
| `005_add_reference_trace_tables.py` | 引用追踪表调整 |
| `011_add_edits_and_annotations.py` | 编辑和注解表调整 |
| `012_add_dimension_set_reading_availability.py` | 维度集阅读可用性 |
| `014_add_translation_types.py` | 翻译类型扩展 |
| `022_add_library_chat_history.py` | 文献聊天历史表 |

**新增**:
- `024_add_journal_kb_prompt_type.py` - 期刊 KB 提示类型

---

## 四、测试更新

**新增测试**:
- `backend/tests/test_cleanup.py` - 清理测试 (290 行新增)
- `backend/tests/test_prompts.py` - 提示词测试 (33 行新增)
- `backend/tests/test_queue_manager.py` - 队列管理测试
- `backend/tests/test_reading.py` - 阅读测试
- `backend/tests/test_upload.py` - 上传测试

---

## 五、文档更新

**新增文档**:
- `docs/JOURNAL_KB_MIGRATION_DEPLOY_LESSONS_2026-05-29.md`
- `docs/MANUAL_DEPLOY_AFTER_CODE_CHANGES.md`
- `docs/NEW_SERVER_SQL_MAINTENANCE.md`
- `docs/PREDEPLOY_MANUAL_DEPLOY_AND_DB_VERIFICATION_CHECKLIST.md`
- `docs/RESEARCH_AGENT_IMPLEMENTATION.md`
- `docs/RESEARCH_AGENT_IMPLEMENTATION_TASKLIST.md`
- `docs/RESEARCH_AGENT_UPGRADE_PLAN.md`
- `docs/POSTGRESQL_DRA_IMPORT_EXPORT_REWRITE_PLAN.md`
- `docs/DIAGNOSIS_2026-05-26_MULTI_SYSTEM_FAILURE.md`

**更新文档**:
- `docs/CONCURRENCY_ANALYSIS.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/DEPLOYMENT_ARCHITECTURE.md`
- `docs/FUNCTION_INDEX.md`
- `docs/INCIDENT_2026-05-06_LIBRARY_502.md`
- `docs/MIGRATION_PLAN_10PLUS_USERS.md`
- `docs/MULTIUSER_PROGRESS.md`
- `docs/OPS_HEALTHCHECK_GUIDE.md`
- `docs/TECHNICAL_OVERVIEW.md`
- `docs/TROUBLESHOOTING_SERVER_ERRORS.md`

---

## 六、脚本和工具

**新增脚本**:
- `backend/scripts/run_cleanup_normal_users.py` - 常规用户清理脚本
- `scripts/agent_large_batch_eval.py` - Agent 大批次评估
- `health_check.py` - 健康检查工具
- `fix_constraint.py` - 约束修复工具

---

## 七、临时文件 (可清理)

这些文件不应纳入 commit:
- `deploy-*.tgz` - 部署包
- `build-repack/`, `dist-repack/` - 构建目录
- `session-*.md` - 会话文件
- `tmp_*.json` - 临时 JSON

---

## 八、依赖更新

**文件**: `backend/requirements.txt`
- 新增/更新依赖 (2 处变化)

---

## 九、部署建议

1. **数据库迁移**: 确保运行 `alembic upgrade head`
2. **依赖安装**: 更新 `requirements.txt`
3. **前端构建**: 重新构建 `frontend/dist`
4. **配置检查**: 确认 `.env.production` 配置正确

---

## 十、回滚计划

如需回滚到 `113ea903`:
1. `git reset --hard 113ea903`
2. 检查数据库 schema 是否需要 downgrade
3. 重新部署旧版本

---

> **生成时间**: 2026-05-29 18:25
> **生成人**: Claude Code
