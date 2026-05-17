# 精读结果多版本并存 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 允许同一篇文献多次精读（不同模式并存、同模式可覆盖或新增、长文本支持增量），用户通过弹窗选择冲突处理策略。

**Architecture:** 后端在 `reading_items` 层按 `job_type` 做覆盖判定，废弃 `force_overwrite` 改用 `conflict_resolution` 枚举。前端精读启动前先调 `check-conflict`，根据返回结果弹窗让用户选择。对比综述默认取最新 job 的结果。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + React 19 + TypeScript + Zustand

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/routers/reading.py` | Modify | `cleanup_old_reading_data` 加 job_type 过滤；新增 `check_conflict` 端点；三个 start 端点改用 `conflict_resolution` |
| `frontend/src/App.tsx` | Modify | LongTab/QuantTab/QualTab 的 handleStart 和 batch handler 改用 `conflict_resolution`，替换 `window.confirm` 为弹窗 |
| `frontend/src/components/ConflictDialog.tsx` | Create | 通用冲突选择弹窗组件 |
| `backend/routers/compare.py` | Modify | `get_reading_data` 按 bib_entry 取最新 job 的 reading_items |
| `frontend/src/components/CompareView.tsx` | Modify | 每篇文献下拉切换精读记录 |
| `frontend/src/LibraryTab.tsx` | Modify | 精读结果折叠展示 |
| `frontend/src/hooks/useCompareData.ts` | Modify | 支持 job_ids 参数切换精读记录 |

---

### Task 1: 后端 — `cleanup_old_reading_data` 加 job_type 过滤

**Files:**
- Modify: `backend/routers/reading.py:406-434`

- [ ] **Step 1: 修改函数签名和实现**

在 `backend/routers/reading.py` 中，将 `cleanup_old_reading_data` 函数替换为以下实现：

```python
async def cleanup_old_reading_data(db: AsyncSession, bib_entry: BibEntry, job_type: str | None = None) -> None:
    query = (
        select(JobBibEntry.job_id)
        .join(Job, Job.id == JobBibEntry.job_id)
        .where(JobBibEntry.bib_entry_id == bib_entry.id)
    )
    if job_type is not None:
        query = query.where(Job.job_type == job_type)
    old_job_ids = (await db.execute(query)).scalars().all()

    if old_job_ids:
        old_artifacts = (
            await db.execute(select(Artifact).where(Artifact.job_id.in_(old_job_ids)))
        ).scalars().all()
        for art in old_artifacts:
            if art.storage_path:
                physical = RESULTS_ROOT / art.storage_path
                if physical.exists():
                    try:
                        physical.unlink()
                    except OSError:
                        pass
        await db.execute(delete(Artifact).where(Artifact.job_id.in_(old_job_ids)))
        await db.execute(delete(ReadingItem).where(ReadingItem.job_id.in_(old_job_ids)))
        await db.execute(delete(JobBibEntry).where(JobBibEntry.job_id.in_(old_job_ids)))
        await db.execute(delete(Job).where(Job.id.in_(old_job_ids)))

    if not old_job_ids:
        await db.execute(delete(ReadingItem).where(ReadingItem.bib_entry_id == bib_entry.id))
    if not old_job_ids or job_type is not None:
        pass
    else:
        bib_entry.reading_status = "has_pdf"
    if not old_job_ids:
        bib_entry.reading_status = "has_pdf"
    await db.flush()
```

注意：当 `job_type` 过滤后有剩余 jobs（其他模式），不修改 `reading_status`；只有当所有 jobs 都被清理后才重置为 `has_pdf`。

- [ ] **Step 2: 更新调用点**

更新所有调用 `cleanup_old_reading_data` 的地方，传入 `job_type` 参数：

1. `start_long_context`（约 line 1447）→ `await cleanup_old_reading_data(db, bib_entry, "reading_long")`
2. `start_quant`（约 line 1503）→ `await cleanup_old_reading_data(db, bib_entry, "reading_quant")`
3. `start_qual`（约 line 1544）→ `await cleanup_old_reading_data(db, bib_entry, "reading_qual")`
4. `start_batch_reading` 内部（约 line 1600）→ `await cleanup_old_reading_data(db, bib_entry, job_type)`（`job_type` 变量已在函数内定义）

- [ ] **Step 3: 验证路由完整性**

```powershell
python -c "from backend.routers.reading import router; [print(r.path) for r in router.routes]"
```

Expected: 输出所有端点路径，和修改前一致。

- [ ] **Step 4: Commit**

```bash
git add backend/routers/reading.py
git commit -m "refactor(reading): cleanup_old_reading_data accepts job_type filter"
```

---

### Task 2: 后端 — Request 模型改为 `conflict_resolution`

**Files:**
- Modify: `backend/routers/reading.py:206-231`

- [ ] **Step 1: 更新 Pydantic 模型**

将三个 Request 模型替换为：

```python
class LongContextRequest(BaseModel):
    file_id: str
    analysis_dims: list[str]
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None
    dimension_set_id: Optional[int] = None


