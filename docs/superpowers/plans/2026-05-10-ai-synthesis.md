# AI 文献综述模块实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 compare.py 中新增 /synthesis 和 /synthesis_long 端点，使用 deepseek-reasoner 按维度串行生成高质量文献综述，支持二次引用和 GB/T 7714 参考文献目录。前端修改现有按钮调用新端点。

**Architecture:** 复用 compare.py 中 resolve_compare_members / build_structured_paper_data / ensure_paper_data 等数据解析函数。新增 prompt 构建函数和参考文献处理函数。前端改造现有「生成 AI 综述」按钮，将 API 调用从旧端点切换到新端点。

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, OpenAI SDK (deepseek-reasoner), vanilla JS (HTML pages)

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/routers/compare.py` | 新增请求模型、辅助函数、2 个端点 |
| 修改 | `frontend/public/compare_7step.html` | 改造 btnSynthesis 调用新端点 |
| 修改 | `frontend/public/compare_4step.html` | 改造 btnSynthesis 调用新端点 |
| 修改 | `frontend/public/compare_long.html` | 改造 btnSynthesis 调用新端点 |

不改动：db/models.py（类型已存在）、main.py（router 已注册）、prompt_registry.py（暂不集成）

---

### Task 1: 后端 — 新增请求模型和辅助函数

**Files:**
- Modify: `backend/routers/compare.py` (在现有 LongCompareRequest 之后，约第 48 行)

- [ ] **Step 1: 在 compare.py 顶部新增请求模型和常量**

在 `LongCompareRequest` 类之后（约第 48 行）插入以下代码：

```python
SYNTHESIS_SYSTEM_PROMPT = (
    "你是一位资深的学术文献综述专家。你的任务是根据已完成的精读分析，撰写高质量的"
    "文献综述段落。你必须严格基于所提供的文献内容，不得捏造任何数据或结论。\n\n"
    "你的综述风格要求：\n"
    "- 不写引言和结论，直接以维度名作为小标题开始\n"
    "- 专注每个维度下文献之间的梳理、总结、源流比较和学术对话\n"
    "- 分析现有研究的缺漏和新研究的起点\n"
    "- 引用格式使用间注法：（作者，年份），如（张三等，2024）或（Smith & Jones, 2023）\n"
    "- 转引标注为：（原作者，年份，转引自 引用者，年份）\n"
    "- 不要写参考文献目录，系统会自动生成\n"
)

CONTENT_CHAR_LIMIT = 3000


class SynthesisDimensionRequest(BaseModel):
    dimensions: list[dict] = Field(default_factory=list)
    bib_entry_ids: list[str] = Field(default_factory=list)
    paperData: list = Field(default_factory=list)
    api_key: Optional[str] = None


class SynthesisLongRequest(BaseModel):
    dimensions: list[str] = Field(default_factory=list)
    bib_entry_ids: list[str] = Field(default_factory=list)
    paperData: list = Field(default_factory=list)
    api_key: Optional[str] = None
```

- [ ] **Step 2: 新增二次引用收集函数**

在 `ensure_paper_data()` 函数之后（约第 365 行）插入：

```python
async def gather_bib_references(
    db: AsyncSession,
    members: list[BibEntry],
) -> dict[str, list[dict]]:
    """Collect extracted references (BibReference) for each member paper.
    Returns {bib_entry_id: [{title, authors, year, journal, raw_text}, ...]}
    """
    from backend.db.models import BibReference

    result: dict[str, list[dict]] = {}
    for member in members:
        refs = (
            await db.execute(
                select(BibReference)
                .where(
                    BibReference.source_bib_entry_id == member.id,
                    BibReference.owner_user_id == member.owner_user_id,
                )
                .order_by(BibReference.reference_order.asc())
            )
        ).scalars().all()
        items = []
        for ref in refs:
            authors = json.loads(ref.authors_json or "[]")
            items.append({
                "title": ref.title or "",
                "authors": authors,
                "year": ref.year,
                "journal": ref.journal or "",
                "raw_text": ref.raw_text or "",
            })
        result[member.id] = items
    return result
