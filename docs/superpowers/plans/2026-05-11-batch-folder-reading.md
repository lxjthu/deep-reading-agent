# 批量文件夹上传精读 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在长文本/七步/四步三个精读 Tab 中支持文件夹批量上传，统一设置精读参数后逐篇排队执行，内联展示批量进度。

**Architecture:** 前端通过 `webkitdirectory` 选择文件夹，过滤 `.pdf/.md/.markdown` 后展示文件列表预览。用户确认后前端先逐个上传文件到 `/api/upload/`，收集 `file_ids`，再调用新端点 `POST /api/reading/batch/start` 一次性创建所有精读 Job（共享 `batch_id`）。前端轮询新端点 `GET /api/reading/batch/{batch_id}/status` 获取整体进度，内联展示每篇状态。后端复用现有单篇精读的全部逻辑（create_reading_job / enqueue / thread worker），仅新增批量编排层。

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy 2.0 async（后端）；React 19 + TypeScript（前端）；Job 表已有 `batch_id` 字段。

**设计决策记录：**
- 入口位置：每个 Tab 内增加「上传文件夹」按钮（非独立 Tab）
- 文件过滤：前端过滤 `.pdf/.md/.markdown`，递归子目录
- 重复处理：批量模式静默覆盖（`force_overwrite=true`）
- 进度展示：内联进度（当前第 N/M 篇 + 文件列表状态）

---

## 文件变更清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/routers/reading.py` | 新增 `BatchStartRequest` 模型、`POST /batch/start` 端点、`GET /batch/{batch_id}/status` 端点 |
| 修改 | `backend/db/models.py` | 无（`batch_id` 字段已存在于 Job 表） |
| 修改 | `frontend/src/App.tsx` | LongTab / QuantTab / QualTab 各增加批量上传 UI + 批量进度面板 + `handleBatchStart` 逻辑 |
| 修改 | `backend/tests/test_reading.py` | 新增批量端点测试 |

无需 Alembic 迁移（`batch_id` 字段已存在于 `jobs` 表，第 229 行 `models.py`）。

---

## 关键上下文（给实施者的地图）

### 后端

- **路由注册**：`backend/main.py:127` — `app.include_router(reading.router, prefix="/api/reading")`
- **Job 模型**：`backend/db/models.py:206` — `batch_id` 已有（`Optional[str]`，非 FK）
- **单篇 start 流程**（以 long 为例）：
  1. `get_file_record(db, user, request.file_id)` — 验证文件归属（`reading.py:249`）
  2. `ensure_readable_file_type(file_record)` — 校验 pdf/markdown（`reading.py:267`）
  3. `get_or_create_bib_entry(db, user, file_record)` — 获取/创建 BibEntry（`reading.py:275`）
  4. `check_reading_duplicate(bib_entry, force_overwrite)` — 检查重复（`reading.py:380`）
  5. `cleanup_old_reading_data(db, bib_entry)` — 覆盖时清理（`reading.py:395`）
  6. `get_effective_prompt_map(db, user_id, prompt_type)` — 获取提示词覆盖（`reading.py:1328`）
  7. `create_reading_job(db, user, file_record, bib_entry, job_type, params)` — 创建 Job（`reading.py:348`）
  8. `task_queue.enqueue(task_id, user.id, "long")` — 入队（`reading.py:1343`）
  9. 启动 `threading.Thread(target=run_*_task, ...)` — 异步执行（`reading.py:1345`）
- **Request 模型**：
  - `LongContextRequest`（`reading.py:206`）：`file_id, analysis_dims, custom_question, extraction_method, api_key, force_overwrite, dimension_set_id`
  - `SimpleReadingRequest`（`reading.py:216`）：`file_id, api_key, force_overwrite`
- **Worker 函数**：`run_long_context_task`、`run_quant_task`、`run_qual_task` — 各自接收 `(task_id, user_id, bib_entry_id, file_path, ...)` 参数启动线程
- **任务队列**：`services/queue_manager.py` — `task_queue.enqueue(task_id, user_id, task_type)`，已支持按用户并发控制

### 前端