class SimpleReadingRequest(BaseModel):
    file_id: str
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None


class BatchReadingRequest(BaseModel):
    file_ids: list[str]
    mode: str
    analysis_dims: Optional[list[str]] = None
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    api_key: Optional[str] = None
    force_overwrite: Optional[bool] = None
    conflict_resolution: Optional[str] = None
    dimension_set_id: Optional[int] = None
```

- [ ] **Step 2: 添加辅助函数 `resolve_conflict_mode`**

在 `reading.py` 中添加：

```python
def resolve_conflict_mode(force_overwrite: Optional[bool], conflict_resolution: Optional[str], default: str = "check") -> str:
    if conflict_resolution in ("overwrite", "new", "incremental"):
        return conflict_resolution
    if force_overwrite is True:
        return "overwrite"
    return default
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/reading.py
git commit -m "feat(reading): add conflict_resolution param to request models"
```

---

### Task 3: 后端 — 新增 `check_conflict` 端点

**Files:**
- Modify: `backend/routers/reading.py`

- [ ] **Step 1: 添加 Pydantic 响应模型和端点**

在 `reading.py` 中添加：

```python
class CheckConflictRequest(BaseModel):
    file_id: str
    mode: str
    analysis_dims: Optional[list[str]] = None


@router.post("/check-conflict")
async def check_conflict(
    request: CheckConflictRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    file_record = await get_file_record(db, user, request.file_id)
    ensure_readable_file_type(file_record)
    bib_entry = await get_or_create_bib_entry(db, user, file_record)

    job_type_map = {"long": "reading_long", "quant": "reading_quant", "qual": "reading_qual"}
    job_type = job_type_map.get(request.mode)
    if not job_type:
        raise HTTPException(status_code=400, detail="mode 必须是 long/quant/qual")

    existing_jobs = (
        await db.execute(
            select(Job)
            .join(JobBibEntry, JobBibEntry.job_id == Job.id)
            .where(
                JobBibEntry.bib_entry_id == bib_entry.id,
                Job.job_type == job_type,
                Job.status == "success",
            )
            .order_by(Job.created_at.desc())
        )
    ).scalars().all()

    if not existing_jobs:
        return {"has_conflict": False}

    latest = existing_jobs[0]
    dimensions: list[str] = []
    incremental_dims: list[str] = []

    if request.analysis_dims and job_type == "reading_long":
        existing_items = (
            await db.execute(
                select(ReadingItem)
                .where(
                    ReadingItem.job_id == latest.id,
                    ReadingItem.section_type.in_(["dimension", "custom"]),
                )
                .order_by(ReadingItem.sort_order)
            )
        ).scalars().all()
        dimensions = [it.item_label for it in existing_items]
        existing_keys = {it.item_key for it in existing_items}
        incremental_dims = [
            d for d in request.analysis_dims
            if LONG_DIMENSION_KEYS.get(d, f"long.{slugify_key_fragment(d)}") not in existing_keys
            and d not in dimensions
        ]

    return {
        "has_conflict": True,
        "bib_entry": {
            "id": bib_entry.id,
            "title": bib_entry.title,
            "reading_status": bib_entry.reading_status,
        },
        "existing_job": {
            "job_id": latest.id,
            "job_type": latest.job_type,
            "created_at": latest.created_at.isoformat() if latest.created_at else None,
            "dimensions": dimensions,
            "mode_label": {
                "reading_long": "长文本精读",
                "reading_quant": "七步精读",
                "reading_qual": "四步精读",
            }.get(latest.job_type, latest.job_type),
        },
        "incremental_dims": incremental_dims,
    }
```

- [ ] **Step 2: 验证端点注册**

```powershell
python -c "from backend.routers.reading import router; [print(r.path, r.methods) for r in router.routes]"
```

Expected: 输出中包含 `/check-conflict` 和 `{'POST'}`。

- [ ] **Step 3: Commit**

```bash
git add backend/routers/reading.py
git commit -m "feat(reading): add POST /check-conflict endpoint"
```

---

### Task 4: 后端 — 改造三个 start 端点使用 `conflict_resolution`

**Files:**
- Modify: `backend/routers/reading.py`

- [ ] **Step 1: 改造 `start_long_context`**

替换 `start_long_context` 函数中 `dup = check_reading_duplicate(...)` 及后续逻辑为：

```python
    resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution)
    if resolution == "overwrite":
        await cleanup_old_reading_data(db, bib_entry, "reading_long")
    elif resolution == "check":
        dup = check_reading_duplicate(bib_entry, False)
        if dup:
            raise HTTPException(status_code=409, detail=dup)
