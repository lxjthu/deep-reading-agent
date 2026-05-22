# 直接导入 & 批量翻译摘要 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在筛选页新增"直接导入"按钮跳过 AI 直接入库；在文献库新增批量翻译英文摘要功能；两个功能共享 BibEntry 新增的 `abstract_cn` 字段。

**Architecture:** 数据库新增 `abstract_cn` 列（Alembic 迁移），后端新增 3 个端点（direct-import / batch-translate / translate-status），前端在 FilterTab 和 LibraryTab 各新增一个操作入口。筛选流程也同步写入 `abstract_cn`。

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, OpenAI SDK (DeepSeek), React 19, Tailwind CSS

---

### Task 1: 数据库迁移 — 新增 abstract_cn 字段

**Files:**
- Modify: `backend/db/models.py` (BibEntry 类, 约第 280 行 abstract 字段之后)
- Create: `migrations/versions/xxxx_add_abstract_cn.py` (Alembic 迁移)

- [ ] **Step 1: 在 BibEntry ORM 模型中添加 abstract_cn 列**

在 `backend/db/models.py` 的 BibEntry 类中，`abstract` 字段之后添加：

```python
abstract_cn: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
```

位置约在 line 280 `abstract` 定义之后。

- [ ] **Step 2: 生成 Alembic 迁移脚本**

```powershell
cd D:\code\deepagent\deep-reading-agent-online\deep-reading-agent
alembic revision --autogenerate -m "add abstract_cn to bib_entries"
```

检查生成的迁移文件，确保包含：
```python
op.add_column('bib_entries', sa.Column('abstract_cn', sa.Text(), nullable=True))
```
以及对应的 downgrade：
```python
op.drop_column('bib_entries', 'abstract_cn')
```

- [ ] **Step 3: 执行迁移**

```powershell
alembic upgrade head
```

- [ ] **Step 4: 验证**

```powershell
python -c "from backend.db.models import BibEntry; print(BibEntry.__table__.c.abstract_cn)"
```

Expected: 输出 `bib_entries.abstract_cn` 列信息

- [ ] **Step 5: Commit**

```bash
git add backend/db/models.py migrations/versions/
git commit -m "feat: add abstract_cn column to bib_entries"
```

---

### Task 2: 更新 data_portability.py

**Files:**
- Modify: `backend/services/data_portability.py`

- [ ] **Step 1: 更新 CURRENT_SCHEMA_VERSION**

将 `CURRENT_SCHEMA_VERSION` 从 `"016"` 更新为新的迁移版本号（与 Task 1 生成的迁移编号一致）。

- [ ] **Step 2: 验证 export/import 自动覆盖 abstract_cn**

`data_portability.py` 使用 `_serialize_table()` / `_deserialize_table()` 自动处理所有列，新增的 `abstract_cn` 列会被自动包含。只需确认版本号正确即可。

- [ ] **Step 3: Commit**

```bash
git add backend/services/data_portability.py
git commit -m "chore: update schema version for abstract_cn"
```

---

### Task 3: 后端 — 提取共用 _upsert_bib_entry 函数

**Files:**
- Modify: `backend/routers/filter.py`

- [ ] **Step 1: 从 persist_filter_results 提取单条 upsert 逻辑**

在 `filter.py` 中（约 line 246 之前）新增独立函数：