```

- [ ] **Step 3: 新增引用标注格式化函数**

在 `gather_bib_references()` 之后插入：

```python
def format_cite_tag(authors: list, year) -> str:
    """Format a citation tag for use in prompts: (第一作者姓等, 年份)"""
    if not authors:
        return f"(佚名, {year or 'n.d.'})"
    first = str(authors[0]).strip()
    last_name = first.split()[-1] if first else first
    if len(authors) == 1:
        return f"({last_name}, {year or 'n.d.'})"
    elif len(authors) == 2:
        second = str(authors[1]).strip().split()[-1]
        return f"({last_name} & {second}, {year or 'n.d.'})"
    else:
        return f"({last_name}等, {year or 'n.d.'})"


def format_cite_tag_en(authors: list, year) -> str:
    """English variant: (Smith et al., 2023)"""
    if not authors:
        return f"(佚名, {year or 'n.d.'})"
    first = str(authors[0]).strip()
    last_name = first.split()[-1] if first else first
    if len(authors) == 1:
        return f"({last_name}, {year or 'n.d.'})"
    elif len(authors) == 2:
        second = str(authors[1]).strip().split()[-1]
        return f"({last_name} & {second}, {year or 'n.d.'})"
    else:
        return f"({last_name} et al., {year or 'n.d.'})"
```

- [ ] **Step 4: 新增文献元数据块构建函数**

```python
def build_paper_metadata_block(papers: list[dict], bib_refs: dict[str, list[dict]], members: list[BibEntry]) -> str:
    """Build the fixed-prefix metadata block for prompt caching."""
    lines = [f"以下是 {len(papers)} 篇文献的元信息，用于引用标注：", ""]

    # Build a mapping from bib_entry_id to paper index for cross-referencing refs
    bib_id_to_idx: dict[str, int] = {}
    for i, member in enumerate(members):
        bib_id_to_idx[member.id] = i

    for i, paper in enumerate(papers):
        title = paper.get('title') or paper.get('filename') or '未知'
        authors = paper.get('authors', [])
        year = paper.get('year', 'n.d.')
        journal = paper.get('journal') or paper.get('source') or ''
        cite = format_cite_tag(authors, year)

        lines.append(f"━━━ 文献 {i + 1} ━━━")
        lines.append(f"标题：{title}")
        lines.append(f"作者：{', '.join(str(a) for a in authors) if authors else '佚名'}")
        lines.append(f"年份：{year}")
        if journal:
            lines.append(f"期刊：{journal}")
        lines.append(f"引用标注：{cite}")
        lines.append("")

    # Secondary references
    has_secondary = False
    for i, member in enumerate(members):
        refs = bib_refs.get(member.id, [])
        if not refs:
            continue
        if not has_secondary:
            lines.append("【二次引用信息】")
            lines.append("以下文献在原文中引用了这些参考文献，你可以使用转引方式引用：")
            lines.append("")
            has_secondary = True
        paper = papers[i] if i < len(papers) else {}
        authors_p = paper.get('authors', [])
        year_p = paper.get('year', 'n.d.')
        cite_p = format_cite_tag(authors_p, year_p)
        lines.append(f"━━━ {cite_p} 引用了： ━━━")
        for j, ref in enumerate(refs[:15], 1):
            ref_cite = format_cite_tag(ref.get('authors', []), ref.get('year'))
            ref_title = ref.get('title') or ref.get('raw_text', '')[:60]
            lines.append(f"{j}. {ref_cite} — 标题：{ref_title}")
        lines.append("")

    if not has_secondary:
        lines.append("【二次引用信息】")
        lines.append("当前未提取到这些文献的参考文献数据。")
        lines.append("")

    return "\n".join(lines)
