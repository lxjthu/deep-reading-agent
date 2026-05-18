# AI 综述二次引用目录过滤 + 引用兜底修复 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AI 综述模块的两个核心问题：(1) `build_gbt7714_references()` 将所有 BibReference 放入二次引用目录导致膨胀，应只保留正文实际引用过的条目；(2) `None` 年份穿透、`n.d.` 中英文不一致等引用兜底问题。

**Architecture:** 在综述正文全部维度拼接完成后，扫描全文中的 `(作者, 年份)` 引用标注构建「已引用集合」，然后二次引用目录只保留被实际引用的条目。同时统一修复所有引用格式函数的 `None` 兜底，确保输出一致。所有改动集中在 `backend/routers/compare.py`。

**Tech Stack:** Python 3, FastAPI, SQLAlchemy 2.0 async, re (正则)

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/routers/compare.py` | 修复 `format_cite_tag`、`build_gbt7714_references`、新增 `extract_cited_tags` 函数，修改两个端点调用逻辑 |

不改动：前端文件（此问题纯后端）、数据库模型、其他 router。

---

### Task 1: 修复 `format_cite_tag` 的 None 年份兜底

**Files:**
- Modify: `backend/routers/compare.py` (line 428-439)

**问题：** 当 `year` 为 `None` 时，`year or 'n.d.'` 输出 `'n.d.'`（英文），但系统提示词要求中文间注法，且中文文献不应出现 `n.d.`。

- [ ] **Step 1: 修改 `format_cite_tag` 函数**

将 line 428-439 整体替换为：

```python
def format_cite_tag(authors: list, year) -> str:
    year_display = year if year else "年份不详"
    if not authors:
        return f"(佚名, {year_display})"
    first = str(authors[0]).strip()
    last_name = first.split()[-1] if first else first
    if len(authors) == 1:
        return f"({last_name}, {year_display})"
    elif len(authors) == 2:
        second = str(authors[1]).strip().split()[-1]
        return f"({last_name} & {second}, {year_display})"
    else:
        return f"({last_name}等, {year_display})"
```

**变更点：**
- `year or 'n.d.'` → `year if year else "年份不详"`
- 无作者分支统一使用 `year_display`（原来漏了兜底）

- [ ] **Step 2: 同步修复 `format_inline_citation`**

将 line 665-678 整体替换为：

```python
def format_inline_citation(authors: list, year) -> str:
    year_display = year if year else "年份不详"
    if not authors:
        return f"(佚名, {year_display})"
    first = authors[0].strip()
    last_name = first.split()[-1] if first else first
    if len(authors) == 1:
        return f"({last_name}, {year_display})"
    elif len(authors) == 2:
        second = authors[1].strip().split()[-1]
        return f"({last_name} & {second}, {year_display})"
    else:
        return f"({last_name} et al., {year_display})"
```

**变更点：**
- 同上 `None` 兜底修复
- 无作者时原来直接 `(佚名, {year})` 会输出 `(佚名, None)`，现在统一为 `(佚名, 年份不详)`

- [ ] **Step 3: 验证路由注册无报错**

Run: `python -c "from backend.routers.compare import router; [print(r.path) for r in router.routes]"`
Expected: 列出所有路由，无 import 报错

- [ ] **Step 4: Commit**

```bash
git add backend/routers/compare.py
git commit -m "fix(synthesis): unify year None fallback to '年份不详' in citation formatters"
```

---

### Task 2: 修复 `build_paper_metadata_block` 和 `build_gbt7714_references` 中的 `None` 兜底

**Files:**
- Modify: `backend/routers/compare.py` (line 442-637)

**问题：** `paper.get('year', 'n.d.')` 当 key 存在但 value 为 `None` 时返回 `None` 而非 `'n.d.'`。`dict.get(key, default)` 只在 key 不存在时返回 default，key 存在但值为 `None` 时返回 `None`。

- [ ] **Step 1: 新增统一年份取值辅助函数**

在 `format_cite_tag` 函数之后（约 line 440 之后）插入：

```python
def _safe_year(year) -> str:
    return str(year) if year else "年份不详"
