#!/usr/bin/env python3
"""
Translation Pipeline - 经济学论文中文重述模块

Flow:
  PDF / MD
    → [Step 1] extract_front_sections()   # 提取标题/摘要/引言
    → [Step 2] generate_glossary()        # 第一套提示词 → 术语词典
    → [Step 3] chunk_md_by_headers()      # 按 ## 标题切块
    → [Step 4] restate_chunk() × N       # 第二套提示词 × 每块
    → [Step 5] 合并 + 注入 YAML 字段 → 输出 _cn.md + _glossary.md
"""

import os
import re
import time
import logging
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
TRANSLATION_OUT_DIR = os.path.join(os.getcwd(), "translation_results")

MAX_RETRIES = 2
TIMEOUT = 120  # seconds per API call

# Extraction suffixes to strip when deriving stem
_EXTRACTION_SUFFIXES = ("_paddleocr", "_raw", "_segmented")


def _get_client() -> OpenAI:
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

GLOSSARY_SYSTEM = (
    "你是一位专业的经济学文献专家，深厚掌握计量经济学、发展经济学、劳动经济学等领域的中英文学术规范，"
    "熟悉国内主流经济学期刊（《经济研究》《经济学（季刊）》等）的术语译法惯例。"
)

GLOSSARY_USER_TMPL = """\
以下是一篇经济学论文的标题、摘要和引言部分。请仔细阅读后，提取其中所有具有专业性的术语、方法名称、变量名、模型名及重要概念，为本文构建一份**中英文术语对照词典**。

输出要求：
1. 以 Markdown 表格呈现，列为：英文原词 | 中文表达 | 简要说明（限20字以内）
2. 优先采用中国经济学界主流期刊的通行译法；若存在多种译法，选最常见者并在说明栏注明备选
3. 计量方法、统计模型务必收录（如 DID、IV、RDD、FE、GMM 等）
4. 数据集名称、政策名称、地理区域等专有名词一律纳入
5. 按类别分组排列：① 核心概念  ② 计量方法与模型  ③ 变量与指标  ④ 数据与政策专有名词
6. 表格之后，用1-2句话概括本文的核心研究问题，供后续重述参考

论文信息如下：

【标题】
{title}

【摘要】
{abstract}

【引言】
{introduction}
"""

RESTATE_SYSTEM = (
    "你是一位资深经济学文献专家，精通计量经济学、发展经济学及中英文经济学学术写作规范，"
    "熟悉《经济研究》《管理世界》等中文顶刊的表达惯例。"
)

RESTATE_USER_TMPL = """\
以下是一篇经济学论文的一个文本块，请依据提供的术语词典，用规范的中文经济学学术语言对其进行完整重述。

**重述规范：**
1. **内容完整**：原文所有信息——数值、系数、置信区间、样本量、回归结果、政策背景——均须完整体现，不得遗漏或简化
2. **术语统一**：严格遵循下方词典的对照表；词典未收录的术语，首次出现时以括号标注英文原词，如"稳健性检验（robustness check）"
3. **格式保留**：严格保留 Markdown 结构，包括标题层级（#/##/###）、列表、表格、公式块（$$...$$）、代码块；YAML frontmatter 中 key 保持英文，描述性 value 改为中文
4. **数字与公式**：所有数字、百分比、统计量（t值、p值、F统计量、R²等）原样保留，不得改动
5. **经济学表达**：行文符合中文经济学期刊规范——因果推断用"识别策略"而非"研究方法"，系数显著性按"在1%水平上显著"表述，"robust"对应"稳健"

**术语词典：**
{glossary}

**输出要求：**
直接输出重述后的 Markdown 内容，不要任何开场白、说明性文字或结语（例如"好的""以下是""我将"等均不得出现）。

**待重述的文本块：**
{chunk}
"""

# ---------------------------------------------------------------------------
# Step 1: Extract front sections (title / abstract / introduction)
# ---------------------------------------------------------------------------

_YAML_RE = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL)

