"""Prompt center router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user, require_admin
from db import get_db
from db.models import User
from prompt_registry import get_prompt_definition
from prompt_service import (
    delete_user_prompt,
    get_catalog,
    get_prompt_payload,
    upsert_system_prompt,
    upsert_user_prompt,
)


router = APIRouter()


class PromptUpdate(BaseModel):
    type: str
    step: str
    content: str


class PromptItemUpdate(BaseModel):
    type: str
    key: str
    content: str


def _normalize_slot(prompt_type: str, prompt_key: str) -> tuple[str, str]:
    try:
        get_prompt_definition(prompt_type, prompt_key)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return prompt_type, prompt_key


@router.get("/catalog")
async def prompt_catalog(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    return {"types": await get_catalog(db, user_id=user.id)}


@router.get("/item")
async def get_prompt_item(
    type: str = Query(...),
    key: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(type, key)
    payload = await get_prompt_payload(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        user_id=user.id,
    )
    return {
        "type": prompt_type,
        "key": prompt_key,
        "title": payload.title,
        "effective_content": payload.effective_content,
        "system_content": payload.system_content,
        "user_content": payload.user_content,
        "source": payload.source,
        "has_system_default": payload.has_system_default,
        "has_user_override": payload.has_user_override,
        "can_edit_system": user.role == "admin",
    }


@router.put("/my")
async def save_my_prompt(
    request: PromptItemUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(request.type, request.key)
    await upsert_user_prompt(
        db,
        user_id=user.id,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        content=request.content,
    )
    return {"success": True, "message": "个人提示词已保存。"}


@router.delete("/my")
async def reset_my_prompt(
    type: str = Query(...),
    key: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(type, key)
    deleted = await delete_user_prompt(
        db,
        user_id=user.id,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
    )
    return {"success": True, "deleted": deleted}


@router.put("/system")
async def save_system_prompt(
    request: PromptItemUpdate,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(request.type, request.key)
    await upsert_system_prompt(
        db,
        admin_user_id=admin_user.id,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        content=request.content,
    )
    return {"success": True, "message": "系统默认提示词已保存。"}


@router.get("/")
async def get_prompt(
    type: str = Query(...),
    step: str = Query(...),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(type, step)
    payload = await get_prompt_payload(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        user_id=user.id,
    )
    return {
        "type": prompt_type,
        "step": prompt_key,
        "content": payload.effective_content,
        "exists": True,
        "source": payload.source,
        "title": payload.title,
    }


@router.put("/")
async def update_prompt(
    request: PromptUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    prompt_type, prompt_key = _normalize_slot(request.type, request.step)
    if user.role == "admin":
        await upsert_system_prompt(
            db,
            admin_user_id=user.id,
            prompt_type=prompt_type,
            prompt_key=prompt_key,
            content=request.content,
        )
        return {"success": True, "message": "系统默认提示词已保存。", "target": "system"}

    await upsert_user_prompt(
        db,
        user_id=user.id,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        content=request.content,
    )
    return {"success": True, "message": "个人提示词已保存。", "target": "user"}


@router.get("/list")
async def list_prompts(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    catalog = await get_catalog(db, user_id=user.id)
    result: dict[str, dict[str, dict[str, object]]] = {}
    for prompt_type in catalog:
        result[prompt_type["type"]] = {}
        for item in prompt_type["items"]:
            result[prompt_type["type"]][item["key"]] = {
                "exists": item["has_system_default"],
                "has_user_override": item["has_user_override"],
                "source": item["source"],
            }
    return result
