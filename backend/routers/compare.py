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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from auth.dependencies import current_user
from db import get_db
from db.models import Annotation, Artifact, BibEntry, DimensionItem, DimensionSet, Job, JobBibEntry, ReadingItem, ReadingItemEdit, User
from db.utils import compute_dedup_key
from result_storage import build_result_storage_path, get_results_root
from backend.utils.api_key import validate_deepseek_key

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()
RESULTS_ROOT = get_results_root()


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


class CompareSynthesisRequest(BaseModel):
    mode: str
    bib_entry_ids: list[str] = Field(default_factory=list)
    api_key: Optional[str] = None
    selected_dimensions: list[str] = Field(default_factory=list)


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
        "volume": bib_entry.volume or "",
        "issue": bib_entry.issue or "",
        "pages": bib_entry.pages or "",
        "subQuestions": {},
        "dimensions": {},
        "content": bib_entry.abstract or "",
    }


async def build_compare_response(
    mode: str,
    bib_entries_items: dict[str, list[ReadingItem]],
    bib_entries: dict[str, BibEntry],
    user_id: int | None = None,
    db: AsyncSession | None = None,
    *,
    edits_map: dict[int, ReadingItemEdit] | None = None,
    annotations_map: dict[int, list] | None = None,
) -> dict:
    mode_labels = {"long": "长文本精读", "quant": "七步精读", "qual": "四步精读"}
    papers = []

    long_dim_set_map: dict[str, str] = {}
    if mode == "long" and db is not None and user_id is not None:
        rows = (
            await db.execute(
                select(DimensionItem.dim_name, DimensionSet.name)
                .join(DimensionSet, DimensionItem.set_id == DimensionSet.id)
                .where(DimensionSet.owner_user_id == user_id)
            )
        ).all()
        for dim_name, set_name in rows:
            if dim_name not in long_dim_set_map:
                long_dim_set_map[dim_name] = set_name

    for bib_id, items in bib_entries_items.items():
        if bib_id not in bib_entries:
            continue
        bib = bib_entries[bib_id]
        paper = {
            "id": bib.id,
            "title": bib.title,
            "authors": json.loads(bib.authors_json or "[]"),
            "year": bib.year,
            "journal": bib.journal or "",
            "doi": bib.doi or "",
        }

        if mode == "long":
            dimensions = []
            seen: set[str] = set()
            for item in items:
                if item.item_key in seen:
                    continue
                seen.add(item.item_key)
                dim_dict: dict = {
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                }
                if edits_map and item.id in edits_map:
                    dim_dict["edit"] = {
                        "edited_content": edits_map[item.id].edited_content,
                        "updated_at": edits_map[item.id].updated_at.isoformat() if edits_map[item.id].updated_at else None,
                    }
                if annotations_map and item.id in annotations_map:
                    dim_dict["annotations"] = [
                        {
                            "id": a.id,
                            "source_type": a.source_type,
                            "selected_text": a.selected_text,
                            "note": a.note,
                            "char_start": a.char_start,
                            "char_end": a.char_end,
                            "is_ai_generated": a.is_ai_generated,
                            "color": a.color,
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in annotations_map[item.id]
                    ]
                ds_name = long_dim_set_map.get(item.item_label)
                if ds_name is not None:
                    dim_dict["dim_set_name"] = ds_name
                dimensions.append(dim_dict)
            paper["dimensions"] = dimensions
        else:
            steps: dict[str, dict] = {}
            for item in items:
                step_name = item.parent_key or item.item_label
                if step_name not in steps:
                    steps[step_name] = {"label": step_name, "subQuestions": []}
                sq: dict = {
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                }
                if edits_map and item.id in edits_map:
                    sq["edit"] = {
                        "edited_content": edits_map[item.id].edited_content,
                        "updated_at": edits_map[item.id].updated_at.isoformat() if edits_map[item.id].updated_at else None,
                    }
                if annotations_map and item.id in annotations_map:
                    sq["annotations"] = [
                        {
                            "id": a.id,
                            "source_type": a.source_type,
                            "selected_text": a.selected_text,
                            "note": a.note,
                            "char_start": a.char_start,
                            "char_end": a.char_end,
                            "is_ai_generated": a.is_ai_generated,
                            "color": a.color,
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in annotations_map[item.id]
                    ]
                steps[step_name]["subQuestions"].append(sq)
            paper["steps"] = steps

        papers.append(paper)

    return {"mode": mode, "label": mode_labels.get(mode, ""), "papers": papers}


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


@router.get("/reading-data")
async def get_reading_data(
    mode: str = Query(..., pattern=r"^(long|quant|qual)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    all_items = (
        await db.execute(
            select(ReadingItem)
            .where(
                ReadingItem.owner_user_id == user.id,
                ReadingItem.mode == mode,
            )
            .order_by(ReadingItem.bib_entry_id, ReadingItem.created_at.desc(), ReadingItem.sort_order.asc(), ReadingItem.id.asc())
        )
    ).scalars().all()

    if not all_items:
        return {"mode": mode, "label": {"long": "长文本精读", "quant": "七步精读", "qual": "四步精读"}.get(mode, ""), "papers": []}

    job_created_at: dict[str, datetime] = {}
    for item in all_items:
        if item.job_id not in job_created_at:
            job_created_at[item.job_id] = item.created_at

    latest_job_per_bib: dict[str, str] = {}
    for item in all_items:
        bib = item.bib_entry_id
        cur = latest_job_per_bib.get(bib)
        if cur is None or job_created_at.get(item.job_id, datetime.min) > job_created_at.get(cur, datetime.min):
            latest_job_per_bib[bib] = item.job_id

    filtered_items = [item for item in all_items if item.job_id == latest_job_per_bib.get(item.bib_entry_id)]

    seen_keys: dict[str, set[str]] = {}
    deduped_items: list[ReadingItem] = []
    for item in filtered_items:
        bib = item.bib_entry_id
        key = item.item_key
        if bib not in seen_keys:
            seen_keys[bib] = set()
        if key in seen_keys[bib]:
            continue
        seen_keys[bib].add(key)
        deduped_items.append(item)

    bib_entries_items: dict[str, list[ReadingItem]] = {}
    bib_ids: set[str] = set()
    for item in deduped_items:
        bib_entries_items.setdefault(item.bib_entry_id, []).append(item)
        bib_ids.add(item.bib_entry_id)
    for bib in bib_entries_items:
        bib_entries_items[bib].sort(key=lambda it: (it.sort_order, it.id))

    bib_rows = (
        await db.execute(
            select(BibEntry).where(BibEntry.id.in_(bib_ids))
        )
    ).scalars().all()
    bib_entries = {b.id: b for b in bib_rows}

    all_item_ids = [item.id for items in bib_entries_items.values() for item in items]

    edit_rows = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.owner_user_id == user.id,
                ReadingItemEdit.reading_item_id.in_(all_item_ids),
            )
        )
    ).scalars().all()
    edits_map: dict[int, ReadingItemEdit] = {e.reading_item_id: e for e in edit_rows}

    ann_rows = (
        await db.execute(
            select(Annotation).where(
                Annotation.owner_user_id == user.id,
                Annotation.source_type.in_(["compare_card", "ai_summary"]),
                Annotation.source_id.in_([str(iid) for iid in all_item_ids]),
            )
        )
    ).scalars().all()
    annotations_map: dict[int, list] = {}
    for ann in ann_rows:
        key = int(ann.source_id)
        annotations_map.setdefault(key, []).append(ann)

    return await build_compare_response(
        mode, bib_entries_items, bib_entries, user.id, db,
        edits_map=edits_map,
        annotations_map=annotations_map,
    )


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
    storage_path = build_result_storage_path(path)
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


