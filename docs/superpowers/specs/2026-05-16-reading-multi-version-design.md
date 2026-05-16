# 精读结果多版本并存设计

> **日期**: 2026-05-16
> **分支**: packaging
> **目标**: 同一篇文献采用不同方法精读时，不覆盖旧结果，而是依托已有元数据补充新记录。支持增量精读（跳过已有维度）。

## 1. 需求摘要

| 规则 | 说明 |
|------|------|
| 不同模式并存 | 七步法、四步法、长文本三种模式的结果互不影响 |
| 同模式可覆盖或并存 | 用户手动选择：覆盖同模式旧结果，或新增独立记录 |
| 长文本增量精读 | 已有维度的分析结果可跳过，只分析新维度 |
| 覆盖判定 | 用户通过弹窗手动选择，前端不再硬编码 `force_overwrite: true` |
| 对比综述引用 | 默认取最新精读记录，可下拉切换 |
| 文献库展示 | 折叠式，默认展示最新，点击展开历史 |

## 2. 后端设计

### 2.1 `cleanup_old_reading_data()` — 增加 job_type 过滤

**当前行为**: 删除 bib_entry 下所有 jobs/artifacts/reading_items。

**改为**: 只删除 `job_type` 匹配的旧 jobs。

```python
async def cleanup_old_reading_data(
    db: AsyncSession,
    bib_entry: BibEntry,
    job_type: str,  # 新增参数
) -> None:
    # 查询该 bib_entry 下同 job_type 的旧 job IDs
    old_job_ids = (
        await db.execute(
            select(JobBibEntry.job_id)
            .join(Job, Job.id == JobBibEntry.job_id)
            .where(
                JobBibEntry.bib_entry_id == bib_entry.id,
                Job.job_type == job_type,
            )
        )
    ).scalars().all()

    # 删除这些 jobs 的 artifacts（物理文件+DB）、reading_items、job_bib_entries、jobs
    if old_job_ids:
        for art in (await db.execute(select(Artifact).where(Artifact.job_id.in_(old_job_ids)))).scalars().all():
            if art.storage_path:
                physical = RESULTS_ROOT / art.storage_path
                if physical.exists():
                    physical.unlink(missing_ok=True)
        await db.execute(delete(Artifact).where(Artifact.job_id.in_(old_job_ids)))
        await db.execute(delete(ReadingItem).where(ReadingItem.job_id.in_(old_job_ids)))
        await db.execute(delete(JobBibEntry).where(JobBibEntry.job_id.in_(old_job_ids)))
        await db.execute(delete(Job).where(Job.id.in_(old_job_ids)))
```

### 2.2 `conflict_resolution` 参数设计

**废弃** `force_overwrite: bool`，改用 `conflict_resolution: str`，三个语义明确的枚举值：

| 值 | 含义 | 后端行为 |
|----|------|----------|
| `"overwrite"` | 覆盖同模式旧结果 | `cleanup_old_reading_data(db, bib_entry, job_type)`，然后新建 Job |
| `"new"` | 新增独立记录，不检查冲突 | 直接新建 Job，忽略已有结果 |
| `"incremental"` | 增量补充（仅长文本） | 跳过已有维度，只分析新维度，新 Job 包含完整结果 |

**后端流程**：

```
1. conflict_resolution = "overwrite" → cleanup → 新建 Job
2. conflict_resolution = "new"       → 直接新建 Job（不查冲突）
3. conflict_resolution = "incremental" → 查已有结果 → 跳过已有维度 → 新建 Job
4. conflict_resolution 未传/空      → 查冲突：
   - 无冲突 → 同 "new"
   - 有冲突 → 返回 409（前端应先调 check-conflict 再决定）
```

### 2.3 新增端点 `POST /reading/check-conflict`

精读按钮点击前调用，返回冲突信息供前端弹窗展示。

```
Request:
  { file_id: str, mode: "long"|"quant"|"qual", analysis_dims?: list[str> }

Response 200:
  { has_conflict: false }
  | { has_conflict: true, existing_job: {...}, incremental_dims: [...] }
```

### 2.4 三个 start 端点改动

`/long/start`、`/quant/start`、`/qual/start` 统一流程，用 `conflict_resolution` 替代 `force_overwrite`。

**`LongContextRequest` 变更**:

```python
class LongContextRequest(BaseModel):
    file_id: str
    analysis_dims: list[str]
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    conflict_resolution: Optional[str] = None  # "overwrite" | "new" | "incremental"
    dimension_set_id: Optional[int] = None

class SimpleReadingRequest(BaseModel):
    file_id: str
    api_key: Optional[str] = None
    conflict_resolution: Optional[str] = None  # "overwrite" | "new"
```

**`force_overwrite` 向后兼容**：如果请求中传了 `force_overwrite=true` 但没有 `conflict_resolution`，映射为 `conflict_resolution="overwrite"`。

### 2.5 长文本增量精读执行逻辑

在 `run_long_context_task` 中，当 `conflict_resolution == "incremental"` 时：