# Header that marks the start of the references/bibliography section.
# Text after this point is NOT sent for supplementary restatement.
_REFERENCES_HEADER_RE = re.compile(
    r'^#+\s*(references|参考文献|bibliography|works\s+cited)\s*$',
    re.IGNORECASE | re.MULTILINE,
)

_ABSTRACT_HEADER_RE = re.compile(
    r'^#{1,3}\s*(abstract|摘\s*要|summary)\s*$',
    re.IGNORECASE | re.MULTILINE,
)
_INTRO_HEADER_RE = re.compile(
    r'^#{1,3}\s*'
    r'(introduction|引\s*言|一\s*[、．.]\s*引\s*言'
    r'|1\s*[\.．]\s*introduction|i\s*\.\s*introduction)\s*$',
    re.IGNORECASE | re.MULTILINE,
)


def _yaml_title(yaml_block: str) -> str:
    m = re.search(r'^title\s*:\s*(.+)$', yaml_block, re.MULTILINE | re.IGNORECASE)
    return m.group(1).strip().strip('"\'') if m else ""


def _section_text(body: str, header_match: re.Match, max_chars: int) -> str:
    """Return the body text following a header, up to the next same-or-higher-level header."""
    level = len(re.match(r'#+', header_match.group(0)).group())
    start = header_match.end()
    nxt = re.search(r'^#{1,' + str(level) + r'}\s+', body[start:], re.MULTILINE)
    end = start + nxt.start() if nxt else len(body)
    return body[start:end].strip()[:max_chars]


def extract_front_sections(md_text: str) -> Dict[str, str]:
    """
    Extract title, abstract, introduction from raw MD text.
    Returns dict: {yaml, title, abstract, introduction}.
    """
    result = {"yaml": "", "title": "", "abstract": "", "introduction": ""}

    yaml_m = _YAML_RE.match(md_text)
    body = md_text
    if yaml_m:
        result["yaml"] = yaml_m.group(1)
        body = md_text[yaml_m.end():]
        result["title"] = _yaml_title(result["yaml"])

    if not result["title"]:
        m = re.search(r'^#\s+(.+)$', body, re.MULTILINE)
        if m:
            result["title"] = m.group(1).strip()

    abs_m = _ABSTRACT_HEADER_RE.search(body)
    if abs_m:
        result["abstract"] = _section_text(body, abs_m, 3000)
    else:
        m = re.search(r'\bAbstract\b[:\s]', body, re.IGNORECASE)
        if m:
            result["abstract"] = body[m.start(): m.start() + 2000].strip()

    intro_m = _INTRO_HEADER_RE.search(body)
    if intro_m:
        result["introduction"] = _section_text(body, intro_m, 5000)

    return result


# ---------------------------------------------------------------------------
# Step 2: Generate terminology glossary
# ---------------------------------------------------------------------------