async def gather_bib_references(
    db: AsyncSession,
    members: list[BibEntry],
) -> dict[str, list[dict]]:
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
                "volume": ref.volume or "",
                "issue": ref.issue or "",
                "pages": ref.pages or "",
                "doi": ref.doi or "",
                "raw_text": ref.raw_text or "",
            })
        result[member.id] = items
    return result


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


def _safe_year(year) -> str:
    return str(year) if year else "年份不详"


_CITE_PATTERN = re.compile(
    r'\('
    r'([^,，)]+?)'
    r'\s*[,\uff0c]\s*'
    r'(\d{4}|年份不详|n\.d\.)'
    r'(?:\s*,\s*转引自\s*[^)]+)?'
    r'\)',
    re.UNICODE,
)


def extract_cited_tags(text: str) -> set[str]:
    tags = set()
    for m in _CITE_PATTERN.finditer(text):
        author_part = m.group(1).strip()
        year_part = m.group(2).strip()
        tags.add(f"({author_part}, {year_part})")
    return tags


def _collect_flat_secondary_refs(
    bib_refs: dict[str, list[dict]],
    members: list[BibEntry],
) -> list[tuple[str, dict]]:
    flat: list[tuple[str, dict]] = []
    for member in members:
        for ref in bib_refs.get(member.id, []):
            flat.append((member.id, ref))
    return flat


