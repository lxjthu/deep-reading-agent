from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user
from db import get_db
from db.models import DimensionItem, DimensionSet, DimensionTemplate, ReadingItem, TemplateItem, User
from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS
from prompt_registry import load_prompt_from_file

router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _activate_dimension_set(
    db: AsyncSession, user_id: int, dimension_set: DimensionSet
) -> None:
    await db.execute(
        update(DimensionSet)
        .where(
            DimensionSet.owner_user_id == user_id,
            DimensionSet.id != dimension_set.id,
        )
        .values(is_default=0)
    )
    dimension_set.is_default = 1
    dimension_set.updated_at = _utcnow()


async def _get_user_set(db: AsyncSession, set_id: int, user_id: int) -> DimensionSet:
    ds = (
        await db.execute(
            select(DimensionSet).where(
                DimensionSet.id == set_id,
                DimensionSet.owner_user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="维度集合不存在")
    return ds


async def _get_user_item(
    db: AsyncSession, set_id: int, item_id: int, user_id: int
) -> tuple[DimensionSet, DimensionItem]:
    ds = await _get_user_set(db, set_id, user_id)
    item = (
        await db.execute(
            select(DimensionItem).where(
                DimensionItem.id == item_id,
                DimensionItem.set_id == set_id,
            )
        )
    ).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="维度条目不存在")
    return ds, item


# ---------------------------------------------------------------------------
# Dimension Set CRUD
# ---------------------------------------------------------------------------


class SetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    clone_from_set_id: Optional[int] = None
    is_available_for_reading: Optional[bool] = True


class SetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class SetAvailabilityUpdate(BaseModel):
    is_available_for_reading: bool


@router.get("/sets")
async def list_sets(
    available_only: bool = False,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(DimensionSet).where(DimensionSet.owner_user_id == user.id)
    if available_only:
        stmt = stmt.where(DimensionSet.is_available_for_reading == 1)
    rows = (
        await db.execute(stmt.order_by(DimensionSet.sort_order, DimensionSet.id))
    ).scalars().all()
    result = []
    for ds in rows:
        count = (
            await db.execute(
                select(func.count()).select_from(DimensionItem).where(
                    DimensionItem.set_id == ds.id
                )
            )
        ).scalar() or 0
        result.append(
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "is_default": bool(ds.is_default),
                "is_system": bool(ds.is_system),
                "is_shared": bool(ds.is_shared),
                "is_available_for_reading": bool(ds.is_available_for_reading),
                "item_count": count,
                "sort_order": ds.sort_order,
            }
        )
    return result


@router.post("/sets", status_code=status.HTTP_201_CREATED)
async def create_set(
    body: SetCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    dup = (
        await db.execute(
            select(DimensionSet).where(
                DimensionSet.owner_user_id == user.id,
                DimensionSet.name == body.name,
            )
        )
    ).scalar_one_or_none()
    if dup:
        raise HTTPException(status_code=409, detail="同名集合已存在")

    max_order = (
        await db.execute(
            select(func.coalesce(func.max(DimensionSet.sort_order), -1)).where(
                DimensionSet.owner_user_id == user.id
            )
        )
    ).scalar()

    ds = DimensionSet(
        owner_user_id=user.id,
        name=body.name,
        description=body.description,
        is_default=0,
        is_system=0,
        is_available_for_reading=1 if body.is_available_for_reading is not False else 0,
        sort_order=max_order + 1,
    )
    db.add(ds)
    await db.flush()

    if body.clone_from_set_id is not None:
        source_items = (
            await db.execute(
                select(DimensionItem)
                .where(DimensionItem.set_id == body.clone_from_set_id)
                .order_by(DimensionItem.sort_order)
            )
        ).scalars().all()
        for src in source_items:
            db.add(
                DimensionItem(
                    set_id=ds.id,
                    dim_key=src.dim_key,
                    dim_name=src.dim_name,
                    description=src.description,
                    prompt_content=src.prompt_content,
                    default_question=src.default_question,
                    sort_order=src.sort_order,
                    group_name=src.group_name,
                    is_builtin=0,
                )
            )

    await db.commit()
    await db.refresh(ds)
    return {"id": ds.id, "name": ds.name}


@router.put("/sets/{set_id}")
async def update_set(
    set_id: int,
    body: SetUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if ds.is_system and body.name is not None:
        raise HTTPException(status_code=400, detail="系统集合不可改名")
    if body.name is not None:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == body.name,
                    DimensionSet.id != set_id,
                )
            )
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="同名集合已存在")
        ds.name = body.name
    if body.description is not None:
        ds.description = body.description
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