```

注意：`resolution == "new"` 和 `resolution == "incremental"` 不做任何冲突检查，直接继续。

- [ ] **Step 2: 传递 `conflict_resolution` 到后台线程**

在 `start_long_context` 中，将 `conflict_resolution` 传给后台线程。修改 `run_long_context_task` 函数签名，新增 `conflict_resolution: Optional[str] = None` 参数。修改 `threading.Thread` 调用处：

```python
    thread = threading.Thread(
        target=run_long_context_task,
        args=(
            task_id, user.id, bib_entry.id, file_path,
            request.analysis_dims, request.custom_question,
            request.extraction_method, prompt_overrides,
            request.api_key, request.dimension_set_id,
            resolution,
        ),
        daemon=True,
    )
```

- [ ] **Step 3: 在 `run_long_context_task` 中实现增量逻辑**

在 `run_long_context_task` 函数中，`results = {}` 之前，添加增量维度复用：

```python
    prev_items: dict[str, str] = {}
    if conflict_resolution == "incremental":
        prev_jobs = asyncio.run(_query_prev_reading_jobs(user_id, bib_entry_id, "reading_long"))
        if prev_jobs:
            prev_job_id = prev_jobs[0]
            prev_ri = asyncio.run(_query_prev_reading_items(prev_job_id))
            prev_items = {it.item_key: it.content for it in prev_ri if it.section_type in ("dimension", "custom")}
```

在维度循环中，分析之前加跳过判定：

```python
        for i, dim_key in enumerate(analysis_dims):
            if tasks[task_id]["status"] == "cancelled":
                return

            item_key_for_dim = LONG_DIMENSION_KEYS.get(dim_key, f"long.{slugify_key_fragment(dim_key)}")
            if conflict_resolution == "incremental" and item_key_for_dim in prev_items:
                results[dim_key] = prev_items[item_key_for_dim]
                tasks[task_id]["logs"].append(f"⏭ {dim_key} 跳过（复用已有结果）")
                continue

            # ... 原有分析逻辑不变
```

添加两个辅助异步函数（放在 `run_long_context_task` 之前）：

```python
async def _query_prev_reading_jobs(user_id: int, bib_entry_id: str, job_type: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Job.id)
                .join(JobBibEntry, JobBibEntry.job_id == Job.id)
                .where(
                    JobBibEntry.bib_entry_id == bib_entry_id,
                    Job.job_type == job_type,
                    Job.status == "success",
                )
                .order_by(Job.created_at.desc())
                .limit(1)
            )
        ).scalars().all()
        return list(rows)


async def _query_prev_reading_items(job_id: str) -> list[ReadingItem]:
    async with AsyncSessionLocal() as db:
        return list(
            (
                await db.execute(
                    select(ReadingItem).where(ReadingItem.job_id == job_id).order_by(ReadingItem.sort_order)
                )
            ).scalars().all()
        )
```

- [ ] **Step 4: 改造 `start_quant` 和 `start_qual`**

在 `start_quant` 中替换冲突检查逻辑：

```python
    resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution)
    if resolution == "overwrite":
        await cleanup_old_reading_data(db, bib_entry, "reading_quant")
    elif resolution == "check":
        dup = check_reading_duplicate(bib_entry, False)
        if dup:
            raise HTTPException(status_code=409, detail=dup)