```python
async def _upsert_bib_entry(
    db,
    owner_user_id: int,
    row: dict,
    source_db: str,
    source_filter_job_id: str | None = None,
    score: float | None = None,
    reason: str | None = None,
    abstract_cn: str | None = None,
) -> BibEntry:
    """
    从单条题录数据创建或更新 BibEntry。
    返回创建/更新后的 BibEntry 对象。
    """
    title = row.get("Title", "")
    authors = row.get("Authors", "")
    year = row.get("Year")
    doi = row.get("DOI")
    journal = row.get("Journal")
    abstract = row.get("Abstract")
    keywords = row.get("Keywords", "")
    venue_type = row.get("Type")
    citation_count = row.get("Citations")
    volume = row.get("Volume")
    issue = row.get("Issue")
    pages = row.get("Pages")

    if not isinstance(title, str) or not title.strip():
        return None
    title = title.strip()

    has_core = bool(title and authors)
    all_present = has_core and year and doi and journal and abstract
    metadata_completeness = "full" if all_present else ("partial" if has_core else "minimal")

    dedup_key = compute_dedup_key(doi, title, authors, year)

    existing = (
        await db.execute(
            select(BibEntry).where(
                BibEntry.owner_user_id == owner_user_id,
                BibEntry.dedup_key == dedup_key,
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(UTC)

    if existing is None:
        entry = BibEntry(
            id=str(uuid.uuid4()),
            owner_user_id=owner_user_id,
            title=title,
            authors_json=json.dumps(
                [a.strip() for a in authors.split(";") if a.strip()], ensure_ascii=False
            )
            if authors
            else "[]",
            year=int(year) if year and str(year).isdigit() else None,
            doi=normalize_doi(doi) if doi else None,
            journal=journal if journal and str(journal) != "nan" else None,
            abstract=abstract if abstract and str(abstract) != "nan" else None,
            keywords_json=json.dumps(
                [k.strip() for k in keywords.split(";") if k.strip()], ensure_ascii=False
            )
            if keywords and str(keywords) != "nan"
            else "[]",
            venue_type=venue_type if venue_type and str(venue_type) != "nan" else None,
            citation_count=int(citation_count) if citation_count and str(citation_count).isdigit() else None,
            volume=volume if volume and str(volume) != "nan" else None,
            issue=issue if issue and str(issue) != "nan" else None,
            pages=pages if pages and str(pages) != "nan" else None,
            language=None,
            source_db=source_db,
            source_filter_job_id=source_filter_job_id,
            source_file_id=None,
            reading_status="none",
            metadata_completeness=metadata_completeness,
            dedup_key=dedup_key,
            abstract_cn=abstract_cn,
            created_at=now,
            updated_at=now,
            expires_at=compute_expires_at(owner_user_id),
        )
        db.add(entry)
        await db.flush()
        return entry
    else:
        updates = {
            "title": title,
            "authors_json": json.dumps(
                [a.strip() for a in authors.split(";") if a.strip()], ensure_ascii=False
            )
            if authors
            else existing.authors_json,
            "year": int(year) if year and str(year).isdigit() else existing.year,
            "doi": normalize_doi(doi) if doi else existing.doi,
            "journal": journal if journal and str(journal) != "nan" else existing.journal,
            "abstract": abstract if abstract and str(abstract) != "nan" else existing.abstract,
            "keywords_json": json.dumps(
                [k.strip() for k in keywords.split(";") if k.strip()], ensure_ascii=False
            )
            if keywords and str(keywords) != "nan"
            else existing.keywords_json,
            "venue_type": venue_type if venue_type and str(venue_type) != "nan" else existing.venue_type,
            "citation_count": int(citation_count)
            if citation_count and str(citation_count).isdigit()
            else existing.citation_count,
            "volume": volume if volume and str(volume) != "nan" else existing.volume,
            "issue": issue if issue and str(issue) != "nan" else existing.issue,
            "pages": pages if pages and str(pages) != "nan" else existing.pages,
            "metadata_completeness": metadata_completeness,
            "updated_at": now,
        }
        if abstract_cn:
            updates["abstract_cn"] = abstract_cn
        for k, v in updates.items():
            setattr(existing, k, v)
        await db.flush()
        return existing
```

- [ ] **Step 2: 重构 persist_filter_results 使用 _upsert_bib_entry**

将 `persist_filter_results()` 中 lines 246-398 的逐行处理逻辑替换为调用 `_upsert_bib_entry()`。保留 `reverse_match_to_existing_files()` 调用、BibFilterLink 创建、Artifact 创建。