- **Tab 结构**：`App.tsx` 中 `LongTab`（1027行）、`QuantTab`（1555行）、`QualTab`（1728行）
- **单篇 handleStart 流程**（三个 Tab 一致）：
  1. `promptForApiKey()` — 获取 Key
  2. `FormData` + `POST /api/upload/` — 上传文件
  3. `POST /api/reading/{mode}/start` — 启动精读
  4. `startTrackingTask(taskId)` — 轮询 `/api/reading/task/{taskId}/status`
- **useReadingTaskTracker**（`App.tsx:513`）：管理 `taskId/isRunning/progress/stage/logs/preview/downloadUrl` 状态，每秒轮询
- **handleFileChange**（各 Tab 内）：`setFile(e.target.files[0])`
- **上传 UI**：各 Tab 的 `<input type="file" accept=".pdf,.md,.markdown">` 在 dashed border label 内

---

### Task 1：后端 — 新增批量请求模型

**Files:**
- 修改：`backend/routers/reading.py`（在 `SimpleReadingRequest` 类之后，约 220 行）

- [ ] **Step 1：新增 Pydantic 模型**

在 `SimpleReadingRequest`（第 219 行）之后添加：

```python
class BatchReadingRequest(BaseModel):
    file_ids: list[str]
    mode: str  # "long" | "quant" | "qual"
    analysis_dims: Optional[list[str]] = None
    custom_question: Optional[str] = None
    extraction_method: str = "full"
    dimension_set_id: Optional[int] = None
    api_key: Optional[str] = None
    force_overwrite: bool = True
```

- [ ] **Step 2：验证模型被正确导入**

无需额外操作，同文件内定义。

---

### Task 2：后端 — 新增 `POST /batch/start` 端点

**Files:**
- 修改：`backend/routers/reading.py`（在 `start_qual` 端点之后，约 1446 行之后）

- [ ] **Step 1：实现端点**

在 `start_qual` 端点（第 1445 行 `return {"task_id": task_id, "status": "queued"}` 之后）添加：

```python
@router.post("/batch/start")
async def start_batch_reading(
    request: BatchReadingRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    if not request.file_ids:
        raise HTTPException(status_code=400, detail="file_ids 不能为空。")
    if request.mode not in ("long", "quant", "qual"):
        raise HTTPException(status_code=400, detail="mode 必须是 long/quant/qual 之一。")
    if len(request.file_ids) > 50:
        raise HTTPException(status_code=400, detail="单次批量最多 50 个文件。")

    batch_id = str(uuid.uuid4())
    job_type_map = {"long": "reading_long", "quant": "reading_quant", "qual": "reading_qual"}
    job_type = job_type_map[request.mode]
    prompt_type_map = {"long": "long", "quant": "quant", "qual": "qual"}
    prompt_type = prompt_type_map[request.mode]

    prompt_overrides = await get_effective_prompt_map(db, user_id=user.id, prompt_type=prompt_type)

    batch_tasks = []
    for file_id in request.file_ids:
        try:
            file_record = await get_file_record(db, user, file_id)
            ensure_readable_file_type(file_record)
            file_path = get_file_path(file_id)
            if not file_path:
                batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": None, "status": "skipped", "error": "文件路径未找到"})
                continue
            bib_entry = await get_or_create_bib_entry(db, user, file_record)
            if request.force_overwrite and bib_entry.reading_status in ("reading", "read"):
                await cleanup_old_reading_data(db, bib_entry)

            params: dict = {}
            if request.mode == "long":
                params = {
                    "analysis_dims": request.analysis_dims or [],
                    "custom_question": request.custom_question,
                    "extraction_method": request.extraction_method,
                }

            task_id = await create_reading_job(db, user, file_record, bib_entry, job_type, params)
            job_obj = (await db.execute(select(Job).where(Job.id == task_id))).scalar_one()
            job_obj.batch_id = batch_id

            await db.commit()

            tasks[task_id] = init_task_payload(task_id, request.mode, user.id, file_id, bib_entry.id)
            task_queue.enqueue(task_id, user.id, request.mode)

            if request.mode == "long":
                thread = threading.Thread(
                    target=run_long_context_task,
                    args=(task_id, user.id, bib_entry.id, file_path, request.analysis_dims or [], request.custom_question, request.extraction_method, prompt_overrides, request.api_key, request.dimension_set_id),
                    daemon=True,
                )
            elif request.mode == "quant":
                thread = threading.Thread(
                    target=run_quant_task,
                    args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
                    daemon=True,
                )
            else:
                thread = threading.Thread(
                    target=run_qual_task,
                    args=(task_id, user.id, bib_entry.id, file_path, prompt_overrides, request.api_key),
                    daemon=True,
                )
            thread.start()

            batch_tasks.append({"file_id": file_id, "file_name": file_record.original_name, "task_id": task_id, "status": "queued"})
        except Exception as exc:
            batch_tasks.append({"file_id": file_id, "file_name": file_id, "task_id": None, "status": "error", "error": str(exc)[:200]})

    return {"batch_id": batch_id, "tasks": batch_tasks}
```