```

`start_qual` 同理，用 `"reading_qual"`。

- [ ] **Step 5: 改造 `start_batch_reading`**

在 `start_batch_reading` 中，将循环内的覆盖逻辑替换为：

```python
            resolution = resolve_conflict_mode(request.force_overwrite, request.conflict_resolution, default="overwrite")
            if resolution == "overwrite" and bib_entry.reading_status in ("reading", "read"):
                await cleanup_old_reading_data(db, bib_entry, job_type)
            elif resolution == "check" and bib_entry.reading_status in ("reading", "read"):
                batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": None, "status": "skipped", "error": "已有同模式精读结果"})
                continue
```

在返回值中添加 `"skipped_count": sum(1 for t in batch_tasks if t.get("status") == "skipped")`。

- [ ] **Step 6: 验证所有端点**

```powershell
python -c "from backend.routers.reading import router; [print(r.path, r.methods) for r in router.routes]"
```

- [ ] **Step 7: Commit**

```bash
git add backend/routers/reading.py
git commit -m "feat(reading): start endpoints use conflict_resolution, support incremental mode"
```

---

### Task 5: 前端 — 创建 `ConflictDialog` 组件

**Files:**
- Create: `frontend/src/components/ConflictDialog.tsx`

- [ ] **Step 1: 创建弹窗组件**

```tsx
import { useState } from 'react'

type ConflictOption = 'overwrite' | 'new' | 'incremental'

interface ConflictInfo {
  has_conflict: true
  existing_job: {
    job_id: string
    job_type: string
    created_at: string | null
    dimensions: string[]
    mode_label: string
  }
  incremental_dims: string[]
  bib_entry: { id: string; title: string; reading_status: string }
}

interface ConflictDialogProps {
  conflict: ConflictInfo
  mode: 'long' | 'quant' | 'qual'
  onResolve: (resolution: ConflictOption) => void
  onCancel: () => void
}

export default function ConflictDialog({ conflict, mode, onResolve, onCancel }: ConflictDialogProps) {
  const [selected, setSelected] = useState<ConflictOption>(
    mode === 'long' && conflict.incremental_dims.length > 0 ? 'incremental' : 'overwrite'
  )
  const isLong = mode === 'long'
  const hasIncremental = isLong && conflict.incremental_dims.length > 0

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-md p-6 space-y-4">
        <h3 className="text-lg font-semibold text-gray-900">
          该文献已有{conflict.existing_job.mode_label}结果
        </h3>

        {conflict.existing_job.created_at && (
          <p className="text-sm text-gray-500">
            完成时间：{new Date(conflict.existing_job.created_at).toLocaleString('zh-CN')}
          </p>
        )}

        {isLong && conflict.existing_job.dimensions.length > 0 && (
          <div className="text-sm">
            <p className="text-gray-600">已分析维度：{conflict.existing_job.dimensions.join('、')}</p>
            {hasIncremental && (
              <p className="text-amber-600 mt-1">本次新增维度：{conflict.incremental_dims.join('、')}</p>
            )}
          </div>
        )}

        <div className="space-y-2">
          {isLong && hasIncremental && (
            <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
              <input type="radio" name="conflict" value="incremental"
                checked={selected === 'incremental'} onChange={() => setSelected('incremental')} />
              <div>
                <span className="font-medium">增量补充</span>
                <span className="text-xs text-gray-500 ml-1">（跳过已有维度）</span>
              </div>
            </label>
          )}

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="conflict" value="overwrite"
              checked={selected === 'overwrite'} onChange={() => setSelected('overwrite')} />
            <div>
              <span className="font-medium">覆盖重跑</span>
              <span className="text-xs text-gray-500 ml-1">（删除同模式旧结果）</span>
            </div>
          </label>

          <label className="flex items-center gap-2 p-3 rounded-lg border cursor-pointer hover:bg-gray-50">
            <input type="radio" name="conflict" value="new"
              checked={selected === 'new'} onChange={() => setSelected('new')} />
            <div>
              <span className="font-medium">新增独立记录</span>
              <span className="text-xs text-gray-500 ml-1">（旧结果保留）</span>
            </div>
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <button onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-600 hover:bg-gray-100 rounded-lg">取消</button>
          <button onClick={() => onResolve(selected)}
            className="px-4 py-2 text-sm bg-indigo-600 text-white rounded-lg hover:bg-indigo-700">确认</button>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ConflictDialog.tsx
git commit -m "feat(frontend): add ConflictDialog component"
```

---

### Task 6: 前端 — 改造 LongTab 使用冲突弹窗

**Files:**
- Modify: `frontend/src/App.tsx` (LongTab section, ~lines 1097-1464)

- [ ] **Step 1: 添加 import 和 state**

在 `App.tsx` 顶部添加 import：
```typescript
import ConflictDialog from './components/ConflictDialog'
```

在 `LongTab` 组件内添加 state（约 line 1122 附近）：

```typescript
const [conflictInfo, setConflictInfo] = useState<any>(null)
```

- [ ] **Step 2: 改造 `handleStart`（约 line 1325）**

将现有的 409 重试逻辑替换为：

```typescript
  const handleStart = async () => {
    // ... 前置校验不变 ...

    // 第一次尝试（不带 force_overwrite）
    const startRes = await fetch('/api/reading/long/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: uploadData.file_id,
        analysis_dims: dims,
        dimension_set_id: dimensionSetId || undefined,
        custom_question: customQ || undefined,
        extraction_method: extraction,
        api_key: effectiveKey,
      }),
    })

    if (startRes.status === 409) {
      // 冲突：先查冲突详情，弹窗让用户选
      const checkRes = await fetch('/api/reading/check-conflict', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_id: uploadData.file_id,
          mode: 'long',
          analysis_dims: dims,
        }),
      })
      const conflict = await checkRes.json()
      if (conflict.has_conflict) {
        setConflictInfo(conflict)
        return
      }
    }

    if (!startRes.ok && startRes.status !== 409) {
      const err = await startRes.json()
      // ... 错误处理不变 ...
    }

    // 成功启动
    const data = await startRes.json()
    startTrackingTask(data.task_id)
  }
