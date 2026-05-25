from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import Artifact, BibEntry, Job, JobBibEntry, RefFormatPreset, User
from result_storage import build_result_storage_path, get_results_root
from routers.upload import compute_expires_at, utcnow_naive
from services.card_notes import json_list
from services.ref_format_service import (
    BibEntryForFormat,
    analyze_reference_format_from_file,
    analyze_reference_format_from_text,
    generate_formatted_references,
)

router = APIRouter()


class RefFormatAnalyzeResponse(BaseModel):
    format_name: str
    format_rules: str
    raw_references_count: int
    raw_references_sample: list[str]
    source_text_truncated: str


class RefFormatGenerateRequest(BaseModel):
    format_rules: str
    format_name: Optional[str] = None
    entry_ids: list[str] = Field(min_length=1)
    api_key: str
    save_preset: bool = False
    preset_name: Optional[str] = None
    source_text: Optional[str] = None
    raw_references_count: int = 0


class RefFormatGenerateResponse(BaseModel):
    result_text: str
    entry_count: int
    artifact_id: int
    preset_id: Optional[int]
    storage_path: str


class RefFormatPresetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    format_name: Optional[str]
    format_rules: str
    source_text: Optional[str]
    entry_count: int
    created_at: Optional[str]
    updated_at: Optional[str]


class RefFormatPresetCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    description: Optional[str] = None
    format_rules: str = Field(min_length=1)
    format_name: Optional[str] = None
    source_text: Optional[str] = None
    entry_count: int = 0


class RefFormatPresetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None


def _dt(value) -> Optional[str]:
    return value.isoformat() if value else None


def _preset_response(item: RefFormatPreset) -> RefFormatPresetResponse:
    return RefFormatPresetResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        format_name=item.detected_format_name,
        format_rules=item.format_rules,
        source_text=item.source_text,
        entry_count=item.entry_count,
        created_at=_dt(item.created_at),
        updated_at=_dt(item.updated_at),
    )


@router.get("/presets", response_model=list[RefFormatPresetResponse])
async def list_presets(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[RefFormatPresetResponse]:
    rows = (
        await db.execute(
            select(RefFormatPreset)
            .where(RefFormatPreset.owner_user_id == user.id)
            .order_by(RefFormatPreset.updated_at.desc(), RefFormatPreset.id.desc())
        )
    ).scalars().all()
    return [_preset_response(item) for item in rows]


@router.post("/presets", response_model=RefFormatPresetResponse)
async def create_preset(
    body: RefFormatPresetCreateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RefFormatPresetResponse:
    item = RefFormatPreset(
        owner_user_id=user.id,
        name=body.name.strip(),
        description=body.description,
        source_text=body.source_text,
        format_rules=body.format_rules,
        detected_format_name=body.format_name,
        entry_count=max(0, body.entry_count),
    )
    db.add(item)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="预设名称已存在，请换一个名称。") from exc
    await db.refresh(item)
    return _preset_response(item)


@router.put("/presets/{preset_id}", response_model=RefFormatPresetResponse)
async def update_preset(
    preset_id: int,
    body: RefFormatPresetUpdateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RefFormatPresetResponse:
    item = await db.get(RefFormatPreset, preset_id)
    if item is None or item.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预设不存在。")
    if body.name is not None:
        item.name = body.name.strip()
    if body.description is not None:
        item.description = body.description
    item.updated_at = utcnow_naive()
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="预设名称已存在，请换一个名称。") from exc
    await db.refresh(item)
    return _preset_response(item)


@router.delete("/presets/{preset_id}")
async def delete_preset(
    preset_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    item = await db.get(RefFormatPreset, preset_id)
    if item is None or item.owner_user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="预设不存在。")
    await db.delete(item)
    await db.commit()
    return {"ok": True}


@router.post("/analyze", response_model=RefFormatAnalyzeResponse)
async def analyze_format(
    source: str = Form(...),
    api_key: str = Form(...),
    text: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    user: User = Depends(current_user),
) -> RefFormatAnalyzeResponse:
    del user
    try:
        if source == "paste":
            if not text:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请粘贴参考文献文本。")
            result = analyze_reference_format_from_text(text, api_key=api_key)
        elif source == "upload":
            if file is None:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="请上传示例文件。")
            suffix = Path(file.filename or "").suffix.lower()
            if suffix not in {".pdf", ".md", ".markdown", ".txt"}:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="仅支持 PDF、Markdown 或 TXT 文件。")
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await file.read())
                temp_path = tmp.name
            try:
                if suffix == ".txt":
                    result = analyze_reference_format_from_text(Path(temp_path).read_text(encoding="utf-8"), api_key=api_key)
                else:
                    result = analyze_reference_format_from_file(temp_path, api_key=api_key)
            finally:
                Path(temp_path).unlink(missing_ok=True)
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="source 必须是 upload 或 paste。")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return RefFormatAnalyzeResponse(**result)


