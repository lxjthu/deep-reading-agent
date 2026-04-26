"""
Compare Router - AI synthesis for literature comparison
"""
import os
import sys
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()


class CompareRequest(BaseModel):
    step: str
    papers: List[str]
    subQuestions: List[str]
    paperData: list
    api_key: Optional[str] = None
    mode: Optional[str] = "single"


class LongCompareRequest(BaseModel):
    dimension: str
    papers: List[str]
    paperData: list
    api_key: Optional[str] = None
    mode: Optional[str] = "single"


def get_api_key(provided_key: Optional[str] = None) -> str:
    if provided_key and provided_key.strip():
        return provided_key.strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


def format_inline_citation(authors: list, year) -> str:
    """Format inline citation: (Author et al., Year)"""
    if not authors:
        return f"(佚名, {year})"
    # Try to get last name of first author
    first = authors[0].strip()
    last_name = first.split()[-1] if first else first
    if len(authors) == 1:
        return f"({last_name}, {year})"
    elif len(authors) == 2:
        second = authors[1].strip().split()[-1]
        return f"({last_name} & {second}, {year})"
    else:
        return f"({last_name} et al., {year})"


def build_paper_header(paper: dict) -> str:
    """Build paper identification string for prompt."""
    title = paper.get('title', paper.get('filename', '未知'))
    authors = paper.get('authors', [])
    year = paper.get('year', 'n.d.')
    cite = format_inline_citation(authors, year)
    return f"【{title} {cite}】"


def build_reference_list(papers: list) -> str:
    """
    Build APA-style reference list programmatically from metadata.
    Never rely on LLM to generate references.
    """
    refs = []
    for paper in papers:
        authors = paper.get('authors', [])
        year = paper.get('year', 'n.d.')
        title = paper.get('title', paper.get('filename', ''))
        journal = paper.get('journal') or paper.get('source', '')
        volume = str(paper.get('volume', '')) if paper.get('volume') else ''
        issue = str(paper.get('issue', '')) if paper.get('issue') else ''
        pages = str(paper.get('pages', '')) if paper.get('pages') else ''
        doi = paper.get('doi', '')

        # APA author formatting
        if not authors:
            author_str = "佚名"
        elif len(authors) == 1:
            author_str = authors[0]
        elif len(authors) <= 3:
            author_str = ", ".join(authors[:-1]) + ", & " + authors[-1]
        else:
            author_str = ", ".join(authors[:3]) + ", 等"

        ref = f"{author_str} ({year}). {title}."
        if journal:
            ref += f" *{journal}*"
            if volume:
                ref += f", *{volume}*"
                if issue:
                    ref += f"({issue})"
            if pages:
                ref += f", {pages}"
            ref += "."
        if doi:
            ref += f" https://doi.org/{doi}"

        # Sort key: first author's last name
        sort_key = (authors[0].split()[-1] if authors else "佚名").lower()
        refs.append((sort_key, ref))

    refs.sort(key=lambda x: x[0])
    ref_block = "\n\n".join(r for _, r in refs)
    return f"\n\n---\n\n## 参考文献\n\n{ref_block}"


SYSTEM_PROMPT = (
    "你是一位中文学术写作专家，擅长撰写规范的文献综述段落。"
    "你的任务是根据已有的精读分析内容，综合多篇文献的观点，"
    "写出适合直接插入学术论文文献综述部分的高质量文字。"
    "不要捏造任何数据或结论，严格基于所提供的文献内容进行综合。"
    "引用格式使用间注法：（第一作者姓氏等，年份），或（作者A & 作者B, 年份）。"
    "不要在回复中包含参考文献目录，参考文献将由系统自动生成。"
)