```

- [ ] **Step 3: 添加冲突解决回调**

在 `LongTab` 内添加：

```typescript
  const handleConflictResolve = async (resolution: 'overwrite' | 'new' | 'incremental') => {
    setConflictInfo(null)
    const effectiveKey = localStorage.getItem(`dra_api_key_${auth.user?.username}`)
    const dims = selectedDims.length > 0 ? selectedDims : ALL_DIMS
    const startRes = await fetch('/api/reading/long/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_id: uploadData.file_id,
        analysis_dims: dims,
        dimension_set_id: dimensionSetId || undefined,
        custom_question: customQ || undefined,
        extraction_method: extraction,
        api_key: effectiveKey,
        conflict_resolution: resolution,
      }),
    })
    if (startRes.ok) {
      const data = await startRes.json()
      startTrackingTask(data.task_id)
    }
  }
```

- [ ] **Step 4: 在 JSX 中渲染弹窗**

在 `LongTab` return 的 JSX 末尾（return 的闭合 `</div>` 前）添加：

```tsx
      {conflictInfo && (
        <ConflictDialog
          conflict={conflictInfo}
          mode="long"
          onResolve={handleConflictResolve}
          onCancel={() => setConflictInfo(null)}
        />
      )}
```

- [ ] **Step 5: 改造 LongTab batch handler（约 line 1438）**

将 batch 请求中的 `force_overwrite: true` 替换为 `conflict_resolution: 'overwrite'`（默认覆盖，批量场景不弹窗）：

```typescript
    body: JSON.stringify({
      file_ids: fileIds,
      mode: 'long',
      analysis_dims: dims,
      dimension_set_id: dimensionSetId || undefined,
      custom_question: customQ || undefined,
      extraction_method: extraction,
      api_key: effectiveKey,
      conflict_resolution: 'overwrite',
    }),
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(long-tab): use ConflictDialog instead of window.confirm"
```

---

### Task 7: 前端 — 改造 QuantTab 和 QualTab

**Files:**
- Modify: `frontend/src/App.tsx` (QuantTab ~lines 1789-1939, QualTab ~lines 2116-2263)

- [ ] **Step 1: 改造 QuantTab `handleStart`（约 line 1824）**

与 LongTab 相同模式：第一次不带 `force_overwrite`，409 时调 `check-conflict` 弹窗。

添加 state：
```typescript
const [conflictInfo, setConflictInfo] = useState<any>(null)
```

替换 handleStart 中 409 重试逻辑为弹窗方式（同 Task 6 模式，但 `mode: 'quant'`）。

添加 `handleConflictResolve`（同 Task 6，但 `mode: 'quant'`，不传 `analysis_dims`）。

在 JSX 中渲染 `ConflictDialog`。

- [ ] **Step 2: 改造 QuantTab batch handler（约 line 1928）**

替换 `force_overwrite: true` 为 `conflict_resolution: 'overwrite'`。

- [ ] **Step 3: 改造 QualTab `handleStart`（约 line 2148）**

同 QuantTab，但 `mode: 'qual'`。

- [ ] **Step 4: 改造 QualTab batch handler（约 line 2252）**

替换 `force_overwrite: true` 为 `conflict_resolution: 'overwrite'`。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(quant-tab,qual-tab): use ConflictDialog instead of window.confirm"
```