核心替换：将 for-loop 内的创建/更新逻辑替换为：
```python
row_dict = df.iloc[idx].to_dict()
abstract_cn_val = row_dict.get("abstract_cn")
if pd.isna(abstract_cn_val):
    abstract_cn_val = None
entry = await _upsert_bib_entry(
    db, user_id, row_dict,
    source_db=row_dict.get("SourceType", "other"),
    source_filter_job_id=job.id,
    abstract_cn=abstract_cn_val,
)
if entry is None:
    continue
```

对于新创建的 entry，仍然调用 `reverse_match_to_existing_files()`。

- [ ] **Step 3: 验证路由注册完整**

```powershell
python -c "from backend.routers.filter import router; [print(r.path, r.methods) for r in router.routes]"
```

Expected: 看到 `/start`, `/task/{task_id}/status`, `/task/{task_id}/cancel`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/filter.py
git commit -m "refactor: extract _upsert_bib_entry from persist_filter_results"
```

---

### Task 4: 后端 — 直接导入端点

**Files:**
- Modify: `backend/routers/filter.py`

- [ ] **Step 1: 添加 Pydantic 模型和端点**

在 `filter.py` 的模型定义区域添加：

```python
class DirectImportRequest(BaseModel):
    file_id: str

class DirectImportEntrySummary(BaseModel):
    title: str
    authors: list[str]
    year: Optional[int] = None
    doi: Optional[str] = None
    journal: Optional[str] = None

class DirectImportResponse(BaseModel):
    count: int
    entries: list[DirectImportEntrySummary]
```

在 `filter.py` 中添加新端点（在现有端点之后）：

```python
@router.post("/direct-import")
async def direct_import(
    req: DirectImportRequest,
    user: User = Depends(current_user),
):
    file_row = (
        await (await anext(get_db())).execute(
            select(File).where(File.id == req.file_id, File.owner_user_id == user.id)
        )
    ).scalar_one_or_none()
    if not file_row:
        raise HTTPException(status_code=404, detail="File not found")

    file_path = lookup_path_by_file_id(req.file_id)
    if not file_path or not Path(file_path).exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    parser = get_parser(file_path)
    if not parser:
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload WoS or CNKI export file.")

    df = parser.parse(file_path).to_dataframe()

    db = await anext(get_db())
    imported: list[DirectImportEntrySummary] = []
    source_db_map = {"WoS": "wos", "CNKI": "cnki"}

    for idx in range(len(df)):
        row_dict = df.iloc[idx].to_dict()
        raw_source = row_dict.get("SourceType", "other")
        source = source_db_map.get(str(raw_source), "other")

        entry = await _upsert_bib_entry(db, user.id, row_dict, source_db=source)
        if entry is None:
            continue

        reverse_match_to_existing_files(db, entry, user.id)

        imported.append(
            DirectImportEntrySummary(
                title=entry.title,
                authors=json.loads(entry.authors_json),
                year=entry.year,
                doi=entry.doi,
                journal=entry.journal,
            )
        )

    await db.commit()

    return DirectImportResponse(count=len(imported), entries=imported)