@router.patch("/sets/{set_id}/reading-availability")
async def update_reading_availability(
    set_id: int,
    body: SetAvailabilityUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if ds.is_system and not body.is_available_for_reading:
        raise HTTPException(status_code=400, detail="系统默认集合不可移出长文本精读")
    ds.is_available_for_reading = 1 if body.is_available_for_reading else 0
    if not body.is_available_for_reading and ds.is_default:
        ds.is_default = 0
    ds.updated_at = _utcnow()
    await db.commit()
    return {
        "id": ds.id,
        "is_available_for_reading": bool(ds.is_available_for_reading),
        "is_default": bool(ds.is_default),
    }


@router.delete("/sets/{set_id}")
async def delete_set(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if ds.is_system:
        raise HTTPException(status_code=400, detail="系统集合不可删除")
    # 检查是否有使用此维度集合精读过文献
    from db.models import Job
    used_jobs = await db.execute(
        select(func.count()).select_from(Job).where(
            Job.owner_user_id == user.id,
            Job.job_type == "reading_long",
            Job.params_json.like(f'%"dimension_set_id": {set_id}%'),
        )
    )
    used_count = used_jobs.scalar() or 0
    if used_count > 0:
        raise HTTPException(
            status_code=409,
            detail=f"该维度集合已有 {used_count} 条精读记录，无法删除",
        )
    await db.execute(delete(DimensionSet).where(DimensionSet.id == set_id))
    await db.commit()
    return {"success": True}


@router.patch("/sets/{set_id}/share")
async def toggle_share(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if ds.is_system:
        raise HTTPException(status_code=400, detail="系统集合不可共享")
    new_val = 0 if ds.is_shared else 1
    await db.execute(
        update(DimensionSet)
        .where(DimensionSet.id == set_id)
        .values(is_shared=new_val)
    )
    await db.commit()
    return {"id": set_id, "is_shared": bool(new_val)}


@router.get("/shared")
async def list_shared(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DimensionSet)
            .where(
                DimensionSet.is_shared == 1,
                DimensionSet.owner_user_id != user.id,
            )
            .order_by(DimensionSet.created_at.desc())
        )
    ).scalars().all()
    result = []
    for ds in rows:
        count = (
            await db.execute(
                select(func.count()).select_from(DimensionItem).where(
                    DimensionItem.set_id == ds.id
                )
            )
        ).scalar() or 0
        owner_name = ds.owner.username if ds.owner else "未知"
        result.append(
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "item_count": count,
                "owner_name": owner_name,
            }
        )
    return result


@router.post("/shared/{set_id}/import", status_code=status.HTTP_201_CREATED)
async def import_shared(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = (
        await db.execute(
            select(DimensionSet).where(
                DimensionSet.id == set_id,
                DimensionSet.is_shared == 1,
            )
        )
    ).scalar_one_or_none()
    if ds is None:
        raise HTTPException(status_code=404, detail="共享集合不存在")

    new_name = ds.name
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{ds.name} ({suffix})"

    max_order = (
        await db.execute(
            select(func.coalesce(func.max(DimensionSet.sort_order), -1)).where(
                DimensionSet.owner_user_id == user.id
            )
        )
    ).scalar()

    new_ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=ds.description,
        is_default=0,
        is_system=0,
        is_shared=0,
        is_available_for_reading=1,
        sort_order=max_order + 1,
    )
    db.add(new_ds)
    await db.flush()

    items = (
        await db.execute(
            select(DimensionItem)
            .where(DimensionItem.set_id == set_id)
            .order_by(DimensionItem.sort_order)
        )
    ).scalars().all()
    for item in items:
        db.add(
            DimensionItem(
                set_id=new_ds.id,
                dim_key=item.dim_key,
                dim_name=item.dim_name,
                description=item.description,
                prompt_content=item.prompt_content,
                default_question=item.default_question,
                sort_order=item.sort_order,
                group_name=item.group_name,
                is_builtin=0,
            )
        )
    await db.commit()
    return {"id": new_ds.id, "name": new_ds.name}