```

- [ ] **Step 5: 新增单维度综述 prompt 构建函数**

```python
def build_synthesis_dimension_prompt(
    dim_label: str,
    papers: list[dict],
    content_field: str = "subQuestions",
) -> str:
    """Build the variable part of the prompt for a single dimension.
    content_field: 'subQuestions' for 7-step/4-step, 'dimensions' for long.
    """
    parts = [
        f"【当前综述维度】{dim_label}",
        "",
        "【写作任务】",
        "请撰写该维度的综述段落，包含以下层次：",
        "1. **梳理与总结**：概述各文献在该维度的核心观点和发现",
        "2. **源流比较**：比较不同文献的研究路径、方法论来源、理论根基的异同",
        "3. **学术对话**：呈现文献间的共识与分歧，构建观点的交锋与呼应",
        "4. **缺漏分析**：识别该维度下现有研究的盲区、方法局限或数据空白",
        "5. **新起点**：基于以上分析，指出未来研究可突破的方向",
        "",
        "【引用要求】",
        "- 正文使用间注法：（第一作者姓等，年份）",
        "- 可使用转引：（被引作者, 年份, 转引自 引用作者, 年份）",
        "- 不要写参考文献目录",
        "",
        "【各文献在该维度的精读内容】",
        "",
    ]

    for i, paper in enumerate(papers):
        cite = format_cite_tag(paper.get('authors', []), paper.get('year', 'n.d.'))
        parts.append(f"━━━ 文献 {i + 1} {cite} ━━━")

        content_dict = paper.get(content_field, {})
        if isinstance(content_dict, dict):
            matched = ""
            for key, value in content_dict.items():
                label = key
                if content_field == "subQuestions" and "]" in key:
                    label = key.split("]", 1)[-1].strip()
                if label == dim_label or dim_label in label:
                    matched = str(value)
                    break
            if not matched:
                for key, value in content_dict.items():
                    if str(value).strip():
                        matched = str(value)
                        break
            parts.append(matched[:CONTENT_CHAR_LIMIT].strip())
        else:
            parts.append(str(content_dict)[:CONTENT_CHAR_LIMIT].strip())
        parts.append("")

    return "\n".join(parts)
```

- [ ] **Step 6: 新增参考文献目录生成函数**

```python
def build_gbt7714_references(
    papers: list[dict],
    bib_refs: dict[str, list[dict]],
    members: list[BibEntry],
) -> str:
    """Build GB/T 7714 reference list. Two sections: primary + secondary."""
    refs = []
    ref_num = 1

    # Primary references (the papers being synthesized)
    for paper in papers:
        authors = paper.get('authors', [])
        year = paper.get('year', 'n.d.')
        title = paper.get('title') or paper.get('filename') or ''
        journal = paper.get('journal') or paper.get('source') or ''
        volume = str(paper.get('volume', '')) if paper.get('volume') else ''
        issue = str(paper.get('issue', '')) if paper.get('issue') else ''
        pages = str(paper.get('pages', '')) if paper.get('pages') else ''
        doi = paper.get('doi', '')

        if not authors:
            author_str = "佚名"
        elif len(authors) <= 3:
            author_str = ", ".join(str(a) for a in authors)
        else:
            author_str = ", ".join(str(a) for a in authors[:3]) + ", 等"

        entry = f"[{ref_num}] {author_str}. {title}[J]."
        if journal:
            entry += f" {journal}"
            if volume:
                entry += f", {volume}"
                if issue:
                    entry += f"({issue})"
            if pages:
                entry += f": {pages}"
            entry += "."
        if doi:
            entry += f" DOI:{doi}"

        cite_tag = format_cite_tag(authors, year)
        refs.append((cite_tag, entry))
        ref_num += 1

    lines = ["---", "", "## 参考文献", ""]
    lines.append("### 主要参考文献", )
    lines.append("")
    for _, entry in refs:
        lines.append(entry)

    # Secondary references
    secondary_items = []
    seen_secondary = set()
    for i, member in enumerate(members):
        paper = papers[i] if i < len(papers) else {}
        authors_p = paper.get('authors', [])
        year_p = paper.get('year', 'n.d.')
        cite_p = format_cite_tag(authors_p, year_p)

        for ref in bib_refs.get(member.id, []):
            ref_authors = ref.get('authors', [])
            ref_year = ref.get('year', 'n.d.')
            ref_cite = format_cite_tag(ref_authors, ref_year)
            dedup_key = f"{ref_cite}_{ref.get('title', '')}"
            if dedup_key in seen_secondary:
                continue
            # Skip if same as primary
            primary_cites = {format_cite_tag(p.get('authors', []), p.get('year', 'n.d.')) for p in papers}
            if ref_cite in primary_cites:
                continue
            seen_secondary.add(dedup_key)

            author_str = ", ".join(str(a) for a in ref_authors) if ref_authors else "佚名"
            ref_title = ref.get('title') or ref.get('raw_text', '')[:80]
            ref_journal = ref.get('journal', '')
            entry = f"[{ref_num}] {author_str}. {ref_title}[J]."
            if ref_journal:
                entry += f" {ref_journal}."
            entry += f" (转引自: {cite_p})"

            secondary_items.append(entry)
            ref_num += 1

    if secondary_items:
        lines.append("")
        lines.append("### 二次引用文献")
        lines.append("")
        lines.extend(secondary_items)

    return "\n".join(lines)