def _build_secondary_ref_check_prompt(synthesis_body: str, flat_refs: list[tuple[str, dict]]) -> str:
    parts = [
        "",
        "【任务】",
        "以下是已生成的综述正文，以及所有候选的二次引用文献。",
        "请判断综述正文中实际引用（包括直接引用和转引）了哪些二次引用文献。",
        "",
        "【综述正文】",
        synthesis_body,
        "",
        "【候选二次引用文献】",
        "",
    ]
    for idx, (_, ref) in enumerate(flat_refs, 1):
        ref_cite = format_cite_tag(ref.get('authors', []), _safe_year(ref.get('year')))
        ref_title = ref.get('title') or ref.get('raw_text', '')[:80]
        parts.append(f"[S{idx}] {ref_cite} — {ref_title}")
    parts.append("")
    parts.append("【输出要求】")
    parts.append("请只输出被综述正文实际引用的文献编号，用逗号分隔。例如：S1,S3,S7")
    parts.append("如果没有引用任何二次引用文献，输出：无")
    return "\n".join(parts)


def _parse_cited_ref_ids(response_text: str) -> set[int]:
    text = response_text.strip()
    if "无" in text or not text:
        return set()
    return {int(m.group(1)) for m in re.finditer(r'S(\d+)', text)}


def _filter_bib_refs_by_indices(
    bib_refs: dict[str, list[dict]],
    members: list[BibEntry],
    cited_indices: set[int],
) -> dict[str, list[dict]]:
    if not cited_indices:
        return {m.id: [] for m in members}
    filtered: dict[str, list[dict]] = {}
    flat_idx = 0
    for member in members:
        kept: list[dict] = []
        for ref in bib_refs.get(member.id, []):
            flat_idx += 1
            if flat_idx in cited_indices:
                kept.append(ref)
        filtered[member.id] = kept
    return filtered


def build_paper_metadata_block(papers: list[dict], bib_refs: dict[str, list[dict]], members: list[BibEntry]) -> str:
    lines = [f"以下是 {len(papers)} 篇文献的元信息，用于引用标注：", ""]

    bib_id_to_idx: dict[str, int] = {}
    for i, member in enumerate(members):
        bib_id_to_idx[member.id] = i

    for i, paper in enumerate(papers):
        title = paper.get('title') or paper.get('filename') or '未知'
        authors = paper.get('authors', [])
        year = _safe_year(paper.get('year'))
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
        year_p = _safe_year(paper.get('year'))
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


def _match_dimension_content(content_dict: dict, dim_label: str) -> str:
    if dim_label in content_dict:
        return str(content_dict[dim_label])

    for key, value in content_dict.items():
        if "]" in key:
            clean = key.split("]", 1)[-1].strip()
            if clean == dim_label:
                return str(value)

    for key, value in content_dict.items():
        if dim_label in key or key in dim_label:
            return str(value)

    parts = [str(v).strip() for v in content_dict.values() if str(v).strip()]
    return "\n\n".join(parts) if parts else ""


def build_synthesis_dimension_prompt(
    dim_label: str,
    papers: list[dict],
    content_field: str = "subQuestions",
) -> str:
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
        cite = format_cite_tag(paper.get('authors', []), _safe_year(paper.get('year')))
        parts.append(f"━━━ 文献 {i + 1} {cite} ━━━")

        content_dict = paper.get(content_field, {})
        if isinstance(content_dict, dict):
            matched = _match_dimension_content(content_dict, dim_label)
            parts.append(matched.strip())
        else:
            parts.append(str(content_dict).strip())
        parts.append("")

    return "\n".join(parts)


