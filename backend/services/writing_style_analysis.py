"""Source-backed writing-style analysis workflow for library entries."""
from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.utils.api_key import validate_deepseek_key
from backend.utils.llm_provider import create_openai_client, model_for_api_key
from db.models import Artifact, BibEntry, File, Job, JobBibEntry
from prompt_service import get_effective_prompt_text
from result_storage import build_result_storage_path, get_results_root
from routers.upload import utcnow_naive
from services.card_notes import json_list
from services.writing_style_retrieval import extract_style_sections
from upload_storage import resolve_storage_path

MAX_SELECTED_PAPERS = 5
MAX_SECTIONS_PER_PAPER = 12
MAX_SECTION_CHARS = 2400
MISSING_MARKDOWN_MESSAGE = "请先使用 PaddleOCR 将 PDF 转换为 Markdown，并把 Markdown 原文挂载/绑定到这篇文献后再分析。"

LlmCall = Callable[[str, str], str]


class MissingMarkdownSourceError(ValueError):
    def __init__(self, skipped: list[dict[str, Any]]):
        super().__init__("没有可分析的 Markdown 原文。")
        self.skipped = skipped


def _entry_meta(entry: BibEntry) -> dict[str, Any]:
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "authors": json_list(entry.authors_json),
        "year": entry.year,
        "journal": entry.journal,
    }


def _skipped(entry: BibEntry, reason: str, message: str = MISSING_MARKDOWN_MESSAGE) -> dict[str, Any]:
    return {"entry_id": entry.id, "title": entry.title, "reason": reason, "message": message}