```python
# 1. 查询同 bib_entry 同模式最近成功的 job
prev_items = {}  # item_key -> content
if conflict_resolution == "incremental":
    prev_job = ... # 查询最近的同模式成功 job
    if prev_job:
        prev_items = {it.item_key: it.content for it in prev_reading_items}

# 2. 对每个维度判断是否跳过
results = {}
for dim_key in analysis_dims:
    item_key = LONG_DIMENSION_KEYS.get(dim_key, f"long.{slugify_key_fragment(dim_key)}")
    if conflict_resolution == "incremental" and item_key in prev_items:
        results[dim_key] = prev_items[item_key]  # 复用旧结果
        tasks[task_id]["logs"].append(f"⏭ {dim_key} 跳过（复用已有结果）")
    else:
        results[dim_key] = engine.analyze_dimension(...)  # 调 LLM

# 3. 新 job 的 reading_items 包含所有维度（复用的 + 新分析的）
```

### 2.6 批量精读 `/batch/start` 改动

- `conflict_resolution="overwrite"` 时：逐文件 `cleanup_old_reading_data(db, bib_entry, job_type)`
- `conflict_resolution="new"` 时：直接新建，不检查冲突
- `conflict_resolution="incremental"` 时：逐文件增量执行
- `conflict_resolution` 未传时：有冲突的文件标记 `skipped`，返回中加 `skipped_count`
- 请求新增 `conflict_resolution` 参数透传

### 2.7 不改的部分

- `reading_status` 状态机不变
- `reading_items` 表结构不变（已通过 `job_id` 区分多次精读）
- `finalize_reading_success()` 不变
- 参考文献提取流程不变

## 3. 前端设计

### 3.1 精读启动流程改造

**当前**: 所有精读调用硬编码 `force_overwrite: true`。

**改为**:

1. 精读按钮点击 → 调 `POST /reading/check-conflict`
2. 无冲突 → 直接启动精读
3. 有冲突 → 弹窗让用户选择

### 3.2 冲突弹窗

**长文本模式**（存在增量选项）:

```
┌──────────────────────────────────────────┐
│  该文献已有长文本精读结果                    │
│  已分析维度：研究问题、理论框架               │
│  本次新增维度：识别策略、数据来源              │
│                                          │
│  ○ 覆盖重跑所有维度                         │
│  ○ 增量补充（跳过已有维度）                   │
│  ○ 新增一条独立精读记录                      │
│                                          │
│        [取消]         [确认]               │
└──────────────────────────────────────────┘
```

选项对应请求参数：
- 覆盖重跑 → `conflict_resolution: "overwrite"`
- 增量补充 → `conflict_resolution: "incremental"`
- 新增独立 → `conflict_resolution: "new"`

**七步/四步模式**:

```
┌──────────────────────────────────────────┐
│  该文献已有七步精读结果（2026-05-16）         │
│                                          │
│  ○ 覆盖旧结果                              │
│  ○ 新增一条独立精读记录                      │
│                                          │
│        [取消]         [确认]               │
└──────────────────────────────────────────┘
```

选项对应：覆盖 → `conflict_resolution: "overwrite"`，新增 → `conflict_resolution: "new"`

### 3.3 批量精读弹窗

加勾选项：`☑ 对本次批量中其他冲突文件采用相同选择`

勾选后，后续冲突文件不再逐个弹窗，统一应用第一次选择。

### 3.4 文献库展示（LibraryTab）

文献卡片内精读结果区改为折叠式：
- 默认展示最新一条精读记录（模式标签 + 时间）
- 点击展开显示所有精读记录列表，每条标注模式、维度/步骤、时间
- 每条记录可独立查看详情、下载

### 3.5 对比综述选文献（CompareView）

选择参与对比的文献时，如果某篇有多条精读记录：
- 默认取最新一条
- 下拉切换其他记录
- 切换后对比卡片即时刷新

## 4. API 变更汇总

| 端点 | 方法 | 变更 |
|------|------|------|
| `/reading/check-conflict` | POST | **新增**，返回冲突信息 |
| `/reading/long/start` | POST | `force_overwrite` 废弃，改用 `conflict_resolution`；支持 `"incremental"` |
| `/reading/quant/start` | POST | `force_overwrite` 废弃，改用 `conflict_resolution` |
| `/reading/qual/start` | POST | `force_overwrite` 废弃，改用 `conflict_resolution` |
| `/reading/batch/start` | POST | 同上，返回加 `skipped_count` |

**向后兼容**：旧客户端传 `force_overwrite=true` 仍可正常工作（映射为 `conflict_resolution="overwrite"`）。

## 5. 错误处理

| 场景 | HTTP 状态 | 处理 |
|------|-----------|------|
| 同模式已有结果 + `conflict_resolution` 未传 | 409 | 返回冲突详情，前端弹窗 |
| `conflict_resolution="incremental"` + 所有维度都已有结果 | 200 | 直接复用，不创建新 job |
| 批量中有冲突文件 + `conflict_resolution` 未传 | 200 | 该文件标记 `skipped` |

## 6. 涉及文件

| 文件 | 改动 |
|------|------|
| `backend/routers/reading.py` | `cleanup_old_reading_data`、`check_reading_duplicate` 改签名；三个 start 端点加逻辑；新增 `check_conflict` 端点 |
| `frontend/src/App.tsx` | 精读启动流程改造、冲突弹窗、`force_overwrite` 不再硬编码 |
| `frontend/src/LibraryTab.tsx` | 精读结果折叠展示 |
| `frontend/src/components/CompareView.tsx` | 多精读记录下拉切换 |
