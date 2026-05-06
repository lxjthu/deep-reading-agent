"""Compare Router - authenticated comparison with DB persistence."""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import PROJECT_ROOT, get_db
from db.models import Artifact, BibEntry, Job, JobBibEntry, ReadingItem, User
from db.utils import compute_dedup_key
from backend.utils.api_key import validate_deepseek_key

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()
RESULTS_ROOT = PROJECT_ROOT / "deep_reading_results"
RESULTS_ROOT.mkdir(parents=True, exist_ok=True)


class CompareRequest(BaseModel):
    step: str
    papers: List[str] = Field(default_factory=list)
    subQuestions: List[str] = Field(default_factory=list)
    paperData: list = Field(default_factory=list)
    bib_entry_ids: List[str] = Field(default_factory=list)
    api_key: Optional[str] = None
    mode: Optional[str] = "single"


class LongCompareRequest(BaseModel):
    dimension: str
    papers: List[str] = Field(default_factory=list)
    paperData: list = Field(default_factory=list)
    bib_entry_ids: List[str] = Field(default_factory=list)
    api_key: Optional[str] = None
    mode: Optional[str] = "single"


class StructuredStepResponse(BaseModel):
    label: str
    sub_questions: dict[str, str] = Field(default_factory=dict)


class StructuredReadingResponse(BaseModel):
    job_id: str
    bib_entry_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal: str = ""
    doi: str = ""
    mode: str
    dimensions: dict[str, str] = Field(default_factory=dict)
    steps: dict[str, StructuredStepResponse] = Field(default_factory=dict)


def get_api_key(provided_key: Optional[str] = None) -> str:
    try:
        return validate_deepseek_key(provided_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def compute_expires_at(user: User) -> datetime | None:
    if user.role == "normal":
        return utcnow_naive() + timedelta(hours=24)
    return None


def get_results_dir(user_id: int, job_id: str) -> Path:
    result_dir = RESULTS_ROOT / str(user_id) / job_id
    result_dir.mkdir(parents=True, exist_ok=True)
    return result_dir


def build_storage_path(absolute_path: Path) -> str:
    try:
        return absolute_path.relative_to(RESULTS_ROOT).as_posix()
    except ValueError:
        return absolute_path.as_posix()


def parse_paper_authors(raw_authors) -> list[str]:
    if raw_authors is None:
        return []
    if isinstance(raw_authors, list):
        return [str(item).strip() for item in raw_authors if str(item).strip()]
    text = str(raw_authors).strip()
    if not text:
        return []
    normalized = text.replace("；", ";").replace(",", ";").replace(" and ", ";")
    return [part.strip() for part in normalized.split(";") if part.strip()]


def bib_entry_to_paper_data(bib_entry: BibEntry) -> dict:
    return {
        "title": bib_entry.title,
        "authors": json.loads(bib_entry.authors_json or "[]"),
        "year": bib_entry.year,
        "journal": bib_entry.journal or "",
        "doi": bib_entry.doi or "",
        "subQuestions": {},
        "dimensions": {},
        "content": bib_entry.abstract or "",
    }


async def build_structured_paper_data(
    db: AsyncSession,
    members: list[BibEntry],
) -> list[dict]:
    paper_data: list[dict] = []
    for bib_entry in members:
        items = (
            await db.execute(
                select(ReadingItem)
                .where(
                    ReadingItem.owner_user_id == bib_entry.owner_user_id,
                    ReadingItem.bib_entry_id == bib_entry.id,
                )
                .order_by(ReadingItem.created_at.desc(), ReadingItem.sort_order.asc(), ReadingItem.id.asc())
            )
        ).scalars().all()

        paper = bib_entry_to_paper_data(bib_entry)
        seen_keys: set[str] = set()
        for item in items:
            if item.item_key in seen_keys:
                continue
            seen_keys.add(item.item_key)

            if item.mode == "long":
                paper["dimensions"][item.item_label] = item.content
                if not paper["content"] and item.content:
                    paper["content"] = item.content
            elif item.section_type == "subquestion":
                paper["subQuestions"][item.item_label] = item.content

        paper_data.append(paper)

    return paper_data


async def resolve_compare_members(
    db: AsyncSession,
    user: User,
    bib_entry_ids: list[str],
    paper_data: list[dict],
) -> list[BibEntry]:
    members: list[BibEntry] = []
    seen: set[str] = set()

    if bib_entry_ids:
        for sort_order, bib_entry_id in enumerate(bib_entry_ids):
            bib_entry = await db.get(BibEntry, bib_entry_id)
            if bib_entry is None or bib_entry.owner_user_id != user.id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bib entry not found")
            if bib_entry.id in seen:
                continue
            seen.add(bib_entry.id)
            members.append(bib_entry)
    else:
        for paper in paper_data:
            title = str(paper.get("title") or paper.get("filename") or "").strip()
            authors = parse_paper_authors(paper.get("authors"))
            year = paper.get("year")
            doi = str(paper.get("doi") or "").strip() or None
            dedup_key = compute_dedup_key(doi, title, authors, year)
            bib_entry = (
                await db.execute(
                    select(BibEntry).where(
                        BibEntry.owner_user_id == user.id,
                        BibEntry.dedup_key == dedup_key,
                    )
                )
            ).scalar_one_or_none()
            if bib_entry is None and title:
                bib_entry = (
                    await db.execute(
                        select(BibEntry).where(
                            BibEntry.owner_user_id == user.id,
                            BibEntry.title == title,
                        )
                    )
                ).scalar_one_or_none()
            if bib_entry is None or bib_entry.id in seen:
                continue
            seen.add(bib_entry.id)
            members.append(bib_entry)

    if len(members) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="对比分析至少需要 2 篇文献。")
    return members