**注意事项：**
- `get_file_path` 是已有函数，接受 `file_id: str` 返回 `Path | None`
- `init_task_payload` 是已有函数（约第 300 行附近），签名：`init_task_payload(task_id, kind, user_id, file_id, bib_entry_id)`
- `run_long_context_task` 签名：`(task_id, user_id, bib_entry_id, file_path, analysis_dims, custom_question, extraction_method, prompt_overrides, api_key, dimension_set_id)`
- `run_quant_task` / `run_qual_task` 签名：`(task_id, user_id, bib_entry_id, file_path, prompt_overrides, api_key)`
- 每个 file 循环内 `await db.commit()`，确保单个失败不影响其余

---

### Task 3：后端 — 新增 `GET /batch/{batch_id}/status` 端点

**Files:**
- 修改：`backend/routers/reading.py`（紧接 Task 2 的端点之后）

- [ ] **Step 1：实现端点**

```python
@router.get("/batch/{batch_id}/status")
async def get_batch_status(
    batch_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    jobs = (
        await db.execute(
            select(Job).where(Job.batch_id == batch_id, Job.owner_user_id == user.id)
        )
    ).scalars().all()

    if not jobs:
        raise HTTPException(status_code=404, detail="Batch not found")

    task_summaries = []
    completed = 0
    failed = 0
    running = 0
    queued = 0

    for job in jobs:
        status_str = job.status
        if status_str == "success":
            completed += 1
        elif status_str in ("failed", "canceled"):
            failed += 1
        elif status_str == "running":
            running += 1
        else:
            queued += 1

        file_name = ""
        if job.input_file_id:
            file_rec = (await db.execute(select(File).where(File.id == job.input_file_id))).scalar_one_or_none()
            file_name = file_rec.original_name if file_rec else ""

        in_memory = tasks.get(job.id, {})
        progress = in_memory.get("progress", job.progress or 0)
        stage = in_memory.get("stage", job.current_stage or "")
        download_url = ""
        preview = ""
        if status_str == "success":
            artifact = (
                await db.execute(
                    select(Artifact).where(Artifact.job_id == job.id, Artifact.artifact_type == "reading_final").limit(1)
                )
            ).scalar_one_or_none()
            if artifact:
                download_url = artifact.storage_path

        task_summaries.append({
            "task_id": job.id,
            "file_name": file_name,
            "status": status_str if status_str != "success" else "completed",
            "progress": progress,
            "stage": stage,
            "download_url": download_url,
        })

    return {
        "batch_id": batch_id,
        "total": len(jobs),
        "completed": completed,
        "failed": failed,
        "running": running,
        "queued": queued,
        "tasks": task_summaries,
    }
```

- [ ] **Step 2：验证端点注册**

运行：`python -c "from backend.routers.reading import router; [print(r.path) for r in router.routes]"`
预期输出包含 `/batch/start` 和 `/batch/{batch_id}/status`

---

### Task 4：后端 — 单元测试

**Files:**
- 修改：`backend/tests/test_reading.py`

- [ ] **Step 1：在现有测试类中添加批量端点测试**

在文件末尾（现有测试类之外）添加：