```

- [ ] **Step 2: 修复 `build_paper_metadata_block` 中的年份取值**

将 `build_paper_metadata_block` 函数中所有 `paper.get('year', 'n.d.')` 替换为 `_safe_year(paper.get('year'))`。

具体替换（共 3 处）：

1. line 452 附近：
   ```python
   # 原：year = paper.get('year', 'n.d.')
   # 改为：
   year = _safe_year(paper.get('year'))
   ```

2. line 477 附近（二次引用循环内）：
   ```python
   # 原：year_p = paper.get('year', 'n.d.')
   # 改为：
   year_p = _safe_year(paper.get('year'))
   ```

- [ ] **Step 3: 修复 `build_gbt7714_references` 中的年份取值**

将 `build_gbt7714_references` 函数中所有 `paper.get('year', 'n.d.')` 和 `ref.get('year', 'n.d.')` 替换为 `_safe_year(...)` 调用。

具体替换（共 3 处）：

1. line 562 附近（主要参考文献循环）：
   ```python
   # 原：year = paper.get('year', 'n.d.')
   # 改为：
   year = _safe_year(paper.get('year'))
   ```

2. line 605 附近（二次引用的父文献）：
   ```python
   # 原：year_p = paper.get('year', 'n.d.')
   # 改为：
   year_p = _safe_year(paper.get('year'))
   ```

3. line 610 附近（二次引用条目本身）：
   ```python
   # 原：ref_year = ref.get('year', 'n.d.')
   # 改为：
   ref_year = _safe_year(ref.get('year'))
   ```

- [ ] **Step 4: 同步修复 `build_synthesis_dimension_prompt` 中的年份取值**

将 line 538 附近：
```python
# 原：cite = format_cite_tag(paper.get('authors', []), paper.get('year', 'n.d.'))
# 改为：
cite = format_cite_tag(paper.get('authors', []), _safe_year(paper.get('year')))
```

- [ ] **Step 5: 同步修复 `build_reference_list` 和 `build_paper_header` 中的年份取值**

`build_reference_list` (line 690 附近)：
```python
# 原：year = paper.get('year', 'n.d.')
# 改为：
year = _safe_year(paper.get('year'))
```

`build_paper_header` (line 681 附近)：
```python
# 原：year = paper.get('year', 'n.d.')
# 改为：
year = _safe_year(paper.get('year'))
```

- [ ] **Step 6: 验证路由注册无报错**

Run: `python -c "from backend.routers.compare import router; [print(r.path) for r in router.routes]"`
Expected: 列出所有路由，无 import 报错

- [ ] **Step 7: Commit**

```bash
git add backend/routers/compare.py
git commit -m "fix(synthesis): fix None year penetration in metadata block and reference list"
```

---

### Task 3: 新增 `extract_cited_tags` — 从综述正文提取所有已引用的 cite_tag

**Files:**
- Modify: `backend/routers/compare.py` (在 `_safe_year` 之后插入)

**目标：** 扫描综述正文，提取所有 `(作者, 年份)` 格式的引用标注，返回去重集合。用于后续过滤二次引用目录。

- [ ] **Step 1: 新增 `extract_cited_tags` 函数**

在 `_safe_year` 函数之后插入：

```python
_CITE_PATTERN = re.compile(
    r'\('
    r'([^,，)]+?)'                    # author part
    r'\s*[,\uff0c]\s*'                # comma (half/full width)
    r'(\d{4}|年份不详|n\.d\.)'         # year part
    r'(?:\s*,\s*转引自\s*[^)]+)?'      # optional secondary citation suffix
    r'\)',
    re.UNICODE,
)


def extract_cited_tags(text: str) -> set[str]:
    """Extract all citation tags like '(Smith, 2023)' from synthesis body.
    Returns a set of strings like {'(Smith, 2023)', '(张三等, 2024)'}.
    """
    tags = set()
    for m in _CITE_PATTERN.finditer(text):
        author_part = m.group(1).strip()
        year_part = m.group(2).strip()
        tags.add(f"({author_part}, {year_part})")
    return tags
