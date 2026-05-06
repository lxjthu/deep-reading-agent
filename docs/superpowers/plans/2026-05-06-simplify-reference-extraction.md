# 参考文献提取简化重构：去除过度过滤，让 DeepSeek 主导识别

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `deepseek_refs.py` 中过度激进的程序化预过滤替换为最小化清理 + DeepSeek 全权识别，使作者-年份制、无编号、单栏/双栏等各类参考文献格式都能被正确提取。

**Architecture:** 程序只负责：(1) 定位"参考文献"标题位置 (2) 截取标题之后的原始文本 (3) 做最少的噪音清理（页眉、页码、英文摘要起点）。所有条目识别、断行合并、噪音排除交给 DeepSeek。删除 `_looks_like_ref_entry()`、`_looks_like_table_data()`、`_NON_REF_PATTERNS` 等过滤函数。

**Tech Stack:** Python, pdfplumber, DeepSeek v4-flash (via OpenAI SDK), json_repair

---

## 问题根因（实测确认）

| 问题 | 详情 |
|------|------|
| `_looks_like_ref_entry()` 只匹配 `(N)` 编号 | 作者-年份制论文 0 命中，导致候选文本全部被短行过滤丢弃 |
| `_is_two_column()` 误判单栏为双栏 | x0 分布阈值对单栏 PDF 误判，触发 `use_text_flow=True` 进一步打乱顺序 |
| 多层过滤（短行<15、表格数据、NON_REF）过于激进 | 年份、期号等关键短行被丢弃，条目信息断裂 |
| `PROMPT_EXTRACT` 偏向合辑 PDF 场景 | 对单篇论文做了不必要的"编号连续性"判断 |
| **实测对比**：现有管线提取 0 条 vs 直接丢 DeepSeek 提取 46/47 条 | |

## 修改范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/services/deepseek_refs.py` | **重写** | 核心修改：简化 `extract_candidate_text()`，删除过滤函数，更新 prompt |
| `backend/tests/test_references.py` | **不改动** | 该测试 mock 了 `run_reference_trace_task`，不涉及底层提取逻辑 |
| `test_deepseek_references.py` | **不改动** | 这是独立验证脚本，不影响后端功能 |

**不改动** `backend/routers/references.py` 和 `backend/routers/reading.py`——它们通过 `extract_references_deepseek()` 和 `trace_citations_deepseek()` 的公共 API 调用，接口签名不变。

---

### Task 1: 删除不再需要的过滤函数和常量

**Files:**
- Modify: `backend/services/deepseek_refs.py`

- [ ] **Step 1: 删除 `_looks_like_ref_entry` 函数**

删除 `deepseek_refs.py` 第 144-145 行：

```python
# 删除以下函数
def _looks_like_ref_entry(line: str) -> bool:
    return bool(re.match(r"^[（(\［[]\s*\d+\s*[）)\］]]", line.strip()))
```

- [ ] **Step 2: 删除 `_looks_like_table_data` 函数**

删除 `deepseek_refs.py` 第 148-158 行的整个 `_looks_like_table_data` 函数。

- [ ] **Step 3: 删除 `_NON_REF_PATTERNS` 列表**

删除 `deepseek_refs.py` 第 161-168 行的 `_NON_REF_PATTERNS` 列表。

- [ ] **Step 4: 删除 `_is_two_column` 函数**

删除 `deepseek_refs.py` 第 171-187 行的 `_is_two_column` 函数。

- [ ] **Step 5: 删除 `_extract_page_text` 函数**

删除 `deepseek_refs.py` 第 190-194 行的 `_extract_page_text` 函数。

- [ ] **Step 6: 运行语法检查**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`（此时文件会有未使用的导入 `pdfplumber`，但不会有语法错误）

---

### Task 2: 重写 `extract_candidate_text()` —— 最小化清理

**Files:**
- Modify: `backend/services/deepseek_refs.py`

新逻辑：
1. 用 pdfplumber 逐页提取文本（**不用** `use_text_flow`，不用 `_is_two_column`）
2. 找到"参考文献"标题后，截取标题之后所有页面的原始文本
3. 只做最少噪音清理：去掉页眉（`XXXX 年第 X 期`）、纯分隔线（`—`）、文章标题头（包含"温军等：韧性视角"这类页眉）、页码
4. 遇到英文摘要 `Summary` / `Abstract` 开头的独立段时停止截取（参考文献不会出现在英文摘要之后，除非是跨摘要续页，这种也由 DeepSeek 判断）
5. **不做**短行过滤、不做条目编号检测、不做表格数据过滤

- [ ] **Step 1: 重写 `extract_candidate_text` 函数**

替换 `deepseek_refs.py` 中 `extract_candidate_text` 函数（原第 197-255 行）为：

```python
_NOISE_LINE_PATTERNS = [
    re.compile(r"^\d{4}\s*年第\s*\d+\s*期"),
    re.compile(r"^—+$"),
]