```

- [ ] **Step 7: 新增产物存储函数**

```python
async def persist_synthesis_result(
    db: AsyncSession,
    user: User,
    job_id: str,
    filename: str,
    content: str,
) -> str:
    result_dir = get_results_dir(user.id, job_id)
    path = result_dir / filename
    path.write_text(content, encoding="utf-8")
    storage_path = build_storage_path(path)
    db.add(
        Artifact(
            job_id=job_id,
            owner_user_id=user.id,
            artifact_type="synthesis_md",
            filename=filename,
            storage_path=storage_path,
            size_bytes=path.stat().st_size,
            expires_at=compute_expires_at(user),
        )
    )
    return storage_path
```

- [ ] **Step 8: 验证代码无语法错误**

Run: `python -c "from backend.routers.compare import router; print('OK')"`
Expected: OK

- [ ] **Step 9: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): add helper functions for AI literature synthesis"
```

---

### Task 2: 后端 — 新增 /synthesis 端点（七步/四步）

**Files:**
- Modify: `backend/routers/compare.py` (在文件末尾，/analyze_long 之后)

- [ ] **Step 1: 新增 POST /synthesis 端点**

在文件末尾追加：

```python
@router.post("/synthesis")
async def synthesize_dimensions(
    req: SynthesisDimensionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI literature synthesis for 7-step/4-step dimensions using deepseek-reasoner."""
    try:
        from openai import OpenAI

        members = await resolve_compare_members(db, user, req.bib_entry_ids, req.paperData)
        paper_data = await ensure_paper_data(db, req.paperData, members)
        bib_refs = await gather_bib_references(db, members)

        dimensions = req.dimensions
        if not dimensions:
            raise HTTPException(status_code=400, detail="请至少选择 1 个维度")

        job_id = await create_compare_job(
            db, user, "synthesis",
            {"dimensions": dimensions, "mode": "synthesis"},
            members,
        )
        job = await db.get(Job, job_id)
        job.status = "running"
        job.progress = 10
        job.current_stage = "准备综述..."
        job.started_at = utcnow_naive()
        await db.flush()

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        metadata_block = build_paper_metadata_block(paper_data, bib_refs, members)

        dimension_sections = []
        total = len(dimensions)
        for idx, dim_info in enumerate(dimensions):
            dim_label = dim_info.get("label", f"维度{idx + 1}")

            job.current_stage = f"正在生成维度 {idx + 1}/{total}：{dim_label}"
            job.progress = 10 + int(80 * idx / total)
            await db.flush()

            dim_prompt = build_synthesis_dimension_prompt(dim_label, paper_data, "subQuestions")
            user_message = metadata_block + "\n\n" + dim_prompt

            response = client.chat.completions.create(
                model="deepseek-reasoner",
                messages=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=4000,
            )

            content = response.choices[0].message.content
            dimension_sections.append({"label": dim_label, "content": content or ""})

        # Assemble
        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        references = build_gbt7714_references(paper_data, bib_refs, members)
        final_text = synthesis_body + "\n\n" + references

        title_parts = [d.get("label", "") for d in dimensions[:3]]
        if len(dimensions) > 3:
            title_parts.append(f"等{len(dimensions)}个维度")
        title = "AI文献综述：" + "、".join(title_parts)

        full_md = build_compare_markdown(title, final_text)

        job.current_stage = "保存结果..."
        job.progress = 95
        await db.flush()

        storage_path = await persist_synthesis_result(
            db, user, job_id,
            f"synthesis_{job_id[:8]}.md",
            full_md,
        )

        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.finished_at = utcnow_naive()
        await db.commit()

        return {
            "synthesis": final_text,
            "job_id": job_id,
            "output_path": storage_path,
            "dimension_sections": dimension_sections,
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_msg = str(e)
                job.finished_at = utcnow_naive()
                await db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: 验证路由注册**

Run: `python -c "from backend.routers.compare import router; paths = [r.path for r in router.routes]; print(paths)"`
Expected: 列表中包含 `/synthesis`

- [ ] **Step 3: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): add POST /synthesis endpoint for 7-step/4-step"
```