```

**设计说明：**
- 正则匹配 `(作者, 年份)` 和 `(作者，年份)`（全角逗号）
- 支持 `转引自` 后缀（二次引用格式如 `(Wang, 2020, 转引自 Smith等, 2023)`）
- 返回的是「原始引用标注字符串集合」，用于后续与 `format_cite_tag()` 的输出做模糊匹配
- 年份部分支持 `\d{4}`、`年份不详`、`n.d.` 三种形式

- [ ] **Step 2: 新增 `_cite_tag_match` 模糊匹配函数**

在 `extract_cited_tags` 之后插入：

```python
def _cite_tag_match(cite_tag: str, cited_tags: set[str]) -> bool:
    """Check if a format_cite_tag() output matches any cited tag in the text.

    format_cite_tag() produces '(Smith, 2023)' or '(张三等, 2024)'.
    The LLM may produce slight variations. We do fuzzy matching:
    - Exact match
    - Match without trailing 等/et al.
    - Match author part only (in case year format differs)
    """
    if cite_tag in cited_tags:
        return True
    author_in_tag = cite_tag.split(",")[0].strip().lstrip("(")
    for ct in cited_tags:
        author_in_ct = ct.split(",")[0].strip().lstrip("(")
        if author_in_tag == author_in_ct:
            return True
    return False
```

**设计说明：**
- 先精确匹配 `format_cite_tag()` 输出与正则提取的引用标注
- 精确不匹配时，比较作者部分（去掉年份差异）
- 这是为了处理 LLM 可能产生 `(Smith等, 2023)` vs `(Smith, 2023)` 等微小差异

- [ ] **Step 3: 验证无语法错误**

Run: `python -c "from backend.routers.compare import extract_cited_tags, _cite_tag_match; print('OK')"`
Expected: OK

- [ ] **Step 4: 快速单元测试验证正则**

Run:
```powershell
python -c "
from backend.routers.compare import extract_cited_tags
text = '张三等(2024)指出，而(Smith & Jones, 2023)认为不同。另有(Wang, 2020, 转引自 张三等, 2024)和(佚名, 年份不详)。'
tags = extract_cited_tags(text)
print(tags)
assert '(Smith & Jones, 2023)' in tags, f'Missing: {tags}'
assert '(Wang, 2020)' in tags, f'Missing: {tags}'
assert '(张三等, 2024)' in tags, f'Missing: {tags}'
assert '(佚名, 年份不详)' in tags, f'Missing: {tags}'
print('All assertions passed')
"
```
Expected: `All assertions passed`

- [ ] **Step 5: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): add extract_cited_tags for scanning citations in synthesis body"
```

---

### Task 4: 修改 `build_gbt7714_references` — 接收已引用集合，过滤二次引用

**Files:**
- Modify: `backend/routers/compare.py` (line 552-637)

**目标：** `build_gbt7714_references` 新增 `cited_tags` 参数，二次引用目录只保留被 `cited_tags` 匹配的条目。

- [ ] **Step 1: 修改 `build_gbt7714_references` 函数签名和二次引用过滤逻辑**

将 `build_gbt7714_references` 函数整体替换为：

```python
def build_gbt7714_references(
    papers: list[dict],
    bib_refs: dict[str, list[dict]],
    members: list[BibEntry],
    cited_tags: set[str] | None = None,
) -> str:
    refs = []
    ref_num = 1

    for paper in papers:
        authors = paper.get('authors', [])
        year = _safe_year(paper.get('year'))
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
    lines.append("### 主要参考文献")
    lines.append("")
    for _, entry in refs:
        lines.append(entry)

    secondary_items = []
    seen_secondary = set()
    for i, member in enumerate(members):
        paper = papers[i] if i < len(papers) else {}
        authors_p = paper.get('authors', [])
        year_p = _safe_year(paper.get('year'))
        cite_p = format_cite_tag(authors_p, year_p)

        for ref in bib_refs.get(member.id, []):
            ref_authors = ref.get('authors', [])
            ref_year = _safe_year(ref.get('year'))
            ref_cite = format_cite_tag(ref_authors, ref_year)
            dedup_key = f"{ref_cite}_{ref.get('title', '')}"
            if dedup_key in seen_secondary:
                continue
            primary_cites = {format_cite_tag(p.get('authors', []), _safe_year(p.get('year'))) for p in papers}
            if ref_cite in primary_cites:
                continue

            if cited_tags is not None and not _cite_tag_match(ref_cite, cited_tags):
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

**关键变更：**
1. 新增 `cited_tags: set[str] | None = None` 参数
2. 在二次引用循环中新增过滤：`if cited_tags is not None and not _cite_tag_match(ref_cite, cited_tags): continue`
3. 当 `cited_tags` 为 `None` 时（向后兼容），保留所有二次引用（旧行为）
4. 所有 `_safe_year()` 替换已在 Task 2 完成

- [ ] **Step 2: 验证无语法错误**

Run: `python -c "from backend.routers.compare import build_gbt7714_references; print('OK')"`
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): add cited_tags filter to build_gbt7714_references"
```