```python
class TestBatchReadingAPI(unittest.TestCase):
    """Tests for POST /batch/start and GET /batch/{batch_id}/status."""

    @classmethod
    def setUpClass(cls):
        from backend.routers import reading as reading_router
        from unittest.mock import patch

        cls._original_run_long = reading_router.run_long_context_task
        cls._original_run_quant = reading_router.run_quant_task
        cls._original_run_qual = reading_router.run_qual_task

        cls._patches = [
            patch.object(reading_router, "run_long_context_task", lambda *a, **kw: None),
            patch.object(reading_router, "run_quant_task", lambda *a, **kw: None),
            patch.object(reading_router, "run_qual_task", lambda *a, **kw: None),
        ]
        for p in cls._patches:
            p.start()

        reading_router.RESULTS_ROOT = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        from backend.routers import reading as reading_router
        for p in cls._patches:
            p.stop()
        shutil.rmtree(str(reading_router.RESULTS_ROOT), ignore_errors=True)

    def setUp(self):
        from backend.routers import reading as reading_router
        reading_router.tasks.clear()

    def test_batch_empty_file_ids(self):
        from backend.routers import reading as reading_router
        from httpx import AsyncClient, ASGITransport
        from backend.main import app

        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/reading/batch/start", json={"file_ids": [], "mode": "quant"})
                self.assertEqual(resp.status_code, 400)

        asyncio.run(_run())

    def test_batch_invalid_mode(self):
        from backend.main import app
        from httpx import AsyncClient, ASGITransport

        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post("/api/reading/batch/start", json={"file_ids": ["fake"], "mode": "invalid"})
                self.assertEqual(resp.status_code, 400)

        asyncio.run(_run())

    def test_batch_status_not_found(self):
        from backend.main import app
        from httpx import AsyncClient, ASGITransport

        async def _run():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/reading/batch/nonexistent/status")
                self.assertEqual(resp.status_code, 404)

        asyncio.run(_run())
```

- [ ] **Step 2：运行测试**

Run: `python -m unittest backend.tests.test_reading -v`
Expected: All tests pass including new batch tests

- [ ] **Step 3：Commit**

```bash
git add backend/routers/reading.py backend/tests/test_reading.py
git commit -m "feat: add batch reading endpoints (batch/start + batch/status)"
```

---

### Task 5：前端 — 新增批量状态管理 Hook

**Files:**
- 修改：`frontend/src/App.tsx`（在 `useReadingTaskTracker` 函数之后，约 660 行之后）

- [ ] **Step 1：新增 `useBatchReadingTracker` hook**

在 `useReadingTaskTracker` 的 return 语句之后（约第 660 行之后）添加：

```typescript
interface BatchTaskItem {
  task_id: string | null
  file_name: string
  status: string
  progress: number
  stage: string
  download_url: string
  error?: string
}

interface BatchState {
  batchId: string | null
  total: number
  completed: number
  failed: number
  running: number
  queued: number
  tasks: BatchTaskItem[]
  isBatchRunning: boolean
}

function useBatchReadingTracker() {
  const [state, setState] = useState<BatchState>({
    batchId: null, total: 0, completed: 0, failed: 0, running: 0, queued: 0, tasks: [], isBatchRunning: false,
  })
  const pollRef = useRef<number | null>(null)

  const stopPolling = () => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const resetBatch = () => {
    stopPolling()
    setState({
      batchId: null, total: 0, completed: 0, failed: 0, running: 0, queued: 0, tasks: [], isBatchRunning: false,
    })
  }

  const startBatchTracking = (batchId: string) => {
    setState(prev => ({ ...prev, batchId, isBatchRunning: true }))
    const poll = async () => {
      try {
        const res = await fetch(`/api/reading/batch/${batchId}/status`)
        const data = await res.json()
        const allDone = data.completed + data.failed >= data.total
        setState(prev => ({
          ...prev,
          total: data.total,
          completed: data.completed,
          failed: data.failed,
          running: data.running,
          queued: data.queued,
          tasks: data.tasks,
          isBatchRunning: !allDone,
        }))
        if (allDone) stopPolling()
      } catch {
        stopPolling()
        setState(prev => ({ ...prev, isBatchRunning: false }))
      }
    }
    void poll()
    stopPolling()
    pollRef.current = window.setInterval(() => void poll(), 2000)
  }

  useEffect(() => () => stopPolling(), [])

  return { ...state, startBatchTracking, resetBatch }
}
```