@router.post("/sets/{set_id}/activate")
async def activate_set(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if not ds.is_available_for_reading:
        ds.is_available_for_reading = 1
    await db.execute(
        update(DimensionSet)
        .where(DimensionSet.owner_user_id == user.id)
        .values(is_default=0)
    )
    ds.is_default = 1
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


@router.post("/sets/{set_id}/reset")
async def reset_set(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    if not ds.is_system:
        raise HTTPException(status_code=400, detail="仅系统集合可恢复默认")
    await db.execute(delete(DimensionItem).where(DimensionItem.set_id == set_id))
    await db.flush()
    for idx, (key, dim) in enumerate(ANALYSIS_DIMENSIONS.items()):
        prompt = load_prompt_from_file("long", key) or dim["system_prompt_addition"]
        db.add(
            DimensionItem(
                set_id=set_id,
                dim_key=key,
                dim_name=dim["name"],
                description=dim["description"],
                prompt_content=prompt,
                default_question=dim["default_questions"][0] if dim["default_questions"] else "",
                sort_order=idx,
                is_builtin=1 if key != "custom" else 0,
            )
        )
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


@router.post("/sets/{set_id}/clone", status_code=status.HTTP_201_CREATED)
async def clone_set(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    new_name = f"{ds.name} (副本)"
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{ds.name} (副本{suffix})"

    max_order = (
        await db.execute(
            select(func.coalesce(func.max(DimensionSet.sort_order), -1)).where(
                DimensionSet.owner_user_id == user.id
            )
        )
    ).scalar()

    new_ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=ds.description,
        is_default=0,
        is_system=0,
        is_available_for_reading=0,
        sort_order=max_order + 1,
    )
    db.add(new_ds)
    await db.flush()

    items = (
        await db.execute(
            select(DimensionItem)
            .where(DimensionItem.set_id == set_id)
            .order_by(DimensionItem.sort_order)
        )
    ).scalars().all()
    for item in items:
        db.add(
            DimensionItem(
                set_id=new_ds.id,
                dim_key=item.dim_key,
                dim_name=item.dim_name,
                description=item.description,
                prompt_content=item.prompt_content,
                default_question=item.default_question,
                sort_order=item.sort_order,
                group_name=item.group_name,
                is_builtin=0,
            )
        )
    await db.commit()
    return {"id": new_ds.id, "name": new_ds.name}


# ---------------------------------------------------------------------------
# Dimension Item CRUD
# ---------------------------------------------------------------------------


class ItemCreate(BaseModel):
    dim_name: str
    description: Optional[str] = None
    prompt_content: str = ""
    default_question: str = ""


class ItemUpdate(BaseModel):
    dim_name: Optional[str] = None
    description: Optional[str] = None
    prompt_content: Optional[str] = None
    default_question: Optional[str] = None


class ItemsReorder(BaseModel):
    orders: list[dict]


@router.get("/sets/{set_id}/items")
async def list_items(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_user_set(db, set_id, user.id)
    items = (
        await db.execute(
            select(DimensionItem)
            .where(DimensionItem.set_id == set_id)
            .order_by(DimensionItem.sort_order, DimensionItem.id)
        )
    ).scalars().all()
    return [
        {
            "id": it.id,
            "dim_key": it.dim_key,
            "dim_name": it.dim_name,
            "description": it.description,
            "prompt_content": it.prompt_content,
            "default_question": it.default_question,
            "sort_order": it.sort_order,
            "is_builtin": bool(it.is_builtin),
            "group_name": it.group_name,
        }
        for it in items
    ]


@router.post("/sets/{set_id}/items", status_code=status.HTTP_201_CREATED)
async def create_item(
    set_id: int,
    body: ItemCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    # dim_key 格式：维度集合-维度（如"计量论文专用-研究问题"）
    set_name_clean = re.sub(r"[^\w\s-]", "", ds.name).strip()
    dim_name_clean = re.sub(r"[^\w\s-]", "", body.dim_name).strip()
    base_key = f"{set_name_clean}-{dim_name_clean}"
    # 处理同一集合内可能的重名
    dim_key = base_key
    suffix = 1
    while True:
        existing = (
            await db.execute(
                select(DimensionItem).where(
                    DimensionItem.set_id == set_id,
                    DimensionItem.dim_key == dim_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            break
        dim_key = f"{base_key}-{suffix}"
        suffix += 1

    max_order = (
        await db.execute(
            select(func.coalesce(func.max(DimensionItem.sort_order), -1)).where(
                DimensionItem.set_id == set_id
            )
        )
    ).scalar()

    item = DimensionItem(
        set_id=set_id,
        dim_key=dim_key,
        dim_name=body.dim_name,
        description=body.description,
        prompt_content=body.prompt_content,
        default_question=body.default_question,
        sort_order=max_order + 1,
        is_builtin=0,
    )
    db.add(item)
    ds.updated_at = _utcnow()
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "dim_key": item.dim_key, "dim_name": item.dim_name}


@router.put("/sets/{set_id}/items/{item_id}")
async def update_item(
    set_id: int,
    item_id: int,
    body: ItemUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds, item = await _get_user_item(db, set_id, item_id, user.id)
    if body.dim_name is not None:
        item.dim_name = body.dim_name
    if body.description is not None:
        item.description = body.description
    if body.prompt_content is not None:
        item.prompt_content = body.prompt_content
    if body.default_question is not None:
        item.default_question = body.default_question
    item.updated_at = _utcnow()
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


@router.delete("/sets/{set_id}/items/{item_id}")
async def delete_item(
    set_id: int,
    item_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds, item = await _get_user_item(db, set_id, item_id, user.id)
    if ds.is_system and item.is_builtin:
        raise HTTPException(status_code=400, detail="系统集合中的内置维度不可删除，请使用恢复默认功能")
    used_count = (await db.execute(
        select(func.count()).select_from(ReadingItem).where(
            ReadingItem.owner_user_id == user.id,
            ReadingItem.mode == "long",
            ReadingItem.item_label == item.dim_name,
        )
    )).scalar() or 0
    if used_count > 0:
        raise HTTPException(status_code=409, detail=f"维度「{item.dim_name}」已有 {used_count} 条精读记录，无法删除")
    await db.execute(delete(DimensionItem).where(DimensionItem.id == item_id))
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


@router.post("/sets/{set_id}/items/reorder")
async def reorder_items(
    set_id: int,
    body: ItemsReorder,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
    for entry in body.orders:
        item_id = entry.get("id")
        sort_order = entry.get("sort_order")
        if item_id is None or sort_order is None:
            continue
        await db.execute(
            update(DimensionItem)
            .where(DimensionItem.id == item_id, DimensionItem.set_id == set_id)
            .values(sort_order=sort_order)
        )
    ds.updated_at = _utcnow()
    await db.commit()
    return {"success": True}


# --------------------------------------------------------------------------
# Template market endpoints
# --------------------------------------------------------------------------

import json


@router.get("/templates")
async def list_templates(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """获取预置模板列表"""
    query = select(DimensionTemplate).where(DimensionTemplate.is_featured == 1)
    if category:
        query = query.where(DimensionTemplate.category == category)
    query = query.order_by(DimensionTemplate.sort_order, DimensionTemplate.id)

    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "dim_count": t.dim_count,
            "preview": json.loads(t.preview_json) if t.preview_json else None,
        }
        for t in rows
    ]


@router.get("/templates/{template_id}")
async def get_template_detail(
    template_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取模板详情（含维度列表）"""
    template = (
        await db.execute(
            select(DimensionTemplate).where(DimensionTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    items = (
        await db.execute(
            select(TemplateItem)
            .where(TemplateItem.template_id == template_id)
            .order_by(TemplateItem.sort_order)
        )
    ).scalars().all()

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "dim_count": template.dim_count,
        "group_config": json.loads(template.group_config) if template.group_config else None,
        "dimensions": [
            {
                "id": item.id,
                "dim_key": item.dim_key,
                "dim_name": item.dim_name,
                "description": item.description,
                "default_question": item.default_question,
                "prompt_content": item.prompt_content,
                "group_name": item.group_name,
                "sort_order": item.sort_order,
            }
            for item in items
        ],
    }


@router.post("/templates/{template_id}/import")
async def import_template(
    template_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """导入预置模板到用户集合"""
    template = (
        await db.execute(
            select(DimensionTemplate).where(DimensionTemplate.id == template_id)
        )
    ).scalar_one_or_none()
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")

    # 创建新集合
    new_name = template.name
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{template.name} ({suffix})"

    ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=template.description,
        is_default=0,
        is_system=0,
        is_available_for_reading=1,
    )
    db.add(ds)
    await db.flush()
    await _activate_dimension_set(db, user.id, ds)

    # 复制维度
    items = (
        await db.execute(
            select(TemplateItem)
            .where(TemplateItem.template_id == template_id)
            .order_by(TemplateItem.sort_order)
        )
    ).scalars().all()

    for item in items:
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=item.dim_key,
                dim_name=item.dim_name,
                description=item.description,
                prompt_content=item.prompt_content,
                default_question=item.default_question,
                sort_order=item.sort_order,
                is_builtin=1,
                group_name=item.group_name,
            )
        )

    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(items)}


# ---------------------------------------------------------------------------
# AI Generation
# ---------------------------------------------------------------------------

_generation_cache: dict[str, dict] = {}



class SaveGeneratedRequest(BaseModel):
    name: str
    description: Optional[str] = None
    category: str = "AI生成"
    dimensions: list[dict]


@router.post("/generate")
async def generate_template(
    file_upload: Optional[UploadFile] = File(None),
    file_id: Optional[str] = Form(None),
    dim_count: int = Form(12),
    force_regenerate: bool = Form(False),
    api_key: Optional[str] = Form(None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    print(f"[generate] file_upload={file_upload}, file_id={file_id}, dim_count={dim_count}, force_regenerate={force_regenerate}, api_key={'***' if api_key else None}")
    import traceback as _tb
    from services.ai_template_generator import generate_template_from_paper

    try:
        text = ""
        if file_id:
            from db.models import File

            file_record = (
                await db.execute(select(File).where(File.id == int(file_id)))
            ).scalar_one_or_none()
            if file_record is None:
                raise HTTPException(status_code=404, detail="文件不存在")

            storage_path = file_record.storage_path  # type: ignore[attr-defined]
            if not storage_path or not os.path.exists(storage_path):
                raise HTTPException(status_code=400, detail="文件路径无效")

            from routers.reading import extract_paper_text

            text = extract_paper_text(storage_path) or ""
        elif file_upload:
            content = await file_upload.read()
            fname = file_upload.filename or "upload.txt"
            ext = os.path.splitext(fname)[1].lower()
            if ext == ".pdf":
                import tempfile

                tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
                try:
                    tmp.write(content)
                    tmp.close()
                    from routers.reading import extract_paper_text

                    text = extract_paper_text(tmp.name) or ""
                finally:
                    if os.path.exists(tmp.name):
                        os.unlink(tmp.name)
            else:
                text = content.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(status_code=400, detail="请提供 file_id 或上传文件")

        if not text or len(text.strip()) < 100:
            raise HTTPException(status_code=400, detail="无法从文件中提取有效文本（至少需要100字符）")

        cache_payload = f"{user.id}:{dim_count}:".encode("utf-8") + text[:8000].encode(
            "utf-8", errors="ignore"
        )
        cache_key = hashlib.sha256(cache_payload).hexdigest()
        if not force_regenerate and cache_key in _generation_cache:
            return _generation_cache[cache_key]

        meta_prompt_template = None
        system_role = None
        try:
            from prompt_service import get_prompt_payload
            meta_payload = await get_prompt_payload(db, prompt_type="ai_template", prompt_key="meta_prompt", user_id=user.id)
            meta_prompt_template = meta_payload.effective_content
            sys_payload = await get_prompt_payload(db, prompt_type="ai_template", prompt_key="system_role", user_id=user.id)
            system_role = sys_payload.effective_content
        except Exception:
            pass

        result = generate_template_from_paper(
            paper_text=text,
            api_key=api_key or "",
            dim_count=dim_count,
            meta_prompt_template=meta_prompt_template,
            system_role=system_role,
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        _generation_cache[cache_key] = result
        return result
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        _tb.print_exc()
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")


@router.post("/generate/save")
async def save_generated_template(
    body: SaveGeneratedRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    new_name = body.name
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{body.name} ({suffix})"

    ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=body.description,
        is_default=0,
        is_system=0,
        is_available_for_reading=0,
    )
    db.add(ds)
    await db.flush()
    await _activate_dimension_set(db, user.id, ds)

    for idx, dim in enumerate(body.dimensions):
        dim_name_slug = re.sub(r"[^\w]", "_", dim.get("dim_name", ""))[:20]
        dim_key = f"ai_{dim_name_slug}_{idx}"
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=dim_key,
                dim_name=dim.get("dim_name", f"维度{idx + 1}"),
                description=dim.get("description"),
                prompt_content=dim.get("prompt_content", ""),
                default_question=dim.get("default_question", ""),
                sort_order=idx,
                is_builtin=0,
                group_name=dim.get("group_name"),
            )
        )

    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(body.dimensions)}


# ---------------------------------------------------------------------------
# Document Import
# ---------------------------------------------------------------------------


class ConfirmImportRequest(BaseModel):
    name: str
    description: Optional[str] = None
    dimensions: list[dict]


@router.post("/import/preview")
async def preview_import(
    file: UploadFile,
    user: User = Depends(current_user),
):
    from services.document_parser import ParseError, parse_document

    try:
        content = await file.read()
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="文件编码错误，请保存为 UTF-8 格式后重试",
        )

    ext = os.path.splitext(file.filename or ".txt")[1]

    try:
        result = parse_document(text, ext)
    except ParseError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    return {
        "template_name": result.get("template_name", ""),
        "description": result.get("description", ""),
        "dimension_count": len(result.get("dimensions", [])),
        "dimensions": [
            {
                "dim_name": d.get("dim_name", ""),
                "description": d.get("description", ""),
                "default_question": d.get("default_question", ""),
                "prompt_content": d.get("prompt_content", ""),
                "group_name": d.get("group_name"),
            }
            for d in result.get("dimensions", [])
        ],
    }


@router.post("/import/confirm")
async def confirm_import(
    body: ConfirmImportRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    new_name = body.name
    suffix = 1
    while True:
        dup = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.name == new_name,
                )
            )
        ).scalar_one_or_none()
        if dup is None:
            break
        suffix += 1
        new_name = f"{body.name} ({suffix})"

    ds = DimensionSet(
        owner_user_id=user.id,
        name=new_name,
        description=body.description,
        is_default=0,
        is_system=0,
        is_available_for_reading=0,
    )
    db.add(ds)
    await db.flush()
    await _activate_dimension_set(db, user.id, ds)

    for idx, dim in enumerate(body.dimensions):
        db.add(
            DimensionItem(
                set_id=ds.id,
                dim_key=f"import_{idx}",
                dim_name=dim.get("dim_name", f"维度{idx + 1}"),
                description=dim.get("description"),
                prompt_content=dim.get("prompt_content", ""),
                default_question=dim.get("default_question", ""),
                sort_order=idx,
                is_builtin=0,
                group_name=dim.get("group_name"),
            )
        )

    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(body.dimensions)}