def generate_glossary(
    sections: Dict[str, str],
    client: OpenAI,
    model: str = "deepseek-chat",
    log_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Call DeepSeek with the first prompt set.
    Returns the glossary as a Markdown table string.
    """
    title = sections.get("title") or "(unknown)"
    abstract = sections.get("abstract") or "(摘要未找到)"
    intro = sections.get("introduction") or "(引言未找到)"

    if not sections.get("abstract") and not sections.get("introduction"):
        _log(log_cb, "⚠ 未找到摘要和引言，词典生成可能不完整")

    user_msg = GLOSSARY_USER_TMPL.format(
        title=title, abstract=abstract, introduction=intro
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            _log(log_cb, f"  [词典] 调用 {model}（第 {attempt + 1} 次）...")
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": GLOSSARY_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                timeout=TIMEOUT,
            )
            glossary = resp.choices[0].message.content.strip()
            _log(log_cb, f"  [词典] 生成完成，共 {len(glossary)} 字符")
            return glossary
        except Exception as e:
            if attempt < MAX_RETRIES:
                _log(log_cb, f"  [词典] 第 {attempt + 1} 次失败：{e}，3 秒后重试...")
                time.sleep(3)
            else:
                _log(log_cb, f"  [词典] 生成失败：{e}")
                return f"（词典生成失败：{e}）"


# ---------------------------------------------------------------------------
# Step 3: Detect section header level (ask DeepSeek)
# ---------------------------------------------------------------------------

_DETECT_PROMPT = """\
以下是一篇论文 Markdown 文档的前几页内容。请判断论文**正文各主要章节**（如 Introduction、\
Literature Review、Data、Methodology、Results、Conclusion 等）所使用的 Markdown 标题层级。

注意：
- 论文总标题通常是 # 级，不要混淆
- 请判断的是**章节标题**的层级，即紧跟在论文标题之后、划分各大节的那一级标题

请只输出以下三种之一，不要任何解释：
###
##
#

文档内容：
{preview}
"""


def detect_section_level(
    md_text: str,
    client: OpenAI,
    model: str = "deepseek-chat",
    preview_chars: int = 4000,
    log_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Ask DeepSeek to identify which Markdown header level is used for main sections.
    Uses only the first ~3 pages (preview_chars) of the document.
    Returns one of: "#", "##", "###".
    Falls back to "##" on any error.
    """
    # Strip YAML frontmatter from preview so it doesn't confuse the model
    yaml_m = _YAML_RE.match(md_text)
    body = md_text[yaml_m.end():] if yaml_m else md_text
    preview = body[:preview_chars]

    prompt = _DETECT_PROMPT.format(preview=preview)

    try:
        _log(log_cb, f"  [分块] 询问 DeepSeek 章节标题层级...")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
            max_tokens=10,
        )
        answer = resp.choices[0].message.content.strip()
        # Match from most specific to least specific
        for level in ("###", "##", "#"):
            if level in answer:
                _log(log_cb, f"  [分块] 检测结果：章节标题层级 = {level}")
                return level
        _log(log_cb, f"  [分块] 无法解析回答「{answer}」，使用默认 ##")
        return "##"
    except Exception as e:
        _log(log_cb, f"  [分块] 检测失败：{e}，使用默认 ##")
        return "##"


# ---------------------------------------------------------------------------
# Step 4: Chunk MD text by detected header level
# ---------------------------------------------------------------------------

def chunk_md_by_headers(
    md_text: str,
    max_chars: int = 5000,
    split_level: Optional[str] = None,
) -> List[Tuple[str, str]]:
    """
    Split md_text into (label, text) chunks.

    split_level: the header level to split on, e.g. "##" or "###".
      If None, auto-detects by trying ## then # (no LLM call).
      Pass the result of detect_section_level() to use the LLM-confirmed level.

    - YAML frontmatter becomes chunk ("__yaml__", text).
    - Text before the first split-level header becomes chunk ("__preamble__", text).
    - Adjacent small sections are merged up to max_chars.
    - A section larger than max_chars is split on paragraph boundaries.
    """
    chunks: List[Tuple[str, str]] = []

    yaml_m = _YAML_RE.match(md_text)
    body = md_text
    if yaml_m:
        chunks.append(("__yaml__", md_text[: yaml_m.end()].rstrip()))
        body = md_text[yaml_m.end():]

    if split_level:
        # Use the LLM-confirmed level exactly; escape # for regex
        escaped = re.escape(split_level)
        split_re = re.compile(r'^' + escaped + r'[^#]', re.MULTILINE)
        positions = [m.start() for m in split_re.finditer(body)]
        if not positions:
            # Confirmed level produced no matches — fall back gracefully
            split_level = None

    if not split_level:
        # Auto-detect: try ## then #
        positions = []
        for pattern_str in (r'^##[^#]', r'^#[^#]'):
            split_re = re.compile(pattern_str, re.MULTILINE)
            positions = [m.start() for m in split_re.finditer(body)]
            if positions:
                break

    if not positions:
        # No headers at all — split by paragraphs
        chunks.extend(_split_by_paragraphs("__body__", body, max_chars))
        return chunks

    # Preamble before the first header
    preamble = body[: positions[0]].strip()
    if preamble:
        chunks.append(("__preamble__", preamble))

    positions.append(len(body))  # sentinel

    buf_label = ""
    buf_text = ""

    for i in range(len(positions) - 1):
        sec = body[positions[i]: positions[i + 1]]
        label = sec.split("\n", 1)[0].strip()

        if len(buf_text) + len(sec) <= max_chars:
            buf_text = (buf_text + "\n\n" + sec).lstrip() if buf_text else sec
            buf_label = buf_label or label
        else:
            if buf_text:
                chunks.append((buf_label, buf_text.strip()))
            if len(sec) > max_chars:
                # Section itself exceeds limit — split body.
                # Only the first sub-chunk gets the header line; subsequent parts
                # omit it to prevent the same heading from appearing repeatedly.
                header_line, body_part = (sec.split("\n", 1) + [""])[:2]
                sub_chunks = _split_by_paragraphs(
                    "", body_part, max_chars - len(header_line) - 1
                )
                for j, (_, sub) in enumerate(sub_chunks, 1):
                    if j == 1:
                        chunks.append((f"{label} (part {j})", header_line + "\n" + sub))
                    else:
                        chunks.append((f"{label} (part {j})", sub))
                buf_text = ""
                buf_label = ""
            else:
                buf_text = sec
                buf_label = label

    if buf_text:
        chunks.append((buf_label, buf_text.strip()))

    return chunks