---

### Task 3: 后端 — 新增 /synthesis_long 端点（长文本）

**Files:**
- Modify: `backend/routers/compare.py` (在 /synthesis 端点之后追加)

- [ ] **Step 1: 新增 POST /synthesis_long 端点**

```python
@router.post("/synthesis_long")
async def synthesize_long_dimensions(
    req: SynthesisLongRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI literature synthesis for long-context dimensions using deepseek-reasoner."""
    try:
        from openai import OpenAI

        members = await resolve_compare_members(db, user, req.bib_entry_ids, req.paperData)
        paper_data = await ensure_paper_data(db, req.paperData, members)
        bib_refs = await gather_bib_references(db, members)

        dimensions = req.dimensions
        if not dimensions:
            raise HTTPException(status_code=400, detail="请至少选择 1 个维度")

        job_id = await create_compare_job(
            db, user, "synthesis",
            {"dimensions": dimensions, "mode": "synthesis_long"},
            members,
        )
        job = await db.get(Job, job_id)
        job.status = "running"
        job.progress = 10
        job.current_stage = "准备长综述..."
        job.started_at = utcnow_naive()
        await db.flush()

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        metadata_block = build_paper_metadata_block(paper_data, bib_refs, members)

        dimension_sections = []
        total = len(dimensions)
        for idx, dim_label in enumerate(dimensions):
            job.current_stage = f"正在生成维度 {idx + 1}/{total}：{dim_label}"
            job.progress = 10 + int(80 * idx / total)
            await db.flush()

            dim_prompt = build_synthesis_dimension_prompt(dim_label, paper_data, "dimensions")
            user_message = metadata_block + "\n\n" + dim_prompt

            response = client.chat.completions.create(
                model="deepseek-reasoner",
                messages=[
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=4000,
            )

            content = response.choices[0].message.content
            dimension_sections.append({"label": dim_label, "content": content or ""})

        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        references = build_gbt7714_references(paper_data, bib_refs, members)
        final_text = synthesis_body + "\n\n" + references

        dim_labels_joined = "、".join(dimensions[:3])
        if len(dimensions) > 3:
            dim_labels_joined += f"等{len(dimensions)}个维度"
        title = f"AI文献综述：{dim_labels_joined}"

        full_md = build_compare_markdown(title, final_text)

        storage_path = await persist_synthesis_result(
            db, user, job_id,
            f"synthesis_long_{job_id[:8]}.md",
            full_md,
        )

        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.finished_at = utcnow_naive()
        await db.commit()

        return {
            "synthesis": final_text,
            "job_id": job_id,
            "output_path": storage_path,
            "dimension_sections": dimension_sections,
        }

    except HTTPException:
        raise
    except Exception as e:
        try:
            job = await db.get(Job, job_id)
            if job:
                job.status = "failed"
                job.error_msg = str(e)
                job.finished_at = utcnow_naive()
                await db.commit()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))
```

- [ ] **Step 2: 验证两个新端点都注册成功**

Run: `python -c "from backend.routers.compare import router; paths = [r.path for r in router.routes]; print(paths)"`
Expected: 列表中包含 `/synthesis` 和 `/synthesis_long`