```

注意：需要在文件顶部确认 `get_parser` 的 import。当前 `filter.py` 没有 import `get_parser`，需要添加：
```python
from parsers import get_parser
```

- [ ] **Step 2: 修复 db session 获取方式**

上述代码中 `await anext(get_db())` 需要适配项目实际的 session 获取模式。查看 `filter.py` 中现有端点如何获取 db session：

如果现有端点使用 `db: AsyncSession = Depends(get_db)` 参数注入，则改为：
```python
@router.post("/direct-import")
async def direct_import(
    req: DirectImportRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
```

并在 `_upsert_bib_entry` 和 `reverse_match_to_existing_files` 调用中传入 `db`。

注意：如果 `persist_filter_results` 是同步函数中使用 `AsyncSessionLocal()` 获取 session，而新端点是 async，则用 `Depends(get_db)` 即可。需要检查 `reverse_match_to_existing_files` 是否是同步函数——如果是，需要调整（可以先不做 reverse_match 或用 `asyncio.to_thread` 包装）。

- [ ] **Step 3: 验证路由注册**

```powershell
python -c "from backend.routers.filter import router; [print(r.path, r.methods) for r in router.routes]"
```

Expected: 新增看到 `/direct-import`

- [ ] **Step 4: Commit**

```bash
git add backend/routers/filter.py
git commit -m "feat: add direct-import endpoint to filter router"
```

---

### Task 5: 前端 — FilterTab 直接导入按钮

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: 在 FilterTab 添加直接导入状态和 handler**

在 FilterTab 的 state 变量区域（约 line 827 之后）添加：

```tsx
const [importing, setImporting] = useState(false)
```

在 `handleStart` 函数之后添加新 handler：

```tsx
async function handleDirectImport() {
    if (!file) return
    setImporting(true)
    setLogs([])
    setResults([])
    try {
        const fd = new FormData()
        fd.append('file', file)
        const uploadRes = await authFetch('/api/upload/', { method: 'POST', body: fd })
        if (!uploadRes.ok) throw new Error('Upload failed')
        const uploadData = await uploadRes.json()
        const res = await authFetch('/api/filter/direct-import', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_id: uploadData.id }),
        })
        if (!res.ok) {
            const err = await res.json()
            throw new Error(err.detail || 'Import failed')
        }
        const data = await res.json()
        setLogs([`✅ 成功导入 ${data.count} 条题录到文献库`])
    } catch (e: any) {
        setLogs([`❌ 导入失败: ${e.message}`])
    } finally {
        setImporting(false)
    }
}
```

- [ ] **Step 2: 在 UI 中添加按钮**

在"开始筛选"按钮旁边（约 line 1130-1145 区域），添加"直接导入"按钮：

```tsx
<button
    onClick={handleDirectImport}
    disabled={!file || importing || isRunning}
    className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white rounded-md text-sm font-medium"
>
    {importing ? '导入中...' : '直接导入（跳过AI）'}
</button>
```

位置：与"开始筛选"按钮同级，放在其右侧或下方。

- [ ] **Step 3: 验证前端构建**

```powershell
cd frontend && npm run build
```

Expected: 无错误

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: add direct import button to FilterTab"
```

---

### Task 6: 后端 — 批量翻译摘要服务

**Files:**
- Create: `backend/services/abstract_translator.py`

- [ ] **Step 1: 创建 abstract_translator.py**