- [ ] **Step 2：Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add useBatchReadingTracker hook"
```

---

### Task 6：前端 — LongTab 增加批量上传 UI

**Files:**
- 修改：`frontend/src/App.tsx` — `LongTab` 函数（第 1027 行起）

- [ ] **Step 1：在 LongTab 内增加批量相关 state**

在 `LongTab` 函数内部，现有 state 声明区域（约第 1048 行 `const [overIdx, setOverIdx]` 之后），添加：

```typescript
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [showBatchPreview, setShowBatchPreview] = useState(false)
  const batchTracker = useBatchReadingTracker()
```

- [ ] **Step 2：新增 `handleFolderChange` 和 `handleBatchStart`**

在 `LongTab` 内的 `handleStart` 函数之后（约第 1310 行 `}` 之后），添加：

```typescript
  const handleFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const allowed = ['.pdf', '.md', '.markdown']
    const filtered = Array.from(e.target.files).filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase()
      return allowed.includes(ext)
    })
    if (filtered.length === 0) { alert('文件夹中没有找到 PDF 或 Markdown 文件'); return }
    setBatchFiles(filtered)
    setShowBatchPreview(true)
  }

  const removeBatchFile = (idx: number) => {
    setBatchFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleBatchStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (batchFiles.length === 0) { alert('没有可处理的文件'); return }

    setIsRunning(true); setProgress(0); setStage('批量上传文件中...'); setLogs([]); setPreview(''); setDownloadUrl('')
    batchTracker.resetBatch()

    try {
      const fileIds: string[] = []
      const failedUploads: string[] = []
      for (let i = 0; i < batchFiles.length; i++) {
        const f = batchFiles[i]
        setStage(`上传文件 ${i + 1}/${batchFiles.length}: ${f.name}`)
        try {
          const formData = new FormData()
          formData.append('file', f)
          const uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
          const uploadData = await uploadRes.json()
          if (uploadData.success) {
            fileIds.push(uploadData.file_id)
          } else {
            failedUploads.push(f.name)
          }
        } catch {
          failedUploads.push(f.name)
        }
      }

      if (fileIds.length === 0) throw new Error('所有文件上传失败')
      if (failedUploads.length > 0) {
        addLog(`⚠ ${failedUploads.length} 个文件上传失败: ${failedUploads.join(', ')}`)
      }
      addLog(`✓ ${fileIds.length} 个文件上传成功`)

      setStage('启动批量精读...')
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'long',
          analysis_dims: dims,
          dimension_set_id: dimensionSetId || undefined,
          custom_question: customQ || undefined,
          extraction_method: extraction,
          api_key: effectiveKey,
          force_overwrite: true,
        }),
      })
      const startData = await startRes.json()
      if (!startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')

      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${fileIds.length} 篇)`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }
```

- [ ] **Step 3：修改上传区域 UI，增加文件夹上传按钮**

找到 LongTab 的上传区域 `<label>` 标签（约第 1319 行），在 `</label>` 关闭标签之后、`<p className="mt-2 text-xs...">` 之前，插入文件夹上传按钮：

```tsx
          <div className="mt-2 flex items-center gap-2">
            <label className="flex items-center gap-1 rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-medium text-blue-700 cursor-pointer hover:bg-blue-100 transition-colors">
              <input type="file" webkitDirectory={{}} onChange={handleFolderChange} className="hidden" />
              上传文件夹
            </label>
            {batchFiles.length > 0 && (
              <span className="text-xs text-blue-600">{batchFiles.length} 个文件待处理</span>
            )}
          </div>
```

注意：`webkitDirectory={{}}` 在 TypeScript 中需要类型扩展。在文件顶部（`import` 之后）添加类型声明：

```typescript
declare module 'react' {
  interface InputHTMLAttributes<T> extends HTMLAttributes<T> {
    webkitdirectory?: string | object
  }
}
```