- [ ] **Step 3: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): add POST /synthesis_long endpoint for long-context"
```

---

### Task 4: 前端 — 改造 compare_7step.html 的 AI 综述按钮

**Files:**
- Modify: `frontend/public/compare_7step.html` (约第 800-909 行)

- [ ] **Step 1: 替换 btnSynthesis 的 onclick 处理函数**

将 `compare_7step.html` 中第 800-909 行（`document.getElementById('btnSynthesis').onclick = async () => {` ... `};`）整体替换为以下代码：

```javascript
    document.getElementById('btnSynthesis').onclick = async () => {
      if (selectedPapers.length < 2) {
        alert('请至少选择两篇文献');
        return;
      }
      if (selectedSubQuestions.size === 0) {
        alert('请至少选择一个问题');
        return;
      }

      const modal = document.getElementById('modalOverlay');
      const loading = document.getElementById('synthesisLoading');
      const content = document.getElementById('synthesisContent');

      modal.classList.add('active');
      loading.style.display = 'block';
      content.style.display = 'none';

      const papers = allReports.filter(r => selectedPapers.includes(r.filename));
      const selectedEntries = Array.from(selectedSubQuestions).map(parseQuestionKey).filter(entry => entry.stepId && entry.questionLabel);
      const selectedStepIds = Array.from(new Set(selectedEntries.map(entry => entry.stepId)));

      // Build dimensions array with step info
      const dimensions = Array.from(selectedSubQuestions).map(key => {
        const { stepId, questionLabel } = parseQuestionKey(key);
        return { label: questionLabel, step: getStepLabel(stepId) };
      });

      const paperData = papers.map(paper => {
        const meta = buildPaperMeta(paper);
        const selectedContent = {};
        for (const key of selectedSubQuestions) {
          const { stepId, questionLabel } = parseQuestionKey(key);
          const allSubQs = getPaperSubQuestions(paper, stepId);
          if (allSubQs[questionLabel]) {
            selectedContent[questionLabel] = allSubQs[questionLabel];
          }
        }
        return { ...meta, subQuestions: selectedContent };
      });

      try {
        const apiKey = promptForApiKey();
        if (!apiKey) { alert('请先设置 DeepSeek API Key'); return; }
        const response = await authFetch('/api/compare/synthesis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dimensions: dimensions,
            paperData: paperData,
            api_key: apiKey,
          })
        });

        const result = await response.json();

        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = result.synthesis || '生成失败';

        const actions = document.getElementById('synthesisActions');
        actions.style.display = 'block';

        const dimLabels = dimensions.map(d => d.label);
        document.getElementById('btnDownloadSynthesis').onclick = async () => {
          try {
            const saveRes = await authFetch('/api/history/synthesis/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                dimension: dimLabels.join('、') + `（${dimLabels.length}个维度）`,
                papers: paperData.map(p => p.title || p.filename),
                content: result.synthesis
              })
            });
            const saveData = await saveRes.json();
            if (saveData.success) {
              alert('✓ 已保存到历史记录');
            } else {
              alert('保存失败');
            }
          } catch (e) {
            alert('保存失败: ' + e.message);
          }
        };
      } catch (e) {
        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = '生成失败: ' + e.message;
      }
    };
```

**关键变更点：**
- API 路径从 `/api/compare/analyze` 改为 `/api/compare/synthesis`
- 请求体从 `{ step, papers, subQuestions, paperData, mode }` 改为 `{ dimensions, paperData }`
- dimensions 格式为 `[{ label, step }, ...]`，每个选中的子问题一个条目
- 不再需要 mode/step/subQuestions 字段

- [ ] **Step 2: 验证前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/public/compare_7step.html
git commit -m "feat(synthesis): switch 7-step page to new /synthesis endpoint"
```

---

### Task 5: 前端 — 改造 compare_4step.html 的 AI 综述按钮

**Files:**
- Modify: `frontend/public/compare_4step.html` (约第 693-778 行)

- [ ] **Step 1: 替换 btnSynthesis 的 onclick 处理函数**

将第 693-778 行整体替换为：

