from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
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


class SetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.get("/sets")
async def list_sets(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(DimensionSet)
            .where(DimensionSet.owner_user_id == user.id)
            .order_by(DimensionSet.sort_order, DimensionSet.id)
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
        result.append(
            {
                "id": ds.id,
                "name": ds.name,
                "description": ds.description,
                "is_default": bool(ds.is_default),
                "is_system": bool(ds.is_system),
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


@router.post("/sets/{set_id}/activate")
async def activate_set(
    set_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await _get_user_set(db, set_id, user.id)
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
    used = await db.execute(
        select(func.count()).select_from(ReadingItem).where(
            ReadingItem.owner_user_id == user.id,
            ReadingItem.mode == "long",
            ReadingItem.item_label == item.dim_name,
        )
    )
    if (used.scalar() or 0) > 0:
        raise HTTPException(status_code=409, detail=f"维度「{item.dim_name}」已有 {used.scalar()} 条精读记录，无法删除")
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
    )
    db.add(ds)
    await db.flush()

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
            )
        )

    await db.commit()
    return {"id": ds.id, "name": ds.name, "dim_count": len(items)}