def _split_by_paragraphs(
    base_label: str, text: str, max_chars: int
) -> List[Tuple[str, str]]:
    """Split text into chunks on blank lines, each chunk ≤ max_chars."""
    paragraphs = re.split(r"\n{2,}", text)
    chunks: List[Tuple[str, str]] = []
    buf = ""
    idx = 0
    for para in paragraphs:
        if len(buf) + len(para) + 2 <= max_chars:
            buf = (buf + "\n\n" + para).lstrip() if buf else para
        else:
            if buf:
                idx += 1
                chunks.append((f"{base_label}_p{idx}" if base_label else f"__part_{idx}__", buf.strip()))
            buf = para
    if buf:
        idx += 1
        chunks.append((f"{base_label}_p{idx}" if base_label else f"__part_{idx}__", buf.strip()))
    return chunks


# ---------------------------------------------------------------------------
# Step 4: Restate a single chunk
# ---------------------------------------------------------------------------

def restate_chunk(
    chunk_text: str,
    glossary: str,
    client: OpenAI,
    model: str = "deepseek-chat",
    log_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Call DeepSeek with the second prompt set.
    Returns the Chinese restatement of chunk_text.
    """
    user_msg = RESTATE_USER_TMPL.format(glossary=glossary, chunk=chunk_text)

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": RESTATE_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                timeout=TIMEOUT,
            )
            return _strip_preamble(resp.choices[0].message.content.strip())
        except Exception as e:
            if attempt < MAX_RETRIES:
                _log(log_cb, f"    重试 {attempt + 1}：{e}")
                time.sleep(3)
            else:
                _log(log_cb, f"    块重述失败：{e}")
                return f"<!-- 重述失败：{e} -->\n\n{chunk_text}"


# ---------------------------------------------------------------------------
# Step 5: Full pipeline — one MD file
# ---------------------------------------------------------------------------

def translate_md_file(
    md_path: str,
    out_dir: Optional[str] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    model: str = "deepseek-chat",
    max_chars: int = 5000,
    max_workers: int = 5,
) -> Tuple[str, str]:
    """
    Full restatement pipeline for one MD file.

    max_workers: number of parallel DeepSeek calls for chunk restatement (Step 5).
      1 = sequential; 5 = recommended default; 10 = max reasonable.

    Returns:
        (cn_md_path, glossary_path)
    """
    def log(msg: str):
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    def check():
        if cancel_check and cancel_check():
            raise InterruptedError("用户取消")

    # Derive clean stem
    stem = Path(md_path).stem
    for suf in _EXTRACTION_SUFFIXES:
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
            break

    if out_dir is None:
        out_dir = os.path.join(TRANSLATION_OUT_DIR, stem)
    os.makedirs(out_dir, exist_ok=True)

    cn_path = os.path.join(out_dir, f"{stem}_cn.md")
    glossary_path = os.path.join(out_dir, f"{stem}_glossary.md")

    log(f"[重述] 读取：{md_path}")
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
    log(f"[重述] 文本长度：{len(md_text):,} 字符")

    client = _get_client()

    # --- Step 1: Extract front sections ---
    log("[重述] Step 1/6  提取标题、摘要、引言...")
    sections = extract_front_sections(md_text)
    log(f"  标题：{sections['title'] or '(未找到)'}")
    log(f"  摘要：{len(sections['abstract']):,} 字符  "
        f"引言：{len(sections['introduction']):,} 字符")
    check()

    # --- Step 2: Generate glossary ---
    log("[重述] Step 2/6  生成术语词典...")
    glossary = generate_glossary(sections, client, model=model, log_cb=log)
    with open(glossary_path, "w", encoding="utf-8") as f:
        f.write(f"# 术语词典：{sections['title']}\n\n{glossary}\n")
    log(f"  词典已保存：{glossary_path}")
    check()

    # --- Step 3: Detect section header level ---
    log("[重述] Step 3/6  检测章节标题层级...")
    split_level = detect_section_level(md_text, client, model=model, log_cb=log)
    check()

    # --- Step 4: Chunk ---
    log(f"[重述] Step 4/6  按 {split_level} 标题切块（每块 ≤ {max_chars:,} 字符）...")
    chunks = chunk_md_by_headers(md_text, max_chars=max_chars, split_level=split_level)
    log(f"  共 {len(chunks)} 块")
    check()

    # --- Step 5: Restate each chunk (parallel) ---
    workers = max(1, min(int(max_workers), len(chunks)))
    log(f"[重述] Step 5/6  逐块重述（共 {len(chunks)} 块，并发 {workers}）...")

    # Pre-allocate result slots to preserve order
    restated_parts: List[str] = [""] * len(chunks)
    completed = [0]  # mutable counter for thread-safe progress logging

    def _restate_one(idx: int, label: str, chunk_text: str) -> None:
        if cancel_check and cancel_check():
            restated_parts[idx] = f"<!-- 已取消 -->\n\n{chunk_text}"
            return
        short_label = label[:60] if label.startswith("#") else f"[{label[:50]}]"
        log(f"  开始 [{idx + 1}/{len(chunks)}] {short_label}  ({len(chunk_text):,} 字符)")
        if label == "__yaml__":
            # Don't send YAML frontmatter through the restate LLM:
            # all YAML fields are technical metadata (filenames, dates, extractor)
            # and don't need Chinese translation.  Sending them to the LLM causes
            # it to hallucinate full Chinese academic text from the metadata, and
            # _inject_cn_fields() then fails to find the closing --- at the end.
            result = _inject_cn_fields(chunk_text, stem)
        else:
            result = restate_chunk(chunk_text, glossary, client, model=model)
            # The LLM sometimes wraps its output in a ---...--- YAML block because
            # the prompt mentions "YAML frontmatter".  Strip it to avoid spurious
            # YAML separators scattered throughout the document.
            result = _strip_leading_yaml(result)
        restated_parts[idx] = result
        completed[0] += 1
        log(f"  完成 [{completed[0]}/{len(chunks)}] {short_label}  → {len(result):,} 字符")

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_restate_one, i, label, chunk_text): i
            for i, (label, chunk_text) in enumerate(chunks)
        }
        for future in as_completed(futures):
            future.result()  # re-raise any exception from the thread

    # --- Assemble ---
    final_text = "\n\n".join(restated_parts)

    # --- Step 6: Supplementary restatement — fix missed English blocks ---
    log(f"[重述] Step 6/6  检查并补译残留英文块...")
    check()
    final_text, n_fixed = fix_untranslated_blocks(
        final_text,
        glossary,
        client,
        model=model,
        log_cb=log,
        cancel_check=cancel_check,
    )
    if n_fixed:
        log(f"  补译完成，共修复 {n_fixed} 个英文块")
    else:
        log("  未发现需补译的英文块")

    # --- Save ---
    with open(cn_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    log(f"[重述] 完成！中文版：{cn_path}")
    return cn_path, glossary_path


_PREAMBLE_RE = re.compile(
    r'^(?:'
    r'好的[，,。]?|以下是|我将|根据(?:您的)?(?:要求|指示)|下面是|这是|作为|请看|如下[：:]?|'
    r'遵循|按照(?:您的)?要求|根据以上|我会|我来|让我|OK[,，]?|Sure[,，]?'
    r')[^\n]*\n+',
    re.IGNORECASE,
)

# Matches a YAML frontmatter block at the start of a string (---\n...\n---\n)
_LEADING_YAML_RE = re.compile(r'^---\s*\n.*?\n---\s*\n*', re.DOTALL)


def _strip_preamble(text: str) -> str:
    """Remove LLM conversational preamble lines from the start of output."""
    # Strip repeatedly in case there are multiple preamble lines
    while True:
        cleaned = _PREAMBLE_RE.sub("", text, count=1)
        if cleaned == text:
            break
        text = cleaned
    return text.lstrip("\n")


def _strip_leading_yaml(text: str) -> str:
    """Strip any leading YAML frontmatter block the LLM may have injected."""
    return _LEADING_YAML_RE.sub("", text).lstrip("\n")


# ---------------------------------------------------------------------------
# Step 6: Supplementary restatement — fix missed English blocks
# ---------------------------------------------------------------------------

def _en_ratio(text: str) -> float:
    """Fraction of alphabetic characters that are ASCII (i.e. English letters)."""
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return 0.0
    return sum(1 for c in alpha if c.isascii()) / len(alpha)


def _is_structural_para(para: str) -> bool:
    """True if a paragraph is structural and should not be checked for translation."""
    s = para.strip()
    if not s or len(s) < 40:
        return True
    # YAML fence, HTML tags, Markdown tables, headers, math, code blocks, images
    if s.startswith(("---", "<", "|", "#", "$$", "`", "![")):
        return True
    # Markdown table row
    if re.match(r"^\|.*\|", s):
        return True
    return False


def fix_untranslated_blocks(
    text: str,
    glossary: str,
    client: OpenAI,
    model: str = "deepseek-chat",
    en_threshold: float = 0.65,
    min_chars: int = 100,
    max_patch_chars: int = 4000,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Tuple[str, int]:
    """
    Scan assembled Chinese text for large English passages that were missed
    during initial restatement, re-restate them via DeepSeek, and stitch back.

    Text after the references/bibliography section header is left untouched.
    Returns (fixed_text, number_of_patches_fixed).
    """
    def log(msg: str):
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    # Determine where to stop (references section)
    ref_m = _REFERENCES_HEADER_RE.search(text)
    cut_at = ref_m.start() if ref_m else len(text)
    body, tail = text[:cut_at], text[cut_at:]

    # Split body into alternating [content, separator, content, ...] segments.
    # Even indices = content, odd indices = "\n\n..." separators.
    segs = re.split(r"(\n\n+)", body)

    # Classify each content segment: True = needs restatement
    def _needs_restate(seg: str) -> bool:
        return (
            not _is_structural_para(seg)
            and _en_ratio(seg) >= en_threshold
            and len(seg.strip()) >= min_chars
        )

    flags: List[Optional[bool]] = []
    for idx, seg in enumerate(segs):
        if idx % 2 == 1:        # separator
            flags.append(None)
        else:
            flags.append(_needs_restate(seg))

    # Find contiguous English "patches": runs of en=True content segments
    # bridged by their intervening separators.
    patches: List[Tuple[int, int]] = []  # (start_seg_idx, end_seg_idx)
    i = 0
    while i < len(segs):
        if i % 2 == 0 and flags[i]:
            j = i
            # Extend patch while the next content segment is also English
            while j + 2 < len(segs) and flags[j + 1] is None and flags[j + 2]:
                j += 2
            patches.append((i, j))
            i = j + 2
        else:
            i += 1

    if not patches:
        log("[补译] 未发现大段英文块，无需补译")
        return text, 0

    log(f"[补译] 发现 {len(patches)} 个英文块，逐一补译...")
    segs_out = list(segs)

    for pi, (start_i, end_i) in enumerate(patches):
        if cancel_check and cancel_check():
            log("[补译] 用户取消")
            break

        raw = "".join(segs[start_i: end_i + 1])
        log(f"[补译] 块 {pi + 1}/{len(patches)}  {len(raw):,} 字符")

        # Split oversized blocks at paragraph boundaries before sending
        sub_raws = [t for _, t in _split_by_paragraphs("", raw, max_patch_chars)]
        restated_subs: List[str] = []
        for sr in sub_raws:
            r = restate_chunk(sr, glossary, client, model=model, log_cb=log_cb)
            r = _strip_leading_yaml(r)
            restated_subs.append(r)

        segs_out[start_i] = "\n\n".join(restated_subs)
        for k in range(start_i + 1, end_i + 1):
            segs_out[k] = ""

        log(f"[补译] 块 {pi + 1} 完成  → {len(segs_out[start_i]):,} 字符")

    fixed = "".join(segs_out) + tail
    log(f"[补译] 全部补译完成，共修复 {len(patches)} 个块")
    return fixed, len(patches)


def _inject_cn_fields(yaml_chunk: str, stem: str) -> str:
    """Append lang/source_stem fields into YAML frontmatter if absent."""
    if "lang:" in yaml_chunk:
        return yaml_chunk
    inject = f"lang: zh-cn\nsource_stem: {stem}\n"
    # Insert before the closing ---
    updated = re.sub(r'(\n---\s*)$', f"\n{inject}---", yaml_chunk, count=1)
    if updated == yaml_chunk:
        # No closing --- found; append fields before end
        updated = yaml_chunk.rstrip() + f"\n{inject}"
    return updated


# ---------------------------------------------------------------------------
# Step 5b: Full pipeline — one PDF file
# ---------------------------------------------------------------------------

def translate_pdf_file(
    pdf_path: str,
    out_dir: Optional[str] = None,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    model: str = "deepseek-chat",
    max_chars: int = 5000,
    extraction_method: str = "PaddleOCR (远程API)",
    max_workers: int = 5,
) -> Tuple[str, str]:
    """
    Extract PDF → MD, then restate.

    extraction_method options (matches Tab 2/3 labels):
      "PaddleOCR (远程API)"  — remote API with auto-fallback (default)
      "PaddleOCR (本地GPU)"  — force local GPU
      "Legacy (pdfplumber)"  — legacy pdfplumber

    Returns (cn_md_path, glossary_path).
    """
    def log(msg: str):
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    log(f"[重述] PDF 提取（{extraction_method}）：{pdf_path}")
    from paddleocr_pipeline import extract_with_fallback, extract_pdf_legacy

    stem = Path(pdf_path).stem
    pdf_out = os.path.join(os.path.dirname(pdf_path), "paddleocr_md")
    os.makedirs(pdf_out, exist_ok=True)

    if extraction_method == "PaddleOCR (本地GPU)":
        md_path, _ = extract_with_fallback(pdf_path, out_dir=pdf_out, force_local=True)
    elif extraction_method == "Legacy (pdfplumber)":
        md_path, _ = extract_pdf_legacy(pdf_path, out_dir=pdf_out)
    else:
        # "PaddleOCR (远程API)" or any unknown value
        md_path, _ = extract_with_fallback(pdf_path, out_dir=pdf_out)

    log(f"[重述] 提取完成：{md_path}")

    return translate_md_file(
        md_path,
        out_dir=out_dir,
        log_cb=log_cb,
        cancel_check=cancel_check,
        model=model,
        max_chars=max_chars,
        max_workers=max_workers,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(cb: Optional[Callable], msg: str):
    logger.info(msg)
    if cb:
        cb(msg)


def collect_files(folder: str) -> List[str]:
    """Return all PDF and MD files in folder (non-recursive)."""
    result = []
    for entry in sorted(Path(folder).iterdir()):
        if entry.is_file() and entry.suffix.lower() in (".pdf", ".md"):
            result.append(str(entry))
    return result