def build_gbt7714_references(
    papers: list[dict],
    bib_refs: dict[str, list[dict]],
    members: list[BibEntry],
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
            entry += f" {journal}, {year}"
            if volume:
                entry += f", {volume}"
                if issue:
                    entry += f" ({issue})"
            if pages:
                entry += f": {pages}"
            entry += "."
        else:
            entry += f" {year}."
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
        lines.append("")

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
            seen_secondary.add(dedup_key)

            author_str = ", ".join(str(a) for a in ref_authors) if ref_authors else "佚名"
            ref_title = ref.get('title') or ref.get('raw_text', '')[:80]
            ref_journal = ref.get('journal', '')
            ref_volume = ref.get('volume', '')
            ref_issue = ref.get('issue', '')
            ref_pages = ref.get('pages', '')
            entry = f"[{ref_num}] {author_str}. {ref_title}[J]."
            if ref_journal:
                entry += f" {ref_journal}, {ref_year}"
                if ref_volume:
                    entry += f", {ref_volume}"
                    if ref_issue:
                        entry += f" ({ref_issue})"
                if ref_pages:
                    entry += f": {ref_pages}"
                entry += "."
            else:
                entry += f" {ref_year}."
            entry += f" (转引自: {cite_p})"

            secondary_items.append(entry)
            ref_num += 1

    if secondary_items:
        lines.append("")
        lines.append("### 二次引用文献")
        lines.append("")
        for entry in secondary_items:
            lines.append(entry)
            lines.append("")

    return "\n".join(lines)


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
    storage_path = build_result_storage_path(path)
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


def format_inline_citation(authors: list, year) -> str:
    """Format inline citation: (Author et al., Year)"""
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


def build_paper_header(paper: dict) -> str:
    """Build paper identification string for prompt."""
    title = paper.get('title', paper.get('filename', '未知'))
    authors = paper.get('authors', [])
    year = _safe_year(paper.get('year'))
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
        year = _safe_year(paper.get('year'))
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

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com", timeout=300.0)

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

        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com", timeout=300.0)

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


@router.post("/synthesis")
async def synthesize_dimensions(
    req: SynthesisDimensionRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
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
    await db.commit()

    async def _stream():
        try:
            client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com", timeout=300.0)
            metadata_block = build_paper_metadata_block(paper_data, bib_refs, members)

            dimension_sections = []
            total = len(dimensions)
            for idx, dim_info in enumerate(dimensions):
                dim_label = dim_info.get("label", f"维度{idx + 1}")

                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = f"正在生成维度 {idx + 1}/{total}：{dim_label}"
                job_cur.progress = 10 + int(80 * idx / total)
                await db.commit()

                dim_prompt = build_synthesis_dimension_prompt(dim_label, paper_data, "subQuestions")
                user_message = metadata_block + "\n\n" + dim_prompt

                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.65,
                    max_tokens=8000,
                )

                content = response.choices[0].message.content or ""
                dimension_sections.append({"label": dim_label, "content": content})

                yield f"event: dimension\ndata: {json.dumps({'label': dim_label, 'content': content, 'index': idx, 'total': total}, ensure_ascii=False)}\n\n"

            section_parts = []
            for sec in dimension_sections:
                section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
            synthesis_body = "\n\n".join(section_parts)

            flat_refs = _collect_flat_secondary_refs(bib_refs, members)
            if flat_refs:
                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = "识别二次引用..."
                job_cur.progress = 90
                await db.commit()
                check_prompt = _build_secondary_ref_check_prompt(synthesis_body, flat_refs)
                user_message = metadata_block + "\n\n" + check_prompt
                ref_check_resp = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                )
                cited_indices = _parse_cited_ref_ids(ref_check_resp.choices[0].message.content or "")
                filtered_refs = _filter_bib_refs_by_indices(bib_refs, members, cited_indices)
            else:
                filtered_refs = bib_refs

            references = build_gbt7714_references(paper_data, filtered_refs, members)
            final_text = synthesis_body + "\n\n" + references

            title_parts = [d.get("label", "") for d in dimensions[:3]]
            if len(dimensions) > 3:
                title_parts.append(f"等{len(dimensions)}个维度")
            title = "AI文献综述：" + "、".join(title_parts)

            first_authors = []
            for p in paper_data:
                a = p.get('authors', [])
                first_authors.append(str(a[0]).split()[-1] if a else "佚名")
            date_str = datetime.now(UTC).strftime("%Y%m%d")
            authors_str = "_".join(first_authors[:3])
            if len(first_authors) > 3:
                authors_str += "等"
            safe_filename = f"综述-{date_str}-{authors_str}.md"

            full_md = build_compare_markdown(title, final_text)

            job_cur = await db.get(Job, job_id)
            job_cur.current_stage = "保存结果..."
            job_cur.progress = 95
            await db.commit()

            storage_path = await persist_synthesis_result(
                db, user, job_id,
                safe_filename,
                full_md,
            )

            job_cur.status = "success"
            job_cur.progress = 100
            job_cur.current_stage = "完成"
            job_cur.finished_at = utcnow_naive()
            await db.commit()

            yield f"event: complete\ndata: {json.dumps({'synthesis': final_text, 'job_id': job_id, 'output_path': storage_path, 'dimension_sections': dimension_sections}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                job_cur = await db.get(Job, job_id)
                if job_cur:
                    job_cur.status = "failed"
                    job_cur.error_msg = str(e)
                    job_cur.finished_at = utcnow_naive()
                    await db.commit()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.post("/synthesis-stream")