```python
"""Batch abstract translation service using DeepSeek."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from openai import OpenAI

from backend.utils.api_key import validate_deepseek_key

_SYSTEM_PROMPT = """你是一位学术翻译专家。将英文学术摘要翻译为中文。
要求：
1. 保持学术术语的准确性
2. 保留关键数据和方法信息
3. 语言流畅自然
4. 直接输出翻译结果，不要添加前缀或说明"""

MAX_RETRIES = 2
TIMEOUT = 120


def _translate_one(
    abstract: str,
    api_key: str,
    model: str = "deepseek-v4-flash",
) -> str:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"请翻译以下学术摘要：\n\n{abstract}"},
                ],
                max_tokens=2000,
                timeout=TIMEOUT,
            )
            return resp.choices[0].message.content.strip()
        except Exception:
            if attempt < MAX_RETRIES:
                time.sleep(3)
            else:
                raise


def run_batch_translate(
    job_id: str,
    user_id: int,
    entry_ids: list[str],
    api_key: str,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    model: str = "deepseek-v4-flash",
    max_workers: int = 5,
):
    """Background thread: translate abstracts for given entry_ids."""
    import asyncio
    from pathlib import Path
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    from db import AsyncSessionLocal
    from db.models import BibEntry, Job
    from sqlalchemy import select

    async def _run():
        total = len(entry_ids)
        translated = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        async with AsyncSessionLocal() as db:
            entries_result = await db.execute(
                select(BibEntry).where(
                    BibEntry.id.in_(entry_ids),
                    BibEntry.owner_user_id == user_id,
                )
            )
            entries = entries_result.scalars().all()

            to_translate = []
            for e in entries:
                if not e.abstract or not e.abstract.strip():
                    skipped += 1
                    continue
                to_translate.append(e)

            actual_total = len(to_translate)
            if log_cb:
                log_cb(f"共 {actual_total} 条待翻译（跳过 {skipped} 条无摘要）")

            def translate_entry(entry: BibEntry):
                if cancel_check and cancel_check():
                    return entry, None, "cancelled"
                try:
                    cn = _translate_one(entry.abstract, api_key, model)
                    return entry, cn, None
                except Exception as exc:
                    return entry, None, str(exc)

            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(translate_entry, e): e for e in to_translate}
                for future in as_completed(futures):
                    if cancel_check and cancel_check():
                        break
                    entry, cn, err = future.result()
                    if err:
                        failed += 1
                        errors.append(f"{entry.title[:30]}: {err}")
                        if log_cb:
                            log_cb(f"❌ 翻译失败: {entry.title[:40]}")
                    else:
                        entry.abstract_cn = cn
                        translated += 1
                        if log_cb:
                            log_cb(f"✅ [{translated}/{actual_total}] {entry.title[:40]}")

                    progress = int((translated + failed) / max(actual_total, 1) * 100)
                    job_result = await db.execute(select(Job).where(Job.id == job_id))
                    job = job_result.scalar_one_or_none()
                    if job:
                        job.progress = progress
                        job.current_stage = f"已翻译 {translated}/{actual_total}，失败 {failed}"
                        await db.commit()

            await db.commit()

            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                job.status = "success" if failed == 0 else ("success" if translated > 0 else "failed")
                job.progress = 100
                job.current_stage = f"完成：翻译 {translated}，跳过 {skipped}，失败 {failed}"
                job.params_json = json.dumps({
                    "total": total,
                    "translated": translated,
                    "skipped": skipped,
                    "failed": failed,
                    "errors": errors[:10],
                }, ensure_ascii=False)
                await db.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
```

- [ ] **Step 2: Commit**

```bash
git add backend/services/abstract_translator.py
git commit -m "feat: add batch abstract translation service"
```

---

### Task 7: 后端 — 批量翻译端点

**Files:**
- Modify: `backend/routers/library.py`

- [ ] **Step 1: 添加 import 和 Pydantic 模型**

在 `library.py` 顶部 import 区域添加：
```python
import threading
from services.abstract_translator import run_batch_translate
```

在 Pydantic 模型区域添加：
```python
class BatchTranslateRequest(BaseModel):
    entry_ids: list[str] = Field(..., min_length=1, max_length=200)
    api_key: str
```

- [ ] **Step 2: 添加批量翻译端点**

在 `library.py` 的 batch 操作端点区域之后添加：

```python
@router.post("/entries/batch-translate-abstracts")
async def batch_translate_abstracts(
    req: BatchTranslateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        api_key = validate_deepseek_key(req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job = Job(
        id=str(uuid.uuid4()),
        owner_user_id=user.id,
        job_type="translate_abstracts",
        status="pending",
        progress=0,
        current_stage="准备翻译...",
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    in_memory_status = {"status": "pending"}

    def cancel_check():
        return in_memory_status.get("status") == "cancelled"

    thread = threading.Thread(
        target=run_batch_translate,
        args=(job.id, user.id, req.entry_ids, api_key),
        daemon=True,
    )
    thread.start()

    return {"job_id": job.id}
```

注意：需要在 `library.py` 中 import `uuid`（如果尚未 import）。

