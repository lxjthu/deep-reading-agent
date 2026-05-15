# MD 文件元数据提取兼容 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让精读（长文本/七步/四步）完成后，对 MD 文件也能正确提取元数据，不再因 `pdfplumber` 抛出 `PDFSyntaxError("No /Root object!")` 导致整个任务失败。

**Architecture:** 在 `pdf_metadata_extract.py` 的 `extract_front_matter()` 中增加 MD 文件分支，读取 MD 头部文本填充到与 PDF 相同的 dict 结构中。`pdf_metadata_llm.py` 的 `extract_metadata_with_llm()` 无需修改，因为它只消费 dict。`reading.py` 中三处调用点也不需要改，因为 `extract_front_matter()` 内部已经透明处理了文件类型。同时用 `try/except` 包裹元数据提取调用，使其失败不阻断精读主流程。

**Tech Stack:** Python 3, pdfplumber (PDF), 标准 open() (MD)

---

### Task 1: 在 `extract_front_matter()` 中增加 MD 文件分支

**Files:**
- Modify: `backend/services/pdf_metadata_extract.py:58-107`

- [ ] **Step 1: 添加 `_is_markdown()` 辅助函数和 `extract_front_matter_md()` 函数**

在 `pdf_metadata_extract.py` 的 `extract_front_matter()` 函数**之前**，添加两个新函数：

```python
def _is_markdown(file_path: str) -> bool:
    return file_path.lower().endswith((".md", ".markdown"))


def extract_front_matter_md(md_path: str, max_lines: int = 150) -> dict:
    """
    Extract metadata-relevant text from a Markdown file.

    Reads the first ~max_lines of the file and maps them into the same
    dict structure that extract_front_matter() returns for PDFs, so
    downstream consumers (extract_metadata_with_llm) work unchanged.
    """
    result = {
        "page_1_full": "",
        "page_2_header": "",
        "page_3_header": "",
        "doi_candidates": [],
        "isbn_candidates": [],
        "total_pages": 0,
    }

    if not Path(md_path).exists():
        return result

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
    except Exception:
        return result

    full_text = "\n".join(lines)
    result["page_1_full"] = full_text
    # For MD files there are no "pages 2/3", but we can populate
    # page_2/3_header with later portions to give the LLM more context.
    chunk_size = max(max_lines // 3, 10)
    if len(lines) > chunk_size:
        result["page_2_header"] = "\n".join(lines[chunk_size : chunk_size * 2])
    if len(lines) > chunk_size * 2:
        result["page_3_header"] = "\n".join(lines[chunk_size * 2 : chunk_size * 3])

    result["doi_candidates"] = extract_dois(full_text)
    result["isbn_candidates"] = extract_isbns(full_text)
    result["total_pages"] = 1

    return result
```

- [ ] **Step 2: 修改 `extract_front_matter()` 入口，增加文件类型判断**

将原 `extract_front_matter()` 函数体改为先判断文件类型：

```python
def extract_front_matter(pdf_path: str, max_pages: int = 3) -> dict:
    """
    Extract metadata-relevant text from the first 1-3 pages of a PDF
    or the first ~150 lines of a Markdown file.
    """
    if _is_markdown(pdf_path):
        return extract_front_matter_md(pdf_path)

    result = {
        "page_1_full": "",
        "page_2_header": "",
        "page_3_header": "",
        "doi_candidates": [],
        "isbn_candidates": [],
        "total_pages": 0,
    }

    if not Path(pdf_path).exists():
        return result

    with pdfplumber.open(pdf_path) as pdf:
        result["total_pages"] = len(pdf.pages)

        if len(pdf.pages) >= 1:
            page1 = pdf.pages[0]
            result["page_1_full"] = page1.extract_text() or ""

        if len(pdf.pages) >= 2:
            page2 = pdf.pages[1]
            result["page_2_header"] = extract_page_header(page2)

        if len(pdf.pages) >= 3:
            page3 = pdf.pages[2]
            result["page_3_header"] = extract_page_header(page3)

    combined_text = "\n".join([
        result["page_1_full"],
        result["page_2_header"],
        result["page_3_header"],
    ])

    result["doi_candidates"] = extract_dois(combined_text)
    result["isbn_candidates"] = extract_isbns(combined_text)

    return result
```

