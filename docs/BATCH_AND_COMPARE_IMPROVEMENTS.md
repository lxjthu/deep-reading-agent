# 2026-05-17 批量精读与对比分析优化

> 日期：2026-05-17
> 涉及 commit：`c44b818c` `ef9d5f3a` `4519de39` + 待提交

## 概述

本次优化解决了批量精读和对比分析视图中的四个问题：

1. 元数据提取重复调用 LLM
2. 参考文献重复提取覆盖旧数据
3. 批量精读静默覆盖已有结果（无冲突提示）
4. 批量精读切换 Tab 后进度丢失
5. 对比分析只显示最后一次精读的维度

---

## 一、元数据提取去重

### 问题

每次精读任务中 `extract_front_matter()` + `extract_metadata_with_llm()` 被调用两次：一次 inline 给报告 YAML frontmatter，一次在 `_try_update_bib_metadata()` 内部给 BibEntry 更新。相同文件、相同 Key，纯浪费。

### 方案

`_try_update_bib_metadata()` 新增 `metadata: Optional[dict] = None` 参数，传入时跳过 LLM 调用。三个精读模式调用点（长文本/七步/四步）将 inline 已提取的 metadata 传入。

### 改动文件

- `backend/routers/reading.py` — `_try_update_bib_metadata()` 签名 + 三个调用点

### 效果

每次精读减少 1 次 `extract_metadata_with_llm` 调用 + 1 次 `extract_front_matter` 调用。

详细文档：`docs/SKIP_DUPLICATE_EXTRACTION.md`

---

## 二、参考文献跳过已有记录

### 问题

`_try_extract_references()` 每次精读都重新调用 `extract_references_deepseek()` + `trace_citations_deepseek()`，不检查是否已有参考文献。重复精读时删除旧数据重提，覆盖人工修正。

### 方案

`_try_extract_references()` 开头查询 `bib_references` 表，已有记录则返回 `None`（跳过标记）。三个调用点增加三段判断：`None` → 显示"已存在跳过"，空列表 → 显示"提取未成功"，非空 → 显示正常结果。手动入口 `start_reference_trace()` 不受影响。

### 改动文件

- `backend/routers/reading.py` — `_try_extract_references()` + 三个调用点 + `BibReference` import

### 效果

重复精读同一论文时跳过 2 次 DeepSeek 调用（提取 + 梳理引用位置）。

---

## 三、批量精读冲突预检

### 问题

三个模式的批量精读前端硬编码 `conflict_resolution: 'overwrite'`，不检查文件是否已有精读结果，静默覆盖。后端 `start_batch_reading` 的 `resolve_conflict_mode` 默认值也是 `"overwrite"`。

### 方案

**后端**：
- 新增 `POST /batch/check-conflict` 端点（`BatchCheckConflictRequest` 模型），遍历 file_ids，对每个文件查 BibEntry → 查已有成功 Job → 算增量维度，返回冲突详情
- `start_batch_reading` 的 `resolve_conflict_mode` default 从 `"overwrite"` 改为 `"check"`（安全兜底）

**前端**：
- 新建 `BatchConflictDialog.tsx` 组件：展示冲突文件列表 + 已有维度信息，三选项（覆盖重跑/增量补充/跳过已有）
- 三个 Tab 的 `handleBatchStart` 改为先调 `/batch/check-conflict`，无冲突直接启动，有冲突弹对话框让用户选择
- 删除三处硬编码 `conflict_resolution: 'overwrite'`

### 改动文件

| 文件 | 改动 |
|------|------|
| `backend/routers/reading.py` | 新增 `BatchCheckConflictRequest` + `/batch/check-conflict` 端点；default 改 `"check"` |
| `frontend/src/components/BatchConflictDialog.tsx` | 新建 |
| `frontend/src/App.tsx` | 三个 Tab 增加 `batchConflictInfo` state + 预检流程 + `handleBatchConflictResolve` |

### 边界情况

- 全部有冲突 + 选"跳过已有" → 所有文件 skip → 前端提示
- 全部无冲突 → 不弹对话框，直接启动
- 长文本 + 无增量维度 → 不显示"增量补充"选项

详细方案：`docs/BATCH_CONFLICT_CHECK_PLAN.md`

---

## 四、批量精读进度恢复

### 问题

`useBatchReadingTracker` 没有 localStorage 持久化。Tab 切换时组件 unmount → `batchId` 丢失 → 回来后不轮询 → 批量进度不显示。对比单篇的 `useReadingTaskTracker` 有 `persistReadingTaskId` / `restoreReadingTaskId` 恢复机制。

### 方案

给 `useBatchReadingTracker` 加上对等的持久化机制：
- 新增 `persistBatchId()` / `restoreBatchId()`，读写 `localStorage` key `dra_batch_task_id`
- `startBatchTracking()` 时写入 localStorage，批量全部完成后清除
- `resetBatch()` 时同步清除
- `useEffect` mount 时从 localStorage 恢复 `batchId` 并重新开始轮询

### 改动文件

- `frontend/src/App.tsx` — `useBatchReadingTracker` 函数

### 效果

切换 Tab 再回来时，批量精读进度自动恢复并继续轮询。

---

## 五、对比分析维度聚合

### 问题

`GET /api/compare/reading-data`（`compare.py:316`）按 job 级别过滤：每个 bib_entry 只保留最新一个 job 的 ReadingItems。如果一篇论文精读了多次、每次维度不同，旧 job 的独有维度被全部丢弃。

例如：
- Job A（旧）：维度 研究背景、理论框架、数据分析
- Job B（新）：维度 研究方法、数据分析

用户只看到 研究方法、数据分析，研究背景和理论框架丢失。

### 方案

改为按 `item_key` 级别去重，逻辑与同文件中 `build_structured_paper_data()` 一致：

1. 排序改为 `created_at DESC, sort_order ASC`，确保同 key 最新的排在前面
2. 按 `(bib_entry_id, item_key)` 去重，每个 key 只保留第一条（即最新的）
3. 分组后按 `sort_order` 重排，保证输出顺序正确

### 改动文件

- `backend/routers/compare.py` — `get_reading_data()` 函数

### 效果

- 跨 job 的维度全部展示（旧 job 独有维度不再丢失）
- 同一维度精读多次时只显示最新一次的结果
- 行为与 AI 综述 (`build_structured_paper_data`) 保持一致

---

## 数据库变更

本次所有改动均不涉及数据库 schema 变更，不需要 Alembic migration。