---

### Task 8: 后端 — 对比接口取最新 job

**Files:**
- Modify: `backend/routers/compare.py:316-379`

- [ ] **Step 1: 修改 `get_reading_data` 按 bib_entry 取最新 job**

在 `get_reading_data` 函数中，查询 `ReadingItem` 后，按 `bib_entry_id` 分组，对每个 bib_entry 只保留最新 job_id 的 items：

```python
    latest_job_per_bib: dict[str, str] = {}
    for item in all_items:
        if item.bib_entry_id not in latest_job_per_bib:
            latest_job_per_bib[item.bib_entry_id] = item.job_id

    filtered_items = [item for item in all_items if item.job_id == latest_job_per_bib.get(item.bib_entry_id)]
```

将后续的 `bib_entries_items` 构建改用 `filtered_items`。

- [ ] **Step 2: 验证**

```powershell
python -c "from backend.routers.compare import router; [print(r.path) for r in router.routes]"
```

- [ ] **Step 3: Commit**

```bash
git add backend/routers/compare.py
git commit -m "fix(compare): reading-data returns latest job per bib_entry"
```

---

### Task 9: 前端 — 对比综述支持切换精读记录

**Files:**
- Modify: `frontend/src/components/CompareView.tsx`
- Modify: `frontend/src/hooks/useCompareData.ts`
- Modify: `backend/routers/compare.py`

- [ ] **Step 1: 后端新增参数 `job_id`**

在 `get_reading_data` 端点添加可选参数 `job_ids: Optional[str] = None`。当传入了 `job_ids`（逗号分隔的 `bib_entry_id:job_id` 对）时，使用指定的 job_id 过滤 reading_items。

```python
@router.get("/reading-data")
async def get_reading_data(
    mode: str = Query(..., pattern=r"^(long|quant|qual)$"),
    job_ids: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
```

解析 `job_ids` 参数：
```python
    job_id_map: dict[str, str] = {}
    if job_ids:
        for pair in job_ids.split(","):
            if ":" in pair:
                bib_id, j_id = pair.split(":", 1)
                job_id_map[bib_id] = j_id
```

查询后过滤：
```python
    if job_id_map:
        filtered = [it for it in all_items if job_id_map.get(it.bib_entry_id, it.job_id) == it.job_id]
        all_items = filtered
```

同时需要修改查询，获取每个 bib_entry 的所有可用 jobs 列表：

```python
    available_jobs: dict[str, list[dict]] = {}
    bib_ids_list = list(bib_ids)
    if bib_ids_list:
        all_jobs = (
            await db.execute(
                select(Job.id, Job.job_type, Job.created_at, Job.finished_at, JobBibEntry.bib_entry_id)
                .join(JobBibEntry, JobBibEntry.job_id == Job.id)
                .where(
                    JobBibEntry.bib_entry_id.in_(bib_ids_list),
                    Job.job_type == job_type_map[mode],
                    Job.status == "success",
                )
                .order_by(JobBibEntry.bib_entry_id, Job.created_at.desc())
            )
        ).all()
        for jid, jtype, jcreated, jfinished, jbid in all_jobs:
            available_jobs.setdefault(jbid, []).append({
                "job_id": jid,
                "created_at": jcreated.isoformat() if jcreated else None,
                "finished_at": jfinished.isoformat() if jfinished else None,
            })
```

返回值中添加 `"available_jobs": available_jobs`。