async def create_compare_job(
    db: AsyncSession,
    user: User,
    job_type: str,
    params_json: dict,
    members: list[BibEntry],
) -> str:
    job_id = str(uuid.uuid4())
    db.add(
        Job(
            id=job_id,
            owner_user_id=user.id,
            job_type=job_type,
            status="pending",
            params_json=json.dumps(params_json, ensure_ascii=False),
            progress=0,
            current_stage="等待开始...",
            expires_at=compute_expires_at(user),
        )
    )
    for sort_order, bib_entry in enumerate(members):
        db.add(
            JobBibEntry(
                job_id=job_id,
                bib_entry_id=bib_entry.id,
                role="compare_member",
                sort_order=sort_order,
            )
        )
    await db.flush()
    return job_id


async def persist_compare_result(
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
            artifact_type="compare_md",
            filename=filename,
            storage_path=storage_path,
            size_bytes=path.stat().st_size,
            expires_at=compute_expires_at(user),
        )
    )
    return storage_path


def build_compare_markdown(title: str, synthesis: str) -> str:
    return f"# {title}\n\n{synthesis}\n"


def extract_step_id(item_key: str) -> str | None:
    match = re.search(r"\.step(\d+)", item_key or "")
    if not match:
        return None
    number = int(match.group(1))
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if 1 <= number <= len(cn):
        return f"第{cn[number - 1]}步"
    return None