async def _load_entries(db: AsyncSession, owner_user_id: int, entry_ids: list[str]) -> list[BibEntry]:
    clean_ids = []
    seen = set()
    for item in entry_ids:
        entry_id = str(item).strip()
        if entry_id and entry_id not in seen:
            clean_ids.append(entry_id)
            seen.add(entry_id)
    if not clean_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请选择至少一篇文献。")
    if len(clean_ids) > MAX_SELECTED_PAPERS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"一次最多分析 {MAX_SELECTED_PAPERS} 篇文献。")

    rows = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == owner_user_id, BibEntry.id.in_(clean_ids))
        )
    ).scalars().all()
    by_id = {entry.id: entry for entry in rows}
    missing = [entry_id for entry_id in clean_ids if entry_id not in by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分文献不存在或无权限访问。")
    return [by_id[entry_id] for entry_id in clean_ids]


async def _load_markdown_source(db: AsyncSession, owner_user_id: int, entry: BibEntry) -> tuple[File | None, str | None, str | None]:
    file_id = entry.markdown_source_file_id or entry.source_file_id
    file_record = await db.get(File, file_id) if file_id else None
    if file_record is None or file_record.owner_user_id != owner_user_id:
        return None, None, "missing_markdown_source"
    if file_record.file_type != "markdown":
        return file_record, None, "missing_markdown_source"
    path = resolve_storage_path(file_record.storage_path)
    if not path.exists() or not path.is_file():
        return file_record, None, "missing_markdown_file"
    return file_record, path.read_text(encoding="utf-8", errors="ignore"), None


def _section_payload(paper: dict[str, Any]) -> str:
    payload = {
        "metadata": paper["metadata"],
        "file": paper.get("file"),
        "source_mode": paper.get("source_mode", "sampled_sections"),
    }
    if paper.get("source_mode") == "full_markdown":
        payload["full_markdown"] = paper.get("full_markdown", "")
    else:
        payload["sections"] = paper.get("sections", [])
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _paper_for_downstream(paper: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "metadata": paper["metadata"],
        "file": paper.get("file"),
        "source_mode": paper.get("source_mode", "sampled_sections"),
    }
    if paper.get("source_mode") == "full_markdown":
        payload["source_note"] = "单篇论文使用完整 Markdown 原文作为写作风格分析上下文。"
    else:
        payload["sections"] = paper.get("sections", [])
    return payload


def _default_llm_call(api_key: str) -> LlmCall:
    checked_key = validate_deepseek_key(api_key)
    client = create_openai_client(
        checked_key,
        timeout=httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0),
    )
    model = model_for_api_key(checked_key, "deepseek-v4-flash")

    def call(prompt: str, payload: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        return (response.choices[0].message.content or "").strip()

    return call


async def _prompt(db: AsyncSession, owner_user_id: int, key: str) -> str:
    return await get_effective_prompt_text(
        db,
        user_id=owner_user_id,
        prompt_type="writing_style",
        prompt_key=key,
    )


def _safe_model_text(value: str) -> str:
    text = (value or "").strip()
    return text or "模型未返回有效内容。"


def _build_report_markdown(
    *,
    papers: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    section_analyses: list[str],
    imitation_advice: str,
    comparative: str | None,
    report_body: str,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "---",
        "type: writing_style_analysis",
        f"generated_at: {now}",
        f"entry_count: {len(papers)}",
        "source_requirement: markdown_original_only",
        "---",
        "",
        "# 写作风格分析报告",
        "",
        "## 分析范围",
    ]
    for paper in papers:
        meta = paper["metadata"]
        authors = ", ".join(meta.get("authors") or []) or "作者待补充"
        year = meta.get("year") or "年份待补充"
        lines.append(f"- {meta.get('title') or '未命名文献'}（{authors}, {year}）")

    sampled_papers = [paper for paper in papers if paper.get("source_mode") != "full_markdown"]
    if sampled_papers:
        lines.extend(["", "## 原文证据概览"])
        for paper in sampled_papers:
            lines.append(f"### {paper['metadata']['title']}")
            for section in paper.get("sections", []):
                heading = section.get("heading_path") or "未命名片段"
                quote = section.get("quote") or ""
                lines.append(f"- **{heading}**：{quote[:240]}")

    lines.extend(["", "## 单篇论文写作风格"])
    for paper, analysis in zip(papers, section_analyses):
        lines.extend(["", f"### {paper['metadata']['title']}", _safe_model_text(analysis)])

    if comparative:
        lines.extend(["", "## 多篇论文对比", _safe_model_text(comparative)])

    lines.extend(["", "## 写作建议", _safe_model_text(imitation_advice)])
    lines.extend(["", "## 报告整理", _safe_model_text(report_body)])

    if skipped:
        lines.extend(["", "## 未分析论文"])
        for item in skipped:
            lines.append(f"- {item['title']}：{item['message']}")

    return "\n".join(lines).rstrip() + "\n"


async def analyze_library_writing_style(
    db: AsyncSession,
    *,
    owner_user_id: int,
    entry_ids: list[str],
    api_key: str,
    analysis_mode: str = "auto",
    llm_call: LlmCall | None = None,
    expires_at=None,
) -> dict[str, Any]:
    entries = await _load_entries(db, owner_user_id, entry_ids)
    papers: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    markdown_sources: list[tuple[BibEntry, File | None, str]] = []
    for entry in entries:
        file_record, markdown, reason = await _load_markdown_source(db, owner_user_id, entry)
        if markdown is None:
            skipped.append(_skipped(entry, reason or "missing_markdown_source"))
            continue
        if not markdown.strip():
            skipped.append(_skipped(entry, "empty_markdown_source", "Markdown 原文没有可用正文片段，请检查挂载文件内容。"))
            continue
        markdown_sources.append((entry, file_record, markdown))

    use_full_markdown = len(markdown_sources) == 1
    for entry, file_record, markdown in markdown_sources:
        base_paper = {
            "metadata": _entry_meta(entry),
            "file": {"file_id": file_record.id if file_record else None, "file_name": file_record.original_name if file_record else None},
        }
        if use_full_markdown:
            papers.append({**base_paper, "source_mode": "full_markdown", "full_markdown": markdown})
            continue

        sections = extract_style_sections(markdown, "general", MAX_SECTIONS_PER_PAPER)
        for section in sections:
            section["quote"] = str(section.get("quote") or "")[:MAX_SECTION_CHARS]
        if not sections:
            skipped.append(_skipped(entry, "empty_markdown_source", "Markdown 原文没有可用正文片段，请检查挂载文件内容。"))
            continue
        papers.append({**base_paper, "source_mode": "sampled_sections", "sections": sections})

    if not papers:
        raise MissingMarkdownSourceError(skipped)

    caller = llm_call or _default_llm_call(api_key)
    use_single_prompt_set = len(papers) == 1 and papers[0].get("source_mode") == "full_markdown"
    if use_single_prompt_set:
        prompts = {
            "analyzer": await _prompt(db, owner_user_id, "single_fulltext_analyzer"),
            "imitation_advisor": await _prompt(db, owner_user_id, "single_imitation_advisor"),
            "report_writer": await _prompt(db, owner_user_id, "single_report_writer"),
        }
    else:
        prompts = {
            "analyzer": await _prompt(db, owner_user_id, "batch_section_analyzer"),
            "imitation_advisor": await _prompt(db, owner_user_id, "batch_imitation_advisor"),
            "comparative_synthesizer": await _prompt(db, owner_user_id, "batch_comparative_synthesizer"),
            "report_writer": await _prompt(db, owner_user_id, "batch_report_writer"),
        }

    now = utcnow_naive()
    job_id = str(uuid.uuid4())
    job = Job(
        id=job_id,
        owner_user_id=owner_user_id,
        job_type="writing_style",
        status="running",
        params_json=json.dumps({"entry_ids": entry_ids, "analysis_mode": analysis_mode}, ensure_ascii=False),
        progress=20,
        current_stage="分析写作风格",
        created_at=now,
        started_at=now,
        expires_at=expires_at,
    )
    db.add(job)
    for index, paper in enumerate(papers):
        db.add(JobBibEntry(job_id=job_id, bib_entry_id=paper["metadata"]["entry_id"], role="target", sort_order=index))
    await db.flush()

    try:
        section_analyses = [
            caller(prompts["analyzer"], _section_payload(paper))
            for paper in papers
        ]
        downstream_papers = [_paper_for_downstream(paper) for paper in papers]
        advice_payload = json.dumps({"papers": downstream_papers, "section_analyses": section_analyses}, ensure_ascii=False, indent=2)
        imitation_advice = caller(prompts["imitation_advisor"], advice_payload)
        comparative = None
        if not use_single_prompt_set and len(papers) > 1:
            comparative = caller(prompts["comparative_synthesizer"], advice_payload)
        report_payload = json.dumps(
            {
                "papers": downstream_papers,
                "section_analyses": section_analyses,
                "imitation_advice": imitation_advice,
                "comparative": comparative,
                "skipped": skipped,
            },
            ensure_ascii=False,
            indent=2,
        )
        report_body = caller(prompts["report_writer"], report_payload)

        markdown = _build_report_markdown(
            papers=papers,
            skipped=skipped,
            section_analyses=section_analyses,
            imitation_advice=imitation_advice,
            comparative=comparative,
            report_body=report_body,
        )
        result_dir = get_results_root() / str(owner_user_id) / job_id
        result_dir.mkdir(parents=True, exist_ok=True)
        filename = f"writing_style_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        path = result_dir / filename
        path.write_text(markdown, encoding="utf-8")

        artifact = Artifact(
            job_id=job_id,
            owner_user_id=owner_user_id,
            artifact_type="writing_style_md",
            filename=filename,
            storage_path=build_result_storage_path(path),
            size_bytes=path.stat().st_size,
            sort_order=0,
            expires_at=expires_at,
        )
        db.add(artifact)
        job.status = "success"
        job.progress = 100
        job.current_stage = "保存到历史记录"
        job.finished_at = utcnow_naive()
        await db.commit()
        await db.refresh(artifact)
        return {
            "job_id": job_id,
            "artifact_id": artifact.id,
            "filename": filename,
            "analyzed_count": len(papers),
            "skipped": skipped,
        }
    except Exception as exc:
        job.status = "failed"
        job.error_msg = str(exc)
        job.current_stage = "写作风格分析失败"
        job.finished_at = utcnow_naive()
        await db.commit()
        raise