```javascript
    document.getElementById('btnSynthesis').onclick = async () => {
      if (selectedPapers.length < 2) { alert('请至少选择两篇文献'); return; }
      if (selectedSubQuestions.size === 0) { alert('请至少选择一个问题'); return; }
      const modal = document.getElementById('modalOverlay');
      const loading = document.getElementById('synthesisLoading');
      const content = document.getElementById('synthesisContent');
      modal.classList.add('active');
      loading.style.display = 'block';
      content.style.display = 'none';

      const papers = allReports.filter(r => selectedPapers.includes(r.filename));
      const selectedEntries = Array.from(selectedSubQuestions).map(parseQuestionKey).filter(entry => entry.stepId && entry.questionLabel);

      const dimensions = Array.from(selectedSubQuestions).map(key => {
        const { stepId, questionLabel } = parseQuestionKey(key);
        return { label: questionLabel, step: getStepLabel(stepId) };
      });

      const paperData = papers.map(paper => {
        const meta = buildPaperMeta(paper);
        const selectedContent = {};
        for (const key of selectedSubQuestions) {
          const { stepId, questionLabel } = parseQuestionKey(key);
          const allSubQs = getPaperSubQuestions(paper, stepId);
          if (allSubQs[questionLabel]) selectedContent[questionLabel] = allSubQs[questionLabel];
        }
        return { ...meta, subQuestions: selectedContent };
      });

      try {
        const apiKey = promptForApiKey();
        if (!apiKey) { alert('请先设置 DeepSeek API Key'); return; }
        const response = await authFetch('/api/compare/synthesis', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dimensions: dimensions,
            paperData: paperData,
            api_key: apiKey,
          })
        });
        const result = await response.json();

        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = result.synthesis || '生成失败';

        const actions = document.getElementById('synthesisActions');
        actions.style.display = 'block';

        const dimLabels = dimensions.map(d => d.label);
        document.getElementById('btnDownloadSynthesis').onclick = async () => {
          try {
            const saveRes = await authFetch('/api/history/synthesis/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                dimension: dimLabels.join('、') + `（${dimLabels.length}个维度）`,
                papers: paperData.map(p => p.title || p.filename),
                content: result.synthesis
              })
            });
            const saveData = await saveRes.json();
            if (saveData.success) alert('✓ 已保存到历史记录');
            else alert('保存失败');
          } catch (e) { alert('保存失败: ' + e.message); }
        };
      } catch (e) {
        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = '生成失败: ' + e.message;
      }
    };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/public/compare_4step.html
git commit -m "feat(synthesis): switch 4-step page to new /synthesis endpoint"
```

---

### Task 6: 前端 — 改造 compare_long.html 的 AI 综述按钮

**Files:**
- Modify: `frontend/public/compare_long.html` (约第 629-722 行)

- [ ] **Step 1: 替换 btnSynthesis 的 onclick 处理函数**

将第 629-722 行整体替换为：

```javascript
    document.getElementById('btnSynthesis').onclick = async () => {
      if (selectedDims.size === 0 || selectedPapers.length === 0) return;

      const modal = document.getElementById('modalOverlay');
      const loading = document.getElementById('synthesisLoading');
      const content = document.getElementById('synthesisContent');
      modal.classList.add('active');
      loading.style.display = 'block';
      content.style.display = 'none';

      const dims = Array.from(selectedDims);
      const papers = allReports.filter(r => selectedPapers.includes(r.filename));

      const paperData = papers.map(paper => {
        const fm = paper.frontmatter;
        const base = {
          filename: paper.filename,
          title: fm.title || paper.filename,
          authors: fm.authors || [],
          year: fm.year,
          journal: fm.journal || fm.source || fm['期刊'] || '',
          volume: fm.volume || fm['卷'] || '',
          issue: fm.issue || fm['期'] || '',
          pages: fm.pages || fm['页码'] || '',
          doi: fm.doi || '',
        };
        const dimensions = {};
        for (const dim of dims) {
          const c = getDimensionContent(paper.content, dim);
          if (c && c.trim()) dimensions[dim] = c;
        }
        return { ...base, dimensions };
      }).filter(p => Object.keys(p.dimensions || {}).length > 0);

      if (paperData.length === 0) {
        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = '所选文献均未包含所选维度的内容，无法生成综述。';
        return;
      }

      try {
        const apiKey = promptForApiKey();
        if (!apiKey) { alert('请先设置 DeepSeek API Key'); return; }
        const response = await authFetch('/api/compare/synthesis_long', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            dimensions: dims,
            paperData: paperData,
            api_key: apiKey,
          })
        });
        const result = await response.json();
        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = result.synthesis || '生成失败';

        const actions = document.getElementById('synthesisActions');
        actions.style.display = 'block';

        document.getElementById('btnDownloadSynthesis').onclick = async () => {
          try {
            const saveRes = await authFetch('/api/history/synthesis/', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                dimension: dims.join('、'),
                papers: paperData.map(p => p.title || p.filename),
                content: result.synthesis
              })
            });
            const saveData = await saveRes.json();
            if (saveData.success) alert('✓ 已保存到历史记录');
            else alert('保存失败');
          } catch (e) { alert('保存失败: ' + e.message); }
        };
      } catch (e) {
        loading.style.display = 'none';
        content.style.display = 'block';
        content.textContent = '生成失败: ' + e.message;
      }
    };
```