@router.get("/jobs/{job_id}/structured", response_model=StructuredReadingResponse)
async def get_structured_reading(
    job_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> StructuredReadingResponse:
    job = await db.get(Job, job_id)
    if job is None or job.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reading job not found")
    if job.job_type not in {"reading_long", "reading_quant", "reading_qual"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported job type")

    target = (
        await db.execute(
            select(JobBibEntry).where(
                JobBibEntry.job_id == job_id,
                JobBibEntry.role == "target",
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target bib entry not found")

    bib_entry = await db.get(BibEntry, target.bib_entry_id)
    if bib_entry is None or bib_entry.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bib entry not found")

    items = (
        await db.execute(
            select(ReadingItem)
            .where(ReadingItem.job_id == job_id)
            .order_by(ReadingItem.sort_order.asc(), ReadingItem.id.asc())
        )
    ).scalars().all()
    if not items:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structured reading items not found")

    response = StructuredReadingResponse(
        job_id=job.id,
        bib_entry_id=bib_entry.id,
        title=bib_entry.title,
        authors=json.loads(bib_entry.authors_json or "[]"),
        year=bib_entry.year,
        journal=bib_entry.journal or "",
        doi=bib_entry.doi or "",
        mode=items[0].mode,
    )

    for item in items:
        if item.mode == "long":
            response.dimensions[item.item_label] = item.content
            continue
        if item.section_type == "step":
            step_id = extract_step_id(item.item_key)
            if not step_id:
                continue
            response.steps[step_id] = StructuredStepResponse(label=item.item_label, sub_questions={})
            continue
        if item.section_type == "subquestion" and item.parent_key:
            step_id = extract_step_id(item.parent_key)
            if not step_id:
                continue
            if step_id not in response.steps:
                response.steps[step_id] = StructuredStepResponse(label=step_id, sub_questions={})
            response.steps[step_id].sub_questions[item.item_label] = item.content

    return response


async def ensure_paper_data(db: AsyncSession, paper_data: list[dict], members: list[BibEntry]) -> list[dict]:
    if members:
        structured = await build_structured_paper_data(db, members)
        has_structured_content = any(
            paper.get("dimensions") or paper.get("subQuestions") or paper.get("content")
            for paper in structured
        )
        if has_structured_content:
            return structured
    if paper_data:
        return paper_data
    return [bib_entry_to_paper_data(member) for member in members]


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
async def analyze_comparison(
    req: CompareRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI synthesis for 7-step or 4-step comparison."""
    try:
        from openai import OpenAI

        members = await resolve_compare_members(db, user, req.bib_entry_ids, req.paperData)
        paper_data = await ensure_paper_data(db, req.paperData, members)
        mode = req.mode or ("multi" if len(req.subQuestions) > 1 else "single")
        job_id = await create_compare_job(
            db,
            user,
            "compare",
            {
                "step": req.step,
                "subQuestions": req.subQuestions,
                "mode": mode,
            },
            members,
        )
        job = await db.get(Job, job_id)
        job.status = "running"
        job.progress = 20
        job.current_stage = "生成对比综述..."
        job.started_at = utcnow_naive()
        await db.flush()

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        if mode == "cross":
            prompt = build_cross_dim_prompt(paper_data)
        elif mode == "multi":
            prompt = build_multi_prompt(req.step, req.subQuestions, paper_data)
        else:
            prompt = build_single_prompt(req.step, paper_data)

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
        references = build_reference_list(paper_data)
        final_text = synthesis + references
        title = f"对比分析：{req.step}"
        storage_path = await persist_compare_result(
            db,
            user,
            job_id,
            f"compare_{req.step}_{job_id}.md",
            build_compare_markdown(title, final_text),
        )
        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.finished_at = utcnow_naive()
        await db.commit()
        return {"synthesis": final_text, "job_id": job_id, "output_path": storage_path}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze_long")
async def analyze_long_comparison(
    req: LongCompareRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate AI synthesis for long context comparison."""
    try:
        from openai import OpenAI

        members = await resolve_compare_members(db, user, req.bib_entry_ids, req.paperData)
        paper_data = await ensure_paper_data(db, req.paperData, members)
        mode = req.mode or "single"
        job_id = await create_compare_job(
            db,
            user,
            "compare",
            {
                "dimension": req.dimension,
                "mode": mode,
            },
            members,
        )
        job = await db.get(Job, job_id)
        job.status = "running"
        job.progress = 20
        job.current_stage = "生成长综述..."
        job.started_at = utcnow_naive()
        await db.flush()

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")

        if mode == "multi":
            all_dims = []
            for p in paper_data:
                for d in p.get("dimensions", {}).keys():
                    if d not in all_dims:
                        all_dims.append(d)
            prompt = build_long_multi_prompt(all_dims or [req.dimension], paper_data)
        else:
            prompt = build_long_single_prompt(req.dimension, paper_data)

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
        references = build_reference_list(paper_data)
        final_text = synthesis + references
        title = f"长综述对比：{req.dimension}"
        storage_path = await persist_compare_result(
            db,
            user,
            job_id,
            f"compare_long_{job_id}.md",
            build_compare_markdown(title, final_text),
        )
        job.status = "success"
        job.progress = 100
        job.current_stage = "完成"
        job.finished_at = utcnow_naive()
        await db.commit()
        return {"synthesis": final_text, "job_id": job_id, "output_path": storage_path}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