- [ ] **Step 2: 前端 `useCompareData` 添加 job 切换**

在 `useCompareData.ts` 中添加：

```typescript
  const [selectedJobIds, setSelectedJobIds] = useState<Record<string, string>>({})

  const fetchWithJobs = async (jobIdMap?: Record<string, string>) => {
    const params = new URLSearchParams({ mode })
    if (jobIdMap && Object.keys(jobIdMap).length > 0) {
      params.set('job_ids', Object.entries(jobIdMap).map(([b, j]) => `${b}:${j}`).join(','))
    }
    const res = await fetch(`/api/compare/reading-data?${params}`)
    // ... 解析逻辑
  }
```

- [ ] **Step 3: CompareView 中添加下拉切换**

在每篇文献的 paper header 区域，如果 `available_jobs[paper.id]` 有多条记录，显示下拉选择器：

```tsx
{availableJobs[paper.id]?.length > 1 && (
  <select
    value={selectedJobIds[paper.id] || ''}
    onChange={(e) => {
      const next = { ...selectedJobIds, [paper.id]: e.target.value }
      setSelectedJobIds(next)
      refetchWithJobs(next)
    }}
    className="text-xs border rounded px-1 py-0.5"
  >
    {availableJobs[paper.id].map((j, i) => (
      <option key={j.job_id} value={j.job_id}>
        {i === 0 ? '最新' : `记录 ${i + 1}`} ({new Date(j.finished_at || j.created_at).toLocaleDateString('zh-CN')})
      </option>
    ))}
  </select>
)}
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/compare.py frontend/src/components/CompareView.tsx frontend/src/hooks/useCompareData.ts
git commit -m "feat(compare): support switching between multiple reading records per paper"
```

---

### Task 10: 前端 — 文献库折叠展示多条精读记录

**Files:**
- Modify: `frontend/src/LibraryTab.tsx`

- [ ] **Step 1: 改造 timeline 展示**

在 `LibraryTab.tsx` 的详情视图（timeline 区域，约 lines 726-783），改为折叠式：

- 默认只展示最新一条精读记录
- 如果同一 bib_entry 有多条 reading job，显示「查看更多 N 条精读记录」按钮
- 点击展开完整列表

添加 state：
```typescript
const [expandedTimeline, setExpandedTimeline] = useState(false)
```

在 timeline 渲染中：

```tsx
const timeline = detail.timeline.filter(t => t.job_type.startsWith('reading_'))
const displayed = expandedTimeline ? timeline : timeline.slice(0, 1)

{displayed.map(item => (
  // ... 原有渲染逻辑不变
))}
{timeline.length > 1 && !expandedTimeline && (
  <button onClick={() => setExpandedTimeline(true)}
    className="text-indigo-600 text-sm hover:underline">
    查看更多 {timeline.length - 1} 条精读记录
  </button>
)}
{expandedTimeline && timeline.length > 1 && (
  <button onClick={() => setExpandedTimeline(false)}
    className="text-gray-500 text-sm hover:underline">
    收起
  </button>
)}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/LibraryTab.tsx
git commit -m "feat(library): collapsible timeline for multiple reading records"
```

---

### Task 11: 集成验证

**Files:**
- All modified files

- [ ] **Step 1: 后端 lint 检查**

```powershell
python -c "from backend.routers.reading import router; [print(r.path) for r in router.routes]"
python -c "from backend.routers.compare import router; [print(r.path) for r in router.routes]"
```

- [ ] **Step 2: 前端 lint 和构建**

```powershell
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: 手动功能验证**

启动 `.\start-dev.ps1`，手动测试：

1. 上传一个 PDF → 长文本精读（选 2 个维度）→ 完成
2. 同一文件再次长文本精读（选不同维度）→ 应弹窗，选「新增独立」→ 两条记录并存
3. 同一文件再次长文本精读（重叠维度）→ 弹窗选「增量补充」→ 跳过已有维度
4. 同一文件 → 七步精读 → 应不弹窗（不同模式不冲突）
5. 文献库查看该文献 → 折叠展示多条精读记录
6. 对比综述选择该文献 → 下拉切换精读记录

- [ ] **Step 4: Final commit**

```bash
git add docs/PACKAGING_BRANCH_CHANGELOG.md
git commit -m "docs: update packaging changelog with multi-version reading feature"
```