_ARTICLE_HEADER_RE = re.compile(r"^.{2,10}[等：:].{5,30}$")


def _is_noise_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    for pat in _NOISE_LINE_PATTERNS:
        if pat.match(s):
            return True
    if re.fullmatch(r"\d{1,5}", s):
        return True
    return False


def extract_candidate_text(pdf_path: str) -> str:
    page_sections: list[str] = []
    found_heading = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            lines = text.splitlines()

            page_lines: list[str] = []
            for line in lines:
                s = _normalize_ws(line)
                if not s:
                    continue

                if not found_heading:
                    if _is_ref_heading(s):
                        found_heading = True
                    continue

                if s.lower().startswith("summary") and len(s) < 100:
                    continue

                cleaned = CONTINUATION_RE.sub("", s).strip()
                if not cleaned:
                    continue
                if _is_ref_heading(cleaned):
                    continue

                if not _is_noise_line(cleaned):
                    page_lines.append(cleaned)

            if page_lines and found_heading:
                page_sections.append("\n".join(page_lines))

    return "\n\n--- PAGE BREAK ---\n\n".join(page_sections)
```

- [ ] **Step 2: 运行语法检查**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

---

### Task 3: 更新 `PROMPT_EXTRACT` —— 通用化，不再偏向合辑 PDF

**Files:**
- Modify: `backend/services/deepseek_refs.py`

当前 prompt 开头就是"你看到的文本来自一本中文学术期刊的合辑 PDF"，对单篇论文不适用。新 prompt 应覆盖：编号制、作者-年份制、中英文混排、各种断行情况。让 DeepSeek 自己判断。

- [ ] **Step 1: 替换 `PROMPT_EXTRACT`**

替换 `deepseek_refs.py` 中 `PROMPT_EXTRACT` 常量（原第 39-89 行）为：

```python
PROMPT_EXTRACT = """你是一个学术文献参考文献解析专家。

## 输入
你看到的是一篇学术论文 PDF 尾部提取的原始文本。由于 PDF 文本提取的限制，文本中可能存在以下问题：
- 每条参考文献可能被拆成多行（断行）
- 页眉、页码、分隔线等噪音
- 多个 PAGE BREAK 分隔不同页面的内容

## 参考文献可能使用的格式
- **编号制**：（1）、[1]、［1］、1. 等
- **作者-年份制**：作者，年份：《标题》，《期刊》第 X 期。或 Author, Year, "Title", Journal, Vol(Issue): Pages.
- **GB/T 7714 格式**：作者. 标题 [J]. 期刊, 年, 卷(期): 页码.
- 中英文参考文献混排

## 特殊情况
- 合辑 PDF 可能包含多篇论文的参考文献，此时只提取编号最连续、数量最多的那组
- 续页标记"下转第 X 页"/"上接第 X 页"应忽略，继续提取后续条目
- 英文摘要（Summary/Abstract）之后的参考文献仍然需要提取

## 任务
1. 将多行合并为完整的参考文献条目
2. 提取每条参考文献的结构化字段
3. 忽略非参考文献内容（摘要、附录、致谢、作者简介、补充材料、注释、页眉、页码等）

## 输出格式
严格 JSON：
```json
{
  "references": [
    {
      "reference_order": 1,
      "raw_text": "完整原文（合并断行后）",
      "authors": ["作者1", "作者2"],
      "year": 2020,
      "title": "论文标题",
      "journal": "期刊名",
      "volume": null,
      "issue": "期号",
      "pages": "页码范围",
      "doi": null,
      "language": "zh",
      "ignore": false,
      "ignore_reason": null
    }
  ]
}
```

## 约束
- `ignore=true` 时必须给出 `ignore_reason`（用于标记非参考文献内容）
- 不确定字段填 null，不得编造
- 保留完整 `raw_text`
- 必须提取所有参考文献条目，不要遗漏
- 程序侧会对 `ignore=false` 的条目重新编号"""
```

- [ ] **Step 2: 运行语法检查**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

---

### Task 4: 简化 `extract_references_deepseek()` 的 fallback 逻辑

**Files:**
- Modify: `backend/services/deepseek_refs.py`

当前 fallback 用了 `_is_two_column` 和 `_extract_page_text`（已删除）。需要简化。

- [ ] **Step 1: 替换 `extract_references_deepseek` 中的 fallback 逻辑**

将 `extract_references_deepseek` 函数（原第 351-412 行）中 fallback 部分从：

```python
with pdfplumber.open(pdf_path) as pdf:
    n = len(pdf.pages)
    start = max(0, n - 5)
    tail_pages = []
    for i in range(start, n):
        page = pdf.pages[i]
        chars = page.chars or []
        use_flow = _is_two_column(chars)
        text = _extract_page_text(page, force_text_flow=use_flow)
        tail_pages.append(text)