---

### Task 5: 修改两个综述端点 — 拼接全文后提取引用标注再生成参考文献

**Files:**
- Modify: `backend/routers/compare.py` (`synthesize_dimensions` 约line 1145-1151, `synthesize_long_dimensions` 对应位置)

**目标：** 在所有维度综述文本拼接完成后、调用 `build_gbt7714_references` 之前，先扫描全文提取引用标注集合，然后传入 `cited_tags` 过滤二次引用。

- [ ] **Step 1: 修改 `synthesize_dimensions` 端点**

找到以下代码段（约 line 1145-1151）：

```python
        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        references = build_gbt7714_references(paper_data, bib_refs, members)
        final_text = synthesis_body + "\n\n" + references
```

替换为：

```python
        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        cited_tags = extract_cited_tags(synthesis_body)
        references = build_gbt7714_references(paper_data, bib_refs, members, cited_tags)
        final_text = synthesis_body + "\n\n" + references
```

**变更：** 新增 `cited_tags = extract_cited_tags(synthesis_body)` 一行，并将 `cited_tags` 传入 `build_gbt7714_references`。

- [ ] **Step 2: 修改 `synthesize_long_dimensions` 端点**

在 `synthesize_long_dimensions` 中找到类似的拼接+生成参考文献代码段：

```python
        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        references = build_gbt7714_references(paper_data, bib_refs, members)
        final_text = synthesis_body + "\n\n" + references
```

替换为：

```python
        section_parts = []
        for sec in dimension_sections:
            section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
        synthesis_body = "\n\n".join(section_parts)

        cited_tags = extract_cited_tags(synthesis_body)
        references = build_gbt7714_references(paper_data, bib_refs, members, cited_tags)
        final_text = synthesis_body + "\n\n" + references
```

- [ ] **Step 3: 验证路由注册**

Run: `python -c "from backend.routers.compare import router; paths = [r.path for r in router.routes]; print(paths); assert '/synthesis' in paths; assert '/synthesis_long' in paths; print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add backend/routers/compare.py
git commit -m "feat(synthesis): filter secondary references by actual citations in synthesis body"
```

---

### Task 6: 同步修复旧对比端点中的 `None` 年份问题

**Files:**
- Modify: `backend/routers/compare.py` (`build_reference_list` 函数，约 line 690)

**问题：** `build_reference_list`（用于旧对比端点 `/analyze` 和 `/analyze_long`）同样存在 `year=None` 穿透问题。虽然 P2.5 主要关注 AI 综述，但同文件的旧对比也应修复。

- [ ] **Step 1: 检查 `build_reference_list` 的 year 取值**

确认 line 698 附近是否已改为 `_safe_year(paper.get('year'))`（Task 2 Step 5 应已修复）。如未修复，执行替换。

- [ ] **Step 2: 检查旧对比端点中所有 `format_inline_citation` 和 `format_cite_tag` 调用**

搜索 `compare.py` 中所有 `format_inline_citation` 和 `format_cite_tag` 的调用点，确认 year 参数均已通过 `_safe_year()` 处理。

Run: `python -c "import re; text = open('backend/routers/compare.py', encoding='utf-8').read(); matches = re.findall(r'.*?(format_cite_tag|format_inline_citation).*', text); [print(m.strip()) for m in matches]"`
Expected: 所有调用点的 year 参数均已通过 `_safe_year()` 或直接传入非 None 值

- [ ] **Step 3: Commit (如有改动)**

```bash
git add backend/routers/compare.py
git commit -m "fix(compare): ensure year None fallback in legacy compare endpoints"
```

---

### Task 7: 端到端验证

- [ ] **Step 1: 验证路由注册完整**

Run: `python -c "from backend.routers.compare import router; [print(r.path, r.methods) for r in router.routes]"`
Expected: 所有路由正常列出，无报错

- [ ] **Step 2: 验证 `extract_cited_tags` 对真实综述文本的匹配**