- [ ] **Step 3: 添加翻译任务状态查询端点**

```python
@router.get("/translate-job/{job_id}/status")
async def get_translate_job_status(
    job_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    job = (
        await db.execute(select(Job).where(Job.id == job_id, Job.owner_user_id == user.id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    result = None
    if job.params_json:
        try:
            result = json.loads(job.params_json)
        except Exception:
            pass

    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress,
        "current_stage": job.current_stage,
        "error": job.error_msg,
        "result": result,
    }
```

注意：需要在 `library.py` 中 import `json`（如果尚未 import）。

- [ ] **Step 4: 验证路由注册**

```powershell
python -c "from backend.routers.library import router; [print(r.path, r.methods) for r in router.routes]"
```

Expected: 新增看到 `/entries/batch-translate-abstracts` 和 `/translate-job/{job_id}/status`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/library.py
git commit -m "feat: add batch translate abstracts endpoints"
```

---

### Task 8: 后端 — 修改 Library 详情读取 abstract_cn

**Files:**
- Modify: `backend/routers/library.py`
- Modify: `backend/db/models.py` (已在 Task 1 完成)

- [ ] **Step 1: 在 LibraryEntryDetail 中添加 abstract_cn 字段**

在 `library.py` 的 `LibraryEntryDetail` 类中添加：
```python
abstract_cn: Optional[str] = None
```

- [ ] **Step 2: 修改 build_entry_detail 使用 entry.abstract_cn**

找到 `get_entry_detail` 端点中构建 `LibraryEntryDetail` 的位置，添加 `abstract_cn=entry.abstract_cn`。

同时在 `LibraryFilterEvaluation` 的 `abstract_translation` 填充逻辑中，优先使用 `entry.abstract_cn`：

```python
abstract_translation=entry.abstract_cn or _load_abstract_translation_from_artifact(entry, artifact),
```

- [ ] **Step 3: 验证路由注册**

```powershell
python -c "from backend.routers.library import router; [print(r.path, r.methods) for r in router.routes]"
```

- [ ] **Step 4: Commit**

```bash
git add backend/routers/library.py
git commit -m "feat: expose abstract_cn in library detail, prefer DB field over Excel"
```

---

### Task 9: 前端 — LibraryTab 批量翻译按钮

**Files:**
- Modify: `frontend/src/LibraryTab.tsx`

- [ ] **Step 1: 添加翻译相关状态变量**

在 LibraryTab 的 state 变量区域（约 line 337 之后）添加：

```tsx
const [translating, setTranslating] = useState(false)
const [translateProgress, setTranslateProgress] = useState('')
```

- [ ] **Step 2: 添加批量翻译 handler**

在 `handleBatchDelete` 等函数之后添加：

```tsx
async function handleBatchTranslate() {
    const apiKey = localStorage.getItem('deepseek_api_key') || ''
    if (!apiKey) {
        alert('请先在设置中配置 DeepSeek API Key')
        return
    }
    const ids = Array.from(selectedIds)
    if (!confirm(`确认翻译 ${ids.length} 条英文摘要？将调用 DeepSeek API。`)) return

    setTranslating(true)
    setTranslateProgress('提交翻译任务...')
    try {
        const res = await authFetch('/api/library/entries/batch-translate-abstracts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ entry_ids: ids, api_key: apiKey }),
        })
        if (!res.ok) throw new Error('Failed to start translation')
        const { job_id } = await res.json()

        const poll = setInterval(async () => {
            try {
                const sr = await authFetch(`/api/library/translate-job/${job_id}/status`)
                const sd = await sr.json()
                setTranslateProgress(sd.current_stage || `${sd.progress}%`)
                if (sd.status === 'success' || sd.status === 'failed') {
                    clearInterval(poll)
                    setTranslating(false)
                    if (sd.status === 'success') {
                        const r = sd.result || {}
                        alert(`翻译完成：${r.translated || 0} 条成功，${r.failed || 0} 条失败`)
                    } else {
                        alert('翻译任务失败：' + (sd.error || '未知错误'))
                    }
                    loadEntries()
                }
            } catch {
                clearInterval(poll)
                setTranslating(false)
            }
        }, 2000)
    } catch (e: any) {
        alert('翻译失败: ' + e.message)
        setTranslating(false)
    }
}
```

- [ ] **Step 3: 在批量操作栏 UI 中添加按钮**

在 LibraryTab 的批量操作栏（约 line 1183-1218，`selectedIds.size > 0` 区域）中，在"删除选中"按钮之前添加：

```tsx
<button
    onClick={handleBatchTranslate}
    disabled={translating}
    className="px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-400 text-white rounded text-sm font-medium"