async def synthesis_stream(
    req: CompareSynthesisRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    from openai import OpenAI

    if req.mode not in ("long", "quant", "qual"):
        raise HTTPException(status_code=400, detail="mode 必须为 long / quant / qual")

    if not req.selected_dimensions:
        raise HTTPException(status_code=400, detail="请至少选择 1 个维度")

    content_field = "dimensions" if req.mode == "long" else "subQuestions"

    members = await resolve_compare_members(db, user, req.bib_entry_ids, [])
    paper_data = await ensure_paper_data(db, [], members)
    bib_refs = await gather_bib_references(db, members)

    dimensions = req.selected_dimensions
    job_id = await create_compare_job(
        db, user, "synthesis",
        {"dimensions": dimensions, "mode": f"synthesis_{req.mode}"},
        members,
    )
    job = await db.get(Job, job_id)
    job.status = "running"
    job.progress = 10
    job.current_stage = f"准备{'长' if req.mode == 'long' else ''}综述..."
    job.started_at = utcnow_naive()
    await db.commit()

    async def _stream():
        try:
            client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com", timeout=300.0)
            metadata_block = build_paper_metadata_block(paper_data, bib_refs, members)

            dimension_sections = []
            total = len(dimensions)
            for idx, dim_label in enumerate(dimensions):
                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = f"正在生成维度 {idx + 1}/{total}：{dim_label}"
                job_cur.progress = 10 + int(80 * idx / total)
                await db.commit()

                dim_prompt = build_synthesis_dimension_prompt(dim_label, paper_data, content_field)
                user_message = metadata_block + "\n\n" + dim_prompt

                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.65,
                    max_tokens=8000,
                )

                content = response.choices[0].message.content or ""
                dimension_sections.append({"label": dim_label, "content": content})

                yield f"event: dimension\ndata: {json.dumps({'label': dim_label, 'content': content, 'index': idx, 'total': total}, ensure_ascii=False)}\n\n"

            section_parts = []
            for sec in dimension_sections:
                section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
            synthesis_body = "\n\n".join(section_parts)

            flat_refs = _collect_flat_secondary_refs(bib_refs, members)
            if flat_refs:
                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = "识别二次引用..."
                job_cur.progress = 90
                await db.commit()
                check_prompt = _build_secondary_ref_check_prompt(synthesis_body, flat_refs)
                user_message = metadata_block + "\n\n" + check_prompt
                ref_check_resp = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                )
                cited_indices = _parse_cited_ref_ids(ref_check_resp.choices[0].message.content or "")
                filtered_refs = _filter_bib_refs_by_indices(bib_refs, members, cited_indices)
            else:
                filtered_refs = bib_refs

            references = build_gbt7714_references(paper_data, filtered_refs, members)
            final_text = synthesis_body + "\n\n" + references

            dim_labels_joined = "、".join(dimensions[:3])
            if len(dimensions) > 3:
                dim_labels_joined += f"等{len(dimensions)}个维度"
            title = f"AI文献综述：{dim_labels_joined}"

            first_authors = []
            for p in paper_data:
                a = p.get('authors', [])
                first_authors.append(str(a[0]).split()[-1] if a else "佚名")
            date_str = datetime.now(UTC).strftime("%Y%m%d")
            authors_str = "_".join(first_authors[:3])
            if len(first_authors) > 3:
                authors_str += "等"
            safe_filename = f"综述-{date_str}-{authors_str}.md"

            full_md = build_compare_markdown(title, final_text)

            job_cur = await db.get(Job, job_id)
            job_cur.current_stage = "保存结果..."
            job_cur.progress = 95
            await db.commit()

            storage_path = await persist_synthesis_result(
                db, user, job_id,
                safe_filename,
                full_md,
            )

            job_cur.status = "success"
            job_cur.progress = 100
            job_cur.current_stage = "完成"
            job_cur.finished_at = utcnow_naive()
            await db.commit()

            yield f"event: complete\ndata: {json.dumps({'synthesis': final_text, 'job_id': job_id, 'output_path': storage_path, 'dimension_sections': dimension_sections}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                job_cur = await db.get(Job, job_id)
                if job_cur:
                    job_cur.status = "failed"
                    job_cur.error_msg = str(e)
                    job_cur.finished_at = utcnow_naive()
                    await db.commit()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")