**关键变更点：**
- API 路径从 `/api/compare/analyze_long` 改为 `/api/compare/synthesis_long`
- 不再区分 single/multi mode，统一传 dimensions 数组
- 始终构造 dimensions dict 而非 content string

- [ ] **Step 2: 验证前端构建**

Run: `cd frontend && npm run build`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/public/compare_long.html
git commit -m "feat(synthesis): switch long-context page to new /synthesis_long endpoint"
```

---

### Task 7: 修复 build_synthesis_dimension_prompt 中的内容匹配逻辑

**Files:**
- Modify: `backend/routers/compare.py` (build_synthesis_dimension_prompt 函数)

- [ ] **Step 1: 改进维度内容匹配算法**

Task 1 中的 `build_synthesis_dimension_prompt` 函数对 subQuestions 的匹配逻辑需要更精确。现有 subQuestions 的 key 有两种格式：
- 七步/四步：`[第一步] 研究问题` 或纯 `研究问题`
- 长文本：维度名直接作为 key

替换 `build_synthesis_dimension_prompt` 中 content_dict 匹配部分的逻辑为：

```python
def _match_dimension_content(content_dict: dict, dim_label: str) -> str:
    """Try to find the content for a specific dimension label in the content dict."""
    # Exact match
    if dim_label in content_dict:
        return str(content_dict[dim_label])

    # Match without step prefix: "[第一步] 研究问题" -> "研究问题"
    for key, value in content_dict.items():
        if "]" in key:
            clean = key.split("]", 1)[-1].strip()
            if clean == dim_label:
                return str(value)

    # Partial match
    for key, value in content_dict.items():
        if dim_label in key or key in dim_label:
            return str(value)

    # Fallback: return all concatenated
    parts = [str(v).strip() for v in content_dict.values() if str(v).strip()]
    return "\n\n".join(parts) if parts else ""
```

然后在 `build_synthesis_dimension_prompt` 中使用此函数替换原来的匹配逻辑：

```python
        content_dict = paper.get(content_field, {})
        if isinstance(content_dict, dict):
            matched = _match_dimension_content(content_dict, dim_label)
            parts.append(matched[:CONTENT_CHAR_LIMIT].strip())
```

- [ ] **Step 2: Commit**

```bash
git add backend/routers/compare.py
git commit -m "fix(synthesis): improve dimension content matching in prompt builder"
```

---

### Task 8: 端到端验证

- [ ] **Step 1: 启动后端**

Run: `uvicorn backend.main:app --reload --port 8000`

- [ ] **Step 2: 启动前端**

Run: `cd frontend && npm run dev`

- [ ] **Step 3: 验证路由注册**

Run: `python -c "from backend.routers.compare import router; [print(r.path, r.methods) for r in router.routes]"`
Expected: 输出中包含 `/synthesis` 和 `/synthesis_long`，methods 包含 POST

- [ ] **Step 4: 手动测试（记录结果）**

测试清单：
1. 七步对比页面：选 2+ 篇文献 → 选 1 个子问题 → 点击「AI 综述」→ 确认调用 /api/compare/synthesis → 等待结果
2. 七步对比页面：选多个子问题 → 跨步骤选择 → 点击「AI 综述」→ 确认每个维度有独立小节
3. 四步对比页面：同上
4. 长文本对比页面：选维度 → 点击「AI 综述」→ 确认调用 /synthesis_long
5. 确认结果中有（作者，年份）引用标注
6. 确认文末有 GB/T 7714 参考文献目录
7. 确认「保存到历史记录」功能正常
8. 确认文献库时间线中出现 synthesis_md 产物

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix(synthesis): address issues found during end-to-end testing"
```