实际上 React 的类型已支持 `webkitdirectory` 作为 `boolean`。使用方式改为：

```tsx
              <input type="file" {...{ webkitdirectory: 'true' }} onChange={handleFolderChange} className="hidden" />
```

- [ ] **Step 4：新增批量文件预览弹窗**

在 LongTab 的 return JSX 中，批量进度面板（Task 7）之前，添加预览弹窗：

```tsx
      {showBatchPreview && batchFiles.length > 0 && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30">
          <div className="bg-white rounded-2xl shadow-2xl p-6 w-full max-w-lg max-h-[80vh] flex flex-col">
            <h3 className="text-base font-semibold text-gray-800 mb-3">批量精读文件列表（{batchFiles.length} 篇）</h3>
            <div className="flex-1 overflow-y-auto space-y-1 mb-4">
              {batchFiles.map((f, i) => (
                <div key={i} className="flex items-center justify-between rounded-lg px-3 py-1.5 hover:bg-gray-50 text-sm">
                  <span className="truncate text-gray-700">{f.name}</span>
                  <button onClick={() => removeBatchFile(i)} className="text-red-400 hover:text-red-600 text-xs ml-2 shrink-0">移除</button>
                </div>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button onClick={() => { setShowBatchPreview(false); setBatchFiles([]) }} className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">取消</button>
              <button onClick={handleBatchStart} disabled={isRunning} className="rounded-lg bg-gradient-to-r from-blue-600 to-blue-500 px-4 py-2 text-sm font-medium text-white hover:from-blue-700 hover:to-blue-600 disabled:opacity-50">
                {isRunning ? '上传中...' : `开始批量精读 (${batchFiles.length} 篇)`}
              </button>
            </div>
          </div>
        </div>
      )}
```

- [ ] **Step 5：验证 LongTab 编译**

Run: `cd frontend && npx tsc --noEmit 2>&1 | Select-String -Pattern "LongTab|batchFiles|handleBatchStart" | Select-Object -First 10`
Expected: 无相关错误