def build_single_prompt(label: str, papers: list) -> str:
    """Single question/dimension: one coherent paragraph."""
    n = len(papers)
    parts = [
        f"以下是{n}篇文献在「{label}」这一问题上的精读分析内容。",
        "",
        "【写作任务】",
        "请综合这些文献的内容，写出**恰好一段**连贯的学术性综述文字（8～15句）。",
        "",
        "【段落结构要求】",
        "① 首句：用主题句点明该问题在学界的整体关注焦点或争议；",
        "② 中间：逐一或分组介绍各文献的研究视角、数据、发现，比较异同；",
        "③ 重点揭示：哪些结论已形成共识？哪些仍存在分歧或对立？",
        "④ 末句：指出现有研究的局限、空白或对未来研究的启示；",
        "",
        "【写作规范】",
        "- 行文流畅、逻辑连贯，适合直接嵌入学术论文；",
        "- 每处引用标注间注：（第一作者姓，年份）或（作者A & 作者B, 年份）；",
        "- 不要加标题、不要分小节、不要写引言或结尾感谢语；",
        "- 不要写参考文献目录（系统自动生成）。",
        "",
        "【文献内容】",
    ]
    for paper in papers:
        parts.append(build_paper_header(paper))
        for sq, content in paper.get('subQuestions', {}).items():
            parts.append(f"  问题：{sq}")
            parts.append(f"  {content[:1500].strip()}")
        parts.append("")
    return "\n".join(parts)


def build_multi_prompt(label: str, sub_questions: list, papers: list) -> str:
    """Multi-question: introduction + one section per question + conclusion."""
    n = len(papers)
    sq_list = "、".join(f"「{sq}」" for sq in sub_questions)
    parts = [
        f"以下是{n}篇文献在「{label}」步骤下，针对以下{len(sub_questions)}个子问题的精读分析内容：",
        sq_list,
        "",
        "【写作任务】",
        "请撰写一篇结构化的分节文献综述，格式如下：",
        "",
        "**引言**（1句）：用一句话概括该步骤的整体研究图景；",
        "",
        f"**各子问题分节**（共{len(sub_questions)}节）：",
        "- 每节以 ### [子问题标题] 为标题；",
        "- 正文1～2段，横向比较各文献在该子问题上的数据、方法、结论；",
        "- 明确指出共识与分歧；",
        "",
        "**结论**（1句）：点出跨问题的整体研究局限或未来方向；",
        "",
        "【写作规范】",
        "- 每处引用标注间注：（第一作者姓，年份）；",
        "- 不要写参考文献目录（系统自动生成）；",
        "- 全文使用学术中文。",
        "",
        "【文献内容】",
    ]
    for paper in papers:
        parts.append(build_paper_header(paper))
        for sq, content in paper.get('subQuestions', {}).items():
            parts.append(f"  [{sq}]")
            parts.append(f"  {content[:1200].strip()}")
        parts.append("")
    return "\n".join(parts)


def build_long_single_prompt(dimension: str, papers: list) -> str:
    """Long context single dimension: one paragraph."""
    n = len(papers)
    parts = [
        f"以下是{n}篇文献在「{dimension}」维度上的精读分析内容。",
        "",
        "【写作任务】",
        "请综合这些文献，写出**恰好一段**连贯的学术性综述文字（8～15句）。",
        "",
        "【段落结构要求】",
        "① 首句：主题句，点明该维度在学界的整体关注或争议；",
        "② 中间：介绍各文献的研究路径、数据来源、核心发现，横向比较；",
        "③ 指出：哪些结论已有共识？哪些存在分歧？",
        "④ 末句：现有研究的局限与未来方向；",
        "",
        "【写作规范】",
        "- 每处引用标注间注：（第一作者姓，年份）；",
        "- 不要分节、不要加标题、不要写参考文献目录；",
        "- 学术中文行文。",
        "",
        "【文献内容】",
    ]
    for paper in papers:
        parts.append(build_paper_header(paper))
        content = paper.get('content', '')[:2000].strip()
        parts.append(f"  {content}")
        parts.append("")
    return "\n".join(parts)