candidate_text = "\n\n".join(tail_pages)
```

替换为：

```python
with pdfplumber.open(pdf_path) as pdf:
    n = len(pdf.pages)
    start = max(0, n - 5)
    tail_pages = []
    for i in range(start, n):
        text = pdf.pages[i].extract_text() or ""
        tail_pages.append(text)
candidate_text = "\n\n".join(tail_pages)
```

- [ ] **Step 2: 同时简化 user_content 构造**

将 `extract_references_deepseek` 中的 user_content 从：

```python
"## 候选参考文献文本（共 {n_lines} 行）\n\n"
"注意：文本中有多个 SECTION BREAK 分隔不同的区域。"
"请仔细扫描全文，包括续页后的内容。\n\n"
```

替换为：

```python
"## 候选参考文献文本（共 {n_lines} 行）\n\n"
"文本中 PAGE BREAK 分隔不同页面。请合并断行，提取所有参考文献。\n\n"
```

- [ ] **Step 3: 运行语法检查**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

---

### Task 5: 简化 `extract_body_text()` —— 去除 `_is_two_column` 调用

**Files:**
- Modify: `backend/services/deepseek_refs.py`

`extract_body_text` 中 3 处调用了已删除的 `_is_two_column` 和 `_extract_page_text`。需要改为直接用 `page.extract_text()`。

- [ ] **Step 1: 替换 `extract_body_text` 函数**

替换整个 `extract_body_text` 函数（原第 258-316 行）为：

```python
def extract_body_text(pdf_path: str) -> tuple[list[dict], str]:
    body_parts: list[str] = []
    ref_lines: list[str] = []
    in_ref = False

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.splitlines():
                s = _normalize_ws(line)
                if not s:
                    continue
                if not in_ref:
                    if _is_ref_heading(s):
                        in_ref = True
                        continue
                    body_parts.append(s)
                else:
                    if _is_ref_heading(s):
                        continue
                    cleaned = CONTINUATION_RE.sub("", s).strip()
                    if cleaned:
                        ref_lines.append(cleaned)

    body_text = "\n".join(body_parts)
    ref_text = "\n".join(ref_lines)

    paragraphs = []
    pid = 0

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            blocks = re.split(r"\n\s*\n", text)
            if len(blocks) == 1:
                blocks = text.splitlines()
            for block in blocks:
                lines = [_normalize_ws(l) for l in block.splitlines() if _normalize_ws(l)]
                if not lines:
                    continue
                joined = " ".join(lines)
                if len(joined) < 30:
                    continue
                if any(_is_ref_heading(l) for l in lines):
                    break
                pid += 1
                paragraphs.append({
                    "id": pid,
                    "page_label": f"第{page_num}页",
                    "paragraph_label": f"P{page_num}-{pid}",
                    "text": joined,
                })

    return paragraphs, ref_text
```

- [ ] **Step 2: 简化 `trace_citations_deepseek` 中的正文提取**

替换 `trace_citations_deepseek` 函数（原第 415-499 行）中正文提取部分（第 426-445 行）：

```python
body_text_parts: list[str] = []
in_ref = False
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        chars = page.chars or []
        use_flow = _is_two_column(chars)
        text = _extract_page_text(page, force_text_flow=use_flow)
        for line in text.splitlines():
            s = _normalize_ws(line)
            if not s:
                continue
            if not in_ref:
                if _is_ref_heading(s):
                    in_ref = True
                    continue
                body_text_parts.append(s)
            else:
                if _is_ref_heading(s):
                    continue
body_text = "\n".join(body_text_parts)
```

替换为：

```python
body_text_parts: list[str] = []
in_ref = False
with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            s = _normalize_ws(line)
            if not s:
                continue
            if not in_ref:
                if _is_ref_heading(s):
                    in_ref = True
                    continue
                body_text_parts.append(s)
            else:
                if _is_ref_heading(s):
                    continue