- [ ] **Step 6：Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add batch folder upload UI to LongTab"
```

---

### Task 7：前端 — LongTab 批量进度面板

**Files:**
- 修改：`frontend/src/App.tsx` — `LongTab` 的 return JSX

- [ ] **Step 1：在 LongTab 的右侧面板区域添加批量进度 UI**

找到 LongTab return JSX 中的右侧面板区域（`2xl:grid-cols-[minmax(320px,420px)_minmax(0,1fr)]` 的第二列）。在现有单篇进度面板（`isRunning` 条件渲染）的**同级**添加批量进度面板。

关键思路：当 `batchTracker.batchId` 存在时，显示批量进度面板替代单篇进度面板。

在现有单篇结果/进度区域之前（找到 `{isRunning && (` 的位置），添加：

```tsx
      {batchTracker.batchId && (
        <div className="rounded-xl border border-blue-200 bg-white p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-blue-700">批量精读进度</h3>
            <span className="text-xs text-gray-500">
              {batchTracker.completed + batchTracker.failed}/{batchTracker.total} 完成
              {batchTracker.failed > 0 && <span className="text-red-500 ml-1">({batchTracker.failed} 失败)</span>}
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2 mb-3">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${batchTracker.total > 0 ? ((batchTracker.completed + batchTracker.failed) / batchTracker.total * 100) : 0}%` }}
            />
          </div>
          {batchTracker.isBatchRunning && (
            <p className="text-xs text-blue-600 animate-pulse mb-3">
              正在处理第 {batchTracker.completed + batchTracker.running + 1}/{batchTracker.total} 篇...
            </p>
          )}
          {!batchTracker.isBatchRunning && batchTracker.total > 0 && (
            <p className="text-xs text-emerald-600 mb-3">
              批量精读完成！成功 {batchTracker.completed} 篇，失败 {batchTracker.failed} 篇。
            </p>
          )}
          <div className="space-y-1 max-h-60 overflow-y-auto">
            {batchTracker.tasks.map((t, i) => (
              <div key={t.task_id || i} className="flex items-center justify-between rounded-lg px-3 py-1.5 text-xs bg-gray-50">
                <span className="truncate text-gray-700 max-w-[200px]">{t.file_name}</span>
                <span className={
                  t.status === 'completed' ? 'text-emerald-600 font-medium' :
                  t.status === 'failed' || t.status === 'canceled' ? 'text-red-500' :
                  t.status === 'running' ? 'text-blue-600 animate-pulse' :
                  'text-gray-400'
                }>
                  {t.status === 'completed' ? '✓ 完成' :
                   t.status === 'failed' ? '✗ 失败' :
                   t.status === 'running' ? `⟳ ${t.progress}%` :
                   t.status === 'canceled' ? '⚠ 取消' :
                   '○ 排队'}
                </span>
                {t.status === 'completed' && t.download_url && (
                  <a href={`/api/download/${encodeURIComponent(t.download_url)}`} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline ml-2">下载</a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
```

- [ ] **Step 2：Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add batch progress panel to LongTab"
```

---

### Task 8：前端 — QuantTab 增加批量上传

**Files:**
- 修改：`frontend/src/App.tsx` — `QuantTab` 函数（第 1555 行起）

- [ ] **Step 1：在 QuantTab 内增加批量 state 和函数**

在 `QuantTab` 内部，现有 state 声明之后（约第 1557 行 `const [extraction, setExtraction]` 之后），添加：

```typescript
  const [batchFiles, setBatchFiles] = useState<File[]>([])
  const [showBatchPreview, setShowBatchPreview] = useState(false)
  const batchTracker = useBatchReadingTracker()
```

在 `handleStart` 函数之后（约第 1637 行 `const addLog = ...` 之后），添加 `handleFolderChange`、`removeBatchFile`、`handleBatchStart`（与 LongTab 逻辑相同，但 `mode: 'quant'`，请求体用 `SimpleReadingRequest` 格式）：

```typescript
  const handleFolderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const allowed = ['.pdf', '.md', '.markdown']
    const filtered = Array.from(e.target.files).filter(f => {
      const ext = f.name.substring(f.name.lastIndexOf('.')).toLowerCase()
      return allowed.includes(ext)
    })
    if (filtered.length === 0) { alert('文件夹中没有找到 PDF 或 Markdown 文件'); return }
    setBatchFiles(filtered)
    setShowBatchPreview(true)
  }

  const removeBatchFile = (idx: number) => {
    setBatchFiles(prev => prev.filter((_, i) => i !== idx))
  }

  const handleBatchStart = async () => {
    const effectiveKey = promptForApiKey()
    if (!effectiveKey) { alert('请先设置 DeepSeek API Key'); return }
    if (batchFiles.length === 0) { alert('没有可处理的文件'); return }

    setIsRunning(true); setProgress(0); setStage('批量上传文件中...'); setLogs([]); setCurrentStep(0)
    batchTracker.resetBatch()

    try {
      const fileIds: string[] = []
      const failedUploads: string[] = []
      for (let i = 0; i < batchFiles.length; i++) {
        const f = batchFiles[i]
        setStage(`上传文件 ${i + 1}/${batchFiles.length}: ${f.name}`)
        try {
          const formData = new FormData()
          formData.append('file', f)
          const uploadRes = await fetch('/api/upload/', { method: 'POST', body: formData })
          const uploadData = await uploadRes.json()
          if (uploadData.success) fileIds.push(uploadData.file_id)
          else failedUploads.push(f.name)
        } catch { failedUploads.push(f.name) }
      }
      if (fileIds.length === 0) throw new Error('所有文件上传失败')
      if (failedUploads.length > 0) addLog(`⚠ ${failedUploads.length} 个文件上传失败`)
      addLog(`✓ ${fileIds.length} 个文件上传成功`)

      setStage('启动批量精读...')
      const startRes = await fetch('/api/reading/batch/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_ids: fileIds,
          mode: 'quant',
          extraction_method: extraction,
          api_key: effectiveKey,
          force_overwrite: true,
        }),
      })
      const startData = await startRes.json()
      if (!startData.batch_id) throw new Error(startData.detail || '启动批量精读失败')

      addLog(`✓ 批量任务已创建: ${startData.batch_id} (${fileIds.length} 篇)`)
      setShowBatchPreview(false)
      batchTracker.startBatchTracking(startData.batch_id)
    } catch (error: any) {
      setStage('错误'); addLog(`❌ ${error.message}`)
      setIsRunning(false)
    }
  }
```

- [ ] **Step 2：在 QuantTab 上传区域增加文件夹按钮 + 预览弹窗 + 批量进度面板**

UI 与 LongTab 完全一致（Task 6 Step 3-4 和 Task 7 Step 1），插入到 QuantTab 的对应位置。

找到 QuantTab 的 `<label>` 上传区域（约第 1645 行），在 `</label>` 后添加文件夹按钮。
找到 QuantTab 的右侧面板添加批量进度面板。

具体代码复用 Task 6 和 Task 7 中的 JSX 模板，无需修改。

- [ ] **Step 3：Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add batch folder upload UI to QuantTab"
```

---

### Task 9：前端 — QualTab 增加批量上传

**Files:**
- 修改：`frontend/src/App.tsx` — `QualTab` 函数（第 1728 行起）

- [ ] **Step 1：在 QualTab 内增加批量 state 和函数**

与 Task 8 完全相同的模式，但 `mode: 'qual'`。

在 `QualTab` 内部 state 声明之后添加 `batchFiles`、`showBatchPreview`、`batchTracker`。
在 `handleStart` 之后添加 `handleFolderChange`、`removeBatchFile`、`handleBatchStart`（`mode: 'qual'`）。

- [ ] **Step 2：在 QualTab 上传区域增加文件夹按钮 + 预览弹窗 + 批量进度面板**

与 Task 6/7/8 相同的 UI 模板。

- [ ] **Step 3：Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add batch folder upload UI to QualTab"
```

---

### Task 10：验证与清理

**Files:** 无新增修改

- [ ] **Step 1：后端路由注册验证**

```powershell
python -c "from backend.routers.reading import router; [print(r.path, r.methods) for r in router.routes]"
```

预期输出包含：
- `/batch/start` — `{'POST'}`
- `/batch/{batch_id}/status` — `{'GET'}`

- [ ] **Step 2：后端测试**

```powershell
python -m unittest backend.tests.test_reading -v
```

预期：所有测试通过。

- [ ] **Step 3：前端 lint + 构建**

```powershell
cd frontend && npm run lint && npm run build
```

预期：lint 无错误，build 成功。

- [ ] **Step 4：功能冒烟测试**

1. 启动后端 `uvicorn backend.main:app --reload --port 8000`
2. 启动前端 `cd frontend && npm run dev`
3. 登录 → 设置 API Key → 进入「七步精读」Tab
4. 点击「上传文件夹」按钮 → 选择一个包含 2-3 个 PDF 的文件夹
5. 确认文件列表预览 → 点击「开始批量精读」
6. 观察批量进度面板是否正常更新
7. 等待完成，验证每篇结果可下载

- [ ] **Step 5：更新 PENDING_PLANS.md**

将 2.8 节状态从「待规划」改为「已完成」，添加完成日期。

- [ ] **Step 6：最终 Commit**

```bash
git add docs/PENDING_PLANS.md
git commit -m "docs: mark batch folder reading as completed"
```

---

## 自查清单

| 检查项 | 状态 |
|--------|------|
| 每个 spec 需求都有对应 Task | ✓ 批量上传、三模式、进度展示、静默覆盖 |
| 无 placeholder（TBD/TODO） | ✓ |
| 类型一致性（前后端字段名匹配） | ✓ `file_ids`/`mode`/`batch_id`/`tasks` 均一致 |
| 后端 Job.batch_id 字段已存在 | ✓ 无需迁移 |
| 前端 webkitdirectory 兼容性 | ✓ 主流浏览器均支持（Chrome/Edge/Firefox/Safari） |
| 三个 Tab 均有批量功能 | ✓ LongTab/QuantTab/QualTab 各有独立 Task |
| 与现有单篇流程互不干扰 | ✓ 批量是额外入口，单篇上传保留 |