@router.post("/synthesis_long")
async def synthesize_long_dimensions(
    req: SynthesisLongRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
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
    await db.commit()

    async def _stream():
        try:
            client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com", timeout=300.0)
            metadata_block = build_paper_metadata_block(paper_data, bib_refs, members)

            dimension_sections = []
            total = len(dimensions)
            for idx, dim_label in enumerate(dimensions):
                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = f"正在生成维度 {idx + 1}/{total}：{dim_label}"
                job_cur.progress = 10 + int(80 * idx / total)
                await db.commit()

                dim_prompt = build_synthesis_dimension_prompt(dim_label, paper_data, "dimensions")
                user_message = metadata_block + "\n\n" + dim_prompt

                response = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    max_tokens=8000,
                )

                content = response.choices[0].message.content or ""
                dimension_sections.append({"label": dim_label, "content": content})

                yield f"event: dimension\ndata: {json.dumps({'label': dim_label, 'content': content, 'index': idx, 'total': total}, ensure_ascii=False)}\n\n"

            section_parts = []
            for sec in dimension_sections:
                section_parts.append(f"## {sec['label']}\n\n{sec['content']}")
            synthesis_body = "\n\n".join(section_parts)

            flat_refs = _collect_flat_secondary_refs(bib_refs, members)
            if flat_refs:
                job_cur = await db.get(Job, job_id)
                job_cur.current_stage = "识别二次引用..."
                job_cur.progress = 90
                await db.commit()
                check_prompt = _build_secondary_ref_check_prompt(synthesis_body, flat_refs)
                user_message = metadata_block + "\n\n" + check_prompt
                ref_check_resp = client.chat.completions.create(
                    model="deepseek-v4-flash",
                    extra_body={"thinking": {"type": "disabled"}},
                    messages=[
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    temperature=0.1,
                    max_tokens=500,
                )
                cited_indices = _parse_cited_ref_ids(ref_check_resp.choices[0].message.content or "")
                filtered_refs = _filter_bib_refs_by_indices(bib_refs, members, cited_indices)
            else:
                filtered_refs = bib_refs

            references = build_gbt7714_references(paper_data, filtered_refs, members)
            final_text = synthesis_body + "\n\n" + references

            dim_labels_joined = "、".join(dimensions[:3])
            if len(dimensions) > 3:
                dim_labels_joined += f"等{len(dimensions)}个维度"
            title = f"AI文献综述：{dim_labels_joined}"

            first_authors = []
            for p in paper_data:
                a = p.get('authors', [])
                first_authors.append(str(a[0]).split()[-1] if a else "佚名")
            date_str = datetime.now(UTC).strftime("%Y%m%d")
            authors_str = "_".join(first_authors[:3])
            if len(first_authors) > 3:
                authors_str += "等"
            safe_filename = f"综述-{date_str}-{authors_str}.md"

            full_md = build_compare_markdown(title, final_text)

            job_cur = await db.get(Job, job_id)
            job_cur.current_stage = "保存结果..."
            job_cur.progress = 95
            await db.commit()

            storage_path = await persist_synthesis_result(
                db, user, job_id,
                safe_filename,
                full_md,
            )

            job_cur.status = "success"
            job_cur.progress = 100
            job_cur.current_stage = "完成"
            job_cur.finished_at = utcnow_naive()
            await db.commit()

            yield f"event: complete\ndata: {json.dumps({'synthesis': final_text, 'job_id': job_id, 'output_path': storage_path, 'dimension_sections': dimension_sections}, ensure_ascii=False)}\n\n"

        except Exception as e:
            try:
                job_cur = await db.get(Job, job_id)
                if job_cur:
                    job_cur.status = "failed"
                    job_cur.error_msg = str(e)
                    job_cur.finished_at = utcnow_naive()
                    await db.commit()
            except Exception:
                pass
            yield f"event: error\ndata: {json.dumps({'detail': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@router.put("/reading-items/{item_id}/edit")
async def save_reading_item_edit(
    item_id: int,
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ri = await db.get(ReadingItem, item_id)
    if not ri or ri.owner_user_id != user.id:
        raise HTTPException(404, "ReadingItem not found")
    content = body.get("edited_content", "")
    existing = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.reading_item_id == item_id,
                ReadingItemEdit.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.edited_content = content
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(ReadingItemEdit(
            reading_item_id=item_id,
            owner_user_id=user.id,
            edited_content=content,
        ))
    await db.commit()
    return {"ok": True}


@router.delete("/reading-items/{item_id}/edit")
async def delete_reading_item_edit(
    item_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ri = await db.get(ReadingItem, item_id)
    if not ri or ri.owner_user_id != user.id:
        raise HTTPException(404, "ReadingItem not found")
    existing = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.reading_item_id == item_id,
                ReadingItemEdit.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"ok": True}


@router.post("/annotations")
async def create_annotation(
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann_id = str(uuid.uuid4())
    db.add(Annotation(
        id=ann_id,
        owner_user_id=user.id,
        source_type=body.get("source_type", "compare_card"),
        source_id=str(body.get("source_id", "")),
        bib_entry_id=body.get("bib_entry_id"),
        selected_text=body.get("selected_text"),
        note=body.get("note", ""),
        char_start=body.get("char_start"),
        char_end=body.get("char_end"),
        is_ai_generated=0,
        color=body.get("color"),
    ))
    await db.commit()
    return {"id": ann_id}


@router.get("/annotations")
async def list_annotations(
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    is_ai: Optional[int] = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Annotation).where(Annotation.owner_user_id == user.id)
    if source_type:
        stmt = stmt.where(Annotation.source_type == source_type)
    if source_id:
        stmt = stmt.where(Annotation.source_id == source_id)
    if is_ai is not None:
        stmt = stmt.where(Annotation.is_ai_generated == is_ai)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": a.id,
            "source_type": a.source_type,
            "source_id": a.source_id,
            "selected_text": a.selected_text,
            "note": a.note,
            "char_start": a.char_start,
            "char_end": a.char_end,
            "is_ai_generated": a.is_ai_generated,
            "color": a.color,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.put("/annotations/{ann_id}")
async def update_annotation(
    ann_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann = await db.get(Annotation, ann_id)
    if not ann or ann.owner_user_id != user.id:
        raise HTTPException(404, "Annotation not found")
    if "note" in body:
        ann.note = body["note"]
    if "color" in body:
        ann.color = body["color"]
    ann.updated_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}


@router.delete("/annotations/{ann_id}")
async def delete_annotation(
    ann_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann = await db.get(Annotation, ann_id)
    if not ann or ann.owner_user_id != user.id:
        raise HTTPException(404, "Annotation not found")
    await db.delete(ann)
    await db.commit()
    return {"ok": True}


@router.post("/ai-summary")
async def ai_summary(
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    text = body.get("text", "")
    api_key = body.get("api_key", "")
    reading_item_id = body.get("reading_item_id")

    if not text.strip() or not api_key:
        raise HTTPException(400, "text and api_key required")

    validate_deepseek_key(api_key)

    from prompt_service import get_prompt_payload
    payload = await get_prompt_payload(
        db, prompt_type="compare", prompt_key="ai_summary", user_id=user.id
    )
    prompt_text = payload.effective_content.replace("{selected_text}", text)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=120.0)
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        extra_body={"thinking": {"type": "disabled"}},
        messages=[
            {"role": "system", "content": "你是一位学术文本总结助手。"},
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    summary = response.choices[0].message.content.strip()

    ann_id = str(uuid.uuid4())
    db.add(Annotation(
        id=ann_id,
        owner_user_id=user.id,
        source_type="ai_summary",
        source_id=str(reading_item_id) if reading_item_id else "",
        bib_entry_id=body.get("bib_entry_id"),
        selected_text=text,
        note=summary,
        char_start=body.get("char_start"),
        char_end=body.get("char_end"),
        is_ai_generated=1,
    ))
    await db.commit()

    return {"summary": summary, "annotation_id": ann_id}