>
    {translating ? translateProgress : '翻译摘要'}
</button>
```

- [ ] **Step 4: 验证前端构建**

```powershell
cd frontend && npm run build
```

Expected: 无错误

- [ ] **Step 5: Commit**

```bash
git add frontend/src/LibraryTab.tsx
git commit -m "feat: add batch translate abstracts button to LibraryTab"
```

---

### Task 10: 后端 — 筛选流程同步写入 abstract_cn

**Files:**
- Modify: `backend/routers/filter.py`

- [ ] **Step 1: 确认 _upsert_bib_entry 已处理 abstract_cn**

Task 3 中 `_upsert_bib_entry` 已接受 `abstract_cn` 参数。检查 `persist_filter_results` 中调用 `_upsert_bib_entry` 时是否正确传入了 `abstract_cn`。

确认点：在 `persist_filter_results` 的 for 循环中：
```python
abstract_cn_val = row_dict.get("abstract_cn")
if pd.isna(abstract_cn_val):
    abstract_cn_val = None
entry = await _upsert_bib_entry(
    db, user_id, row_dict,
    source_db=...,
    source_filter_job_id=job.id,
    abstract_cn=abstract_cn_val,
)
```

- [ ] **Step 2: Commit（如有改动）**

```bash
git add backend/routers/filter.py
git commit -m "feat: filter pipeline writes abstract_cn to BibEntry"
```

---

### Task 11: 前端 — LibraryTab 详情显示 abstract_cn

**Files:**
- Modify: `frontend/src/LibraryTab.tsx`

- [ ] **Step 1: 在详情面板的摘要区域显示中文翻译**

在 LibraryTab 的详情面板中，找到 abstract 显示区域，在其下方添加 abstract_cn 的展示：

```tsx
{detail.abstract_cn && (
    <div className="mt-2">
        <label className="block text-xs font-medium text-gray-500 mb-1">中文摘要</label>
        <p className="text-sm text-gray-700 whitespace-pre-wrap bg-blue-50 p-2 rounded">{detail.abstract_cn}</p>
    </div>
)}
```

- [ ] **Step 2: 验证前端构建**

```powershell
cd frontend && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/LibraryTab.tsx
git commit -m "feat: display abstract_cn in library detail panel"
```

---

### Task 12: 整体验证

- [ ] **Step 1: 后端启动验证**

```powershell
python -c "from backend.main import app; print('App loaded successfully')"
```

- [ ] **Step 2: 前端 lint + build**

```powershell
cd frontend && npm run lint && npm run build
```

- [ ] **Step 3: 后端单测**

```powershell
python -m unittest backend.tests.test_queue_manager
```

- [ ] **Step 4: 路由完整性验证**

```powershell
python -c "from backend.routers.filter import router; [print(r.path, r.methods) for r in router.routes]"
python -c "from backend.routers.library import router; [print(r.path, r.methods) for r in router.routes]"
```

Expected:
- filter: `/start`, `/task/{task_id}/status`, `/task/{task_id}/cancel`, `/direct-import`
- library: 原有端点 + `/entries/batch-translate-abstracts` + `/translate-job/{job_id}/status`