Run:
```powershell
python -c "
from backend.routers.compare import extract_cited_tags, _cite_tag_match, format_cite_tag

# Simulate a synthesis body
body = '''## 研究问题

在现有研究中，(张三等, 2024) 指出生态环境治理面临多重挑战。(Smith & Jones, 2023) 则从制度视角分析了不同路径。值得注意的是，(Wang, 2020, 转引自 张三等, 2024) 提出了最早的框架。

## 研究方法

(张三等, 2024) 采用了混合方法，而 (Smith & Jones, 2023) 使用了量化分析。
'''

tags = extract_cited_tags(body)
print('Extracted tags:', tags)
assert '(张三等, 2024)' in tags
assert '(Smith & Jones, 2023)' in tags
assert '(Wang, 2020)' in tags

# Test _cite_tag_match
assert _cite_tag_match(format_cite_tag(['张三', '李四'], '2024'), tags)
assert _cite_tag_match(format_cite_tag(['Smith', 'Jones'], '2023'), tags)
assert _cite_tag_match(format_cite_tag(['Wang'], '2020'), tags)
assert not _cite_tag_match(format_cite_tag(['Unknown'], '2025'), tags)
print('All assertions passed')
"
```
Expected: `All assertions passed`

- [ ] **Step 3: 验证 `build_gbt7714_references` 过滤效果**

Run:
```powershell
python -c "
from backend.routers.compare import build_gbt7714_references, extract_cited_tags

# Simulate synthesis body that only cites Wang (2020) as secondary
body = '根据(Wang, 2020)的研究，可以得出结论。'
cited_tags = extract_cited_tags(body)

papers = [{'authors': ['张三'], 'year': '2024', 'title': '测试论文', 'journal': '测试期刊'}]
bib_refs = {'m1': [
    {'authors': ['Wang'], 'year': '2020', 'title': 'Wang Paper', 'journal': 'Some Journal'},
    {'authors': ['Li'], 'year': '2019', 'title': 'Li Paper', 'journal': 'Other Journal'},
    {'authors': ['Zhao'], 'year': '2018', 'title': 'Zhao Paper', 'journal': 'Third Journal'},
]}

class FakeMember:
    id = 'm1'

result_with_filter = build_gbt7714_references(papers, bib_refs, [FakeMember()], cited_tags)
print('=== With filter ===')
print(result_with_filter)
print()

result_without_filter = build_gbt7714_references(papers, bib_refs, [FakeMember()], None)
print('=== Without filter ===')
print(result_without_filter)

# With filter: only Wang should appear in secondary
assert 'Wang Paper' in result_with_filter
assert 'Li Paper' not in result_with_filter, 'Li should be filtered out'
assert 'Zhao Paper' not in result_with_filter, 'Zhao should be filtered out'

# Without filter: all should appear
assert 'Li Paper' in result_without_filter
assert 'Zhao Paper' in result_without_filter

print('All assertions passed')
"
```
Expected: `All assertions passed`

- [ ] **Step 4: 启动后端验证完整流程**

Run: `uvicorn backend.main:app --reload --port 8000`

在浏览器中测试 AI 综述功能，确认：
1. 参考文献目录中二次引用只包含正文实际引用的条目
2. 不再出现 `(佚名, None)` 或 `n.d.` 等不规范格式
3. 旧对比功能（/analyze、/analyze_long）不受影响

- [ ] **Step 5: Final commit (如有修复)**

```bash
git add -A
git commit -m "fix(synthesis): final adjustments after e2e testing"
```

---

## 自检清单

### 1. 规格覆盖

| PENDING_PLANS 中的问题 | 对应 Task |
|---|---|
| P2.5 二次引用目录过滤（只保留正文实际引用过的文献） | Task 3 + Task 4 + Task 5 |
| P2 bug #1: None 年份穿透（`佚名 (None). 标题...`） | Task 1 + Task 2 |
| P2 bug #2: 行内引用 None 年份（`(佚名, None)`） | Task 1 |
| P2 bug #3: 中英文不一致（`n.d.` 英文 vs 中文系统） | Task 1 |

### 2. 占位符扫描

无 TBD/TODO/待补充/稍后处理等占位符。

### 3. 类型一致性

- `_safe_year()` 返回 `str`，所有 year 参数统一经此函数处理
- `extract_cited_tags()` 返回 `set[str]`
- `build_gbt7714_references()` 新增 `cited_tags: set[str] | None = None`，向后兼容
- `_cite_tag_match(cite_tag: str, cited_tags: set[str]) -> bool`
- `format_cite_tag()` 签名不变，返回 `str`