def build_cross_dim_prompt(papers: list) -> str:
    """
    Cross-dimension synthesis: questions prefixed with step name.
    subQuestions keys are like "[第一步] 研究问题" / "[第三步] 数据来源".
    Groups by step in prompt, writes one section per step.
    """
    # Collect all step groups from question keys
    step_groups: dict = {}
    for paper in papers:
        for key in paper.get('subQuestions', {}).keys():
            if key.startswith('[') and ']' in key:
                step = key[1:key.index(']')]
                sub = key[key.index(']') + 1:].strip()
            else:
                step = '其他'
                sub = key
            step_groups.setdefault(step, set()).add(sub)

    n = len(papers)
    step_list = "、".join(f"「{s}」" for s in step_groups)
    parts = [
        f"以下是{n}篇文献在**多个分析维度**上的精读内容，涉及：{step_list}。",
        "",
        "【写作任务】",
        "请撰写一篇**跨维度结构化文献综述**，格式如下：",
        "",
        "① **引言**（1句）：用一句话概括这批文献整体的研究图景与共性关切；",
        "",
        f"② **各维度分节**（共{len(step_groups)}节）：",
        "   - 每节以 `### [维度名称]` 为标题；",
        "   - 正文1～2段，横向比较各文献在该维度的数据/方法/发现；",
        "   - 明确指出共识与分歧；",
        "   - 如该维度下有多个子问题，按子问题自然过渡，不再单独分节；",
        "",
        "③ **跨维度结论**（1句）：综合各维度，点出整体研究局限或未来突破方向；",
        "",
        "【引用规范】",
        "- 间注法：（第一作者姓，年份）；",
        "- 不写参考文献目录（系统自动生成）；",
        "- 全文学术中文。",
        "",
        "【文献内容（按维度·子问题组织）】",
    ]

    for step, sub_set in step_groups.items():
        parts.append(f"\n▶ **{step}**")
        for sub in sub_set:
            key = f"[{step}] {sub}"
            parts.append(f"  · {sub}")
            for paper in papers:
                sq = paper.get('subQuestions', {})
                content = sq.get(key, '').strip()
                if content:
                    header = build_paper_header(paper)
                    parts.append(f"    {header}：{content[:1000]}")
        parts.append("")

    return "\n".join(parts)


def build_long_multi_prompt(dimensions: list, papers: list) -> str:
    """Long context multi-dimension: sectioned by dimension."""
    n = len(papers)
    dim_label = "、".join(f"「{d}」" for d in dimensions)
    parts = [
        f"以下是{n}篇文献在{len(dimensions)}个维度上的精读分析内容：{dim_label}。",
        "",
        "【写作任务】",
        "请撰写一篇结构化的分节文献综述：",
        "- **引言**（1句）：概括这些维度的整体研究图景；",
        f"- **分节**（共{len(dimensions)}节，每节标题 ### [维度名]）：每节1～2段，横向比较各文献，指出共识与分歧；",
        "- **结论**（1句）：整体局限与未来方向。",
        "",
        "【写作规范】",
        "- 间注引用：（第一作者姓，年份）；",
        "- 不写参考文献目录；学术中文。",
        "",
        "【文献内容】",
    ]
    for paper in papers:
        parts.append(build_paper_header(paper))
        for dim, content in paper.get('dimensions', {}).items():
            parts.append(f"  [{dim}]")
            parts.append(f"  {str(content)[:1200].strip()}")
        parts.append("")
    return "\n".join(parts)


@router.post("/analyze")
async def analyze_comparison(req: CompareRequest):
    """Generate AI synthesis for 7-step or 4-step comparison."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        mode = req.mode or ("multi" if len(req.subQuestions) > 1 else "single")

        if mode == "cross":
            prompt = build_cross_dim_prompt(req.paperData)
        elif mode == "multi":
            prompt = build_multi_prompt(req.step, req.subQuestions, req.paperData)
        else:
            prompt = build_single_prompt(req.step, req.paperData)

        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.65,
            max_tokens=5000,
        )

        synthesis = response.choices[0].message.content
        references = build_reference_list(req.paperData)
        return {"synthesis": synthesis + references}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze_long")
async def analyze_long_comparison(req: LongCompareRequest):
    """Generate AI synthesis for long context comparison."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        mode = req.mode or "single"

        # For multi-dimension long context, paperData items may carry a 'dimensions' dict
        if mode == "multi":
            # Collect unique dimensions from paperData
            all_dims = []
            for p in req.paperData:
                for d in p.get('dimensions', {}).keys():
                    if d not in all_dims:
                        all_dims.append(d)
            prompt = build_long_multi_prompt(all_dims or [req.dimension], req.paperData)
        else:
            prompt = build_long_single_prompt(req.dimension, req.paperData)

        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.65,
            max_tokens=5000,
        )

        synthesis = response.choices[0].message.content
        references = build_reference_list(req.paperData)
        return {"synthesis": synthesis + references}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