async def _load_entries(db: AsyncSession, user: User, ids: list[str]) -> list[BibEntryForFormat]:
    rows = (
        await db.execute(
            select(BibEntry).where(BibEntry.owner_user_id == user.id, BibEntry.id.in_(ids))
        )
    ).scalars().all()
    by_id = {item.id: item for item in rows}
    missing = [item for item in ids if item not in by_id]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="部分文献不存在或无权限访问。")
    result: list[BibEntryForFormat] = []
    for item_id in ids:
        item = by_id[item_id]
        result.append(
            BibEntryForFormat(
                id=item.id,
                title=item.title,
                authors=json_list(item.authors_json),
                year=item.year,
                journal=item.journal,
                volume=item.volume,
                issue=item.issue,
                pages=item.pages,
                doi=item.doi,
                language=item.language,
            )
        )
    return result


@router.post("/generate", response_model=RefFormatGenerateResponse)
async def generate_reference_list(
    body: RefFormatGenerateRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> RefFormatGenerateResponse:
    if body.save_preset and not (body.preset_name or "").strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="保存预设时必须填写预设名称。")
    entries = await _load_entries(db, user, body.entry_ids)
    try:
        result_text = generate_formatted_references(
            entries,
            format_rules=body.format_rules,
            format_name=body.format_name,
            api_key=body.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    task_id = str(uuid.uuid4())
    job = Job(
        id=task_id,
        owner_user_id=user.id,
        job_type="ref_format",
        status="success",
        params_json=json.dumps({"entry_ids": body.entry_ids, "format_name": body.format_name}, ensure_ascii=False),
        progress=100,
        current_stage="参考文献目录已生成",
        started_at=utcnow_naive(),
        finished_at=utcnow_naive(),
        expires_at=compute_expires_at(user),
    )
    db.add(job)
    for index, entry_id in enumerate(body.entry_ids):
        db.add(JobBibEntry(job_id=task_id, bib_entry_id=entry_id, role="target", sort_order=index))

    result_dir = get_results_root() / str(user.id) / task_id
    result_dir.mkdir(parents=True, exist_ok=True)
    filename = "reference-format.md"
    path = result_dir / filename
    markdown = f"# 参考文献目录\n\n{result_text}\n"
    path.write_text(markdown, encoding="utf-8")
    artifact = Artifact(
        job_id=task_id,
        owner_user_id=user.id,
        artifact_type="ref_format_md",
        filename=filename,
        storage_path=build_result_storage_path(path),
        size_bytes=path.stat().st_size,
        sort_order=0,
        expires_at=compute_expires_at(user),
    )
    db.add(artifact)

    preset_id = None
    if body.save_preset:
        preset = RefFormatPreset(
            owner_user_id=user.id,
            name=(body.preset_name or "").strip(),
            source_text=body.source_text,
            format_rules=body.format_rules,
            detected_format_name=body.format_name,
            entry_count=max(0, body.raw_references_count),
        )
        db.add(preset)
        try:
            await db.flush()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="预设名称已存在，请换一个名称。") from exc
        preset_id = preset.id

    await db.commit()
    await db.refresh(artifact)
    return RefFormatGenerateResponse(
        result_text=result_text,
        entry_count=len(entries),
        artifact_id=artifact.id,
        preset_id=preset_id,
        storage_path=artifact.storage_path,
    )