body_text = "\n".join(body_text_parts)
```

- [ ] **Step 3: 运行语法检查**

Run: `python -c "import ast; ast.parse(open('backend/services/deepseek_refs.py', encoding='utf-8').read()); print('OK')"`
Expected: `OK`

---

### Task 6: 验证现有测试通过

**Files:**
- Test: `backend/tests/test_references.py`

- [ ] **Step 1: 运行现有 references 路由测试**

Run: `python -m pytest backend/tests/test_references.py -v`
Expected: 所有测试 PASS（该测试 mock 了底层提取，不依赖实际的 PDF 提取逻辑）

- [ ] **Step 2: 确认 `deepseek_refs.py` 可正常导入**

Run: `python -c "from backend.services.deepseek_refs import extract_references_deepseek, trace_citations_deepseek, call_deepseek_json; print('Import OK')"`
Expected: `Import OK`

---

### Task 7: 用目标 PDF 做端到端验证

**Files:**
- Modify: `C:\Users\langx\AppData\Local\Temp\opencode\test_direct.py`（已有验证脚本）

此 Task 需要 `DEEPSEEK_API_KEY` 环境变量。

- [ ] **Step 1: 用新管线测试目标 PDF**

Run（在项目根目录）：
```powershell
.\venv\Scripts\Activate.ps1
python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from backend.services.deepseek_refs import extract_references_deepseek
refs = extract_references_deepseek(r'C:\Users\langx\Desktop\韧性视角下企业数字化转型与股票市场稳定性_温军.pdf')
print('Total refs:', len(refs))
for r in refs:
    authors = ', '.join((r.get('authors') or [])[:2])
    print('[{:>2}] {:30s} ({:>4}) {}'.format(
        r['reference_order'], authors[:30], r.get('year', '?'), (r.get('title') or '')[:50]))
"
```

Expected:
- 提取 >= 40 条参考文献（实际约 47 条）
- 中文参考文献 ~31 条，英文参考文献 ~15 条
- 每条都有 title、authors、year

- [ ] **Step 2: 回归测试其他已有验证 PDF**

如果桌面上有其他已验证过的 PDF（如 `人工智能如何提升企业生产效率？——基于劳动力技能结构调整的视角_姚加权.pdf`），也运行一次确认不退化：

```powershell
python -c "
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from backend.services.deepseek_refs import extract_references_deepseek
refs = extract_references_deepseek(r'C:\Users\langx\Desktop\人工智能如何提升企业生产效率？——基于劳动力技能结构调整的视角_姚加权.pdf')
print('Total refs:', len(refs))
"
```

Expected: 提取数量 >= 之前验证的 52 条

- [ ] **Step 3: Commit**

```bash
git add backend/services/deepseek_refs.py
git commit -m "refactor: simplify reference extraction - remove over-filtering, let DeepSeek handle identification

- Remove _looks_like_ref_entry, _looks_like_table_data, _NON_REF_PATTERNS
- Remove _is_two_column (caused false positives on single-column PDFs)
- Simplify extract_candidate_text to minimal noise cleanup only
- Update PROMPT_EXTRACT to handle all reference formats (numbered, author-year, GB/T 7714)
- Simplify extract_body_text and trace_citations_deepseek (no use_text_flow)
- Verified: 46/47 refs extracted from author-year format PDF (was 0 before)"
```

---

## 文件最终状态预览

### `backend/services/deepseek_refs.py` 最终结构

```
第 1-27 行:   导入 + 常量 (MODEL, BASE_URL, MAX_RETRIES, ...)
第 28-37 行:   CONTINUATION_RE, REFERENCE_HEADINGS
第 38-100 行:  PROMPT_EXTRACT (新通用化版本)
第 101-128 行: PROMPT_CITE (不变)
第 129-142 行: _normalize_ws, _is_ref_heading (不变)
第 143-155 行: _NOISE_LINE_PATTERNS, _is_noise_line (新增，极简)
第 156-190 行: extract_candidate_text (简化版)
第 191-240 行: extract_body_text (简化版)
第 241-270 行: call_deepseek_json (不变)
第 271-330 行: extract_references_deepseek (简化 fallback)
第 331-410 行: trace_citations_deepseek (简化正文提取)
第 411-420 行: _locate_paragraph, _expand_excerpt (不变)
```

### 删除的函数/常量

| 名称 | 原行号 | 原因 |
|------|--------|------|
| `_looks_like_ref_entry()` | 144-145 | 只匹配编号格式，作者-年份制 0 命中 |
| `_looks_like_table_data()` | 148-158 | 过滤过激，由 DeepSeek 判断 |
| `_NON_REF_PATTERNS` | 161-168 | 过滤过激，由 DeepSeek 判断 |
| `_is_two_column()` | 171-187 | 误判单栏为双栏，且 `use_text_flow` 对参考文献提取无益 |
| `_extract_page_text()` | 190-194 | 只是 `_is_two_column` 的包装，已无调用者 |

### 不变的部分

| 名称 | 说明 |
|------|------|
| `_is_ref_heading()` | 标题检测逻辑通用且有效 |
| `_normalize_ws()` | 通用工具函数 |
| `call_deepseek_json()` | API 调用层，稳定 |
| `PROMPT_CITE` | 引用追踪 prompt，稳定 |
| `_locate_paragraph()` | 段落定位，稳定 |
| `_expand_excerpt()` | 摘录扩展，稳定 |
| `extract_references_deepseek()` 返回格式 | list[dict]，字段不变 |
| `trace_citations_deepseek()` 返回格式 | list[dict]，字段不变 |
| 所有调用方 (`reading.py`, `references.py`) | 接口签名不变 |