- [ ] **Step 3: 验证模块导入无误**

Run: `python -c "from backend.services.pdf_metadata_extract import extract_front_matter; print('OK')"`
Expected: `OK`

---

### Task 2: 保护精读任务中元数据提取不阻断主流程

**Files:**
- Modify: `backend/routers/reading.py` (3 处精读函数)

当前三处精读函数（长文本 `~970`、七步 `~1118`、四步 `~1254`）中，元数据提取调用**不在 try/except 保护内**，一旦 `extract_front_matter()` 或 `extract_metadata_with_llm()` 抛异常，整个任务就被外层 `except Exception` 捕获，标记为 `failed`。

需要用 try/except 包裹每个精读函数中的元数据提取代码块，让元数据提取失败时仅记录日志，不中断报告生成。

- [ ] **Step 1: 在长文本精读中保护元数据提取**

找到长文本精读函数中（约 `reading.py:969-974`）：

```python
        # Extract metadata from PDF front matter
        tasks[task_id]["stage"] = "提取论文元数据..."
        tasks[task_id]["logs"].append("提取论文元数据...")
        front_matter = extract_front_matter(file_path)
        metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
        tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
```

替换为：

```python
        # Extract metadata from front matter (tolerant — never fail the main task)
        metadata = None
        try:
            tasks[task_id]["stage"] = "提取论文元数据..."
            tasks[task_id]["logs"].append("提取论文元数据...")
            front_matter = extract_front_matter(file_path)
            metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {exc}")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()
```

- [ ] **Step 2: 在七步精读中保护元数据提取**

找到七步精读函数中（约 `reading.py:1115-1120`），做相同的包裹处理：

```python
        # Extract metadata from front matter (tolerant — never fail the main task)
        metadata = None
        try:
            tasks[task_id]["stage"] = "提取论文元数据..."
            tasks[task_id]["logs"].append("提取论文元数据...")
            front_matter = extract_front_matter(file_path)
            metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {exc}")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()
```

- [ ] **Step 3: 在四步精读中保护元数据提取**

找到四步精读函数中（约 `reading.py:1251-1256`），做相同的包裹处理：

```python
        # Extract metadata from front matter (tolerant — never fail the main task)
        metadata = None
        try:
            tasks[task_id]["stage"] = "提取论文元数据..."
            tasks[task_id]["logs"].append("提取论文元数据...")
            front_matter = extract_front_matter(file_path)
            metadata = extract_metadata_with_llm(front_matter, original_name, api_key=api_key)
            tasks[task_id]["logs"].append(f"✓ 元数据提取完成: {metadata.get('title', '未知标题')}")
        except Exception as exc:
            tasks[task_id]["logs"].append(f"⚠ 元数据提取跳过: {exc}")
        if not metadata:
            from backend.services.pdf_metadata_llm import _empty_metadata
            metadata = _empty_metadata()
```

- [ ] **Step 4: 验证模块导入无误**

Run: `python -c "from backend.routers.reading import router; print(len(router.routes), 'routes OK')"`
Expected: 输出路由数量，无 import 错误

---

### Task 3: 验证参考文献提取对 MD 文件已兼容

**Files:**
- Read-only: `backend/services/deepseek_refs.py`

- [ ] **Step 1: 确认 `deepseek_refs.py` 已正确处理 MD**

`deepseek_refs.py` 的 `extract_references_deepseek()` 在 `line 304` 通过 `_is_markdown(file_path)` 判断文件类型：
- MD 文件 → `extract_candidate_text_md(file_path)` (`line 307`)
- PDF 文件 → `extract_candidate_text(file_path)` (`line 309`)

`trace_citations_deepseek()` (`line 383`) 同样有 `_is_markdown()` 分支。

**结论：参考文献提取已兼容 MD，无需修改。**

---

### Task 4: 端到端验证

- [ ] **Step 1: 启动后端，上传一个 .md 文件执行四步精读**

Run: `uvicorn backend.main:app --reload --port 8000`

操作：上传 `.md` 文件 → 触发四步精读 → 观察日志不再出现 `No /Root object` 错误，精读正常完成。

- [ ] **Step 2: 同样验证 PDF 文件精读未回归**

操作：上传 `.pdf` 文件 → 触发精读 → 元数据正常提取，无报错。
