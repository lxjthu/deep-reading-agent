"""Admin router for user management and invite codes."""
from __future__ import annotations

import secrets
import json
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import require_admin
from auth.schemas import MessageResponse, UserResponse
from auth.security import hash_password, validate_password_strength
from cleanup import reapply_user_retention
from db import get_db
from db.models import AdminAuditLog, InviteCode, User
from routers.auth import build_user_response

router = APIRouter()


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class AdminUserUpdateRequest(BaseModel):
    role: Optional[str] = Field(default=None, pattern="^(admin|vip|normal)$")
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)
    is_active: Optional[int] = Field(default=None, ge=0, le=1)


class AdminInviteCreateRequest(BaseModel):
    code: Optional[str] = Field(default=None, max_length=128)
    max_uses: int = Field(default=1, ge=1)
    expires_at: Optional[datetime] = None
    note: Optional[str] = Field(default=None, max_length=255)


class AdminInviteResponse(BaseModel):
    id: int
    code: str
    created_by_user_id: int
    max_uses: int
    used_count: int
    expires_at: Optional[datetime]
    note: Optional[str]
    created_at: datetime
    is_expired: bool


class AdminUserUpdateResponse(BaseModel):
    message: str
    user: UserResponse


def build_invite_response(invite: InviteCode) -> AdminInviteResponse:
    now = utcnow_naive()
    return AdminInviteResponse(
        id=invite.id,
        code=invite.code,
        created_by_user_id=invite.created_by_user_id,
        max_uses=invite.max_uses,
        used_count=invite.used_count,
        expires_at=invite.expires_at,
        note=invite.note,
        created_at=invite.created_at,
        is_expired=invite.expires_at is not None and invite.expires_at <= now,
    )


def generate_invite_code() -> str:
    return f"VIP-{secrets.token_hex(4).upper()}"


def add_admin_audit(
    db: AsyncSession,
    *,
    admin_user_id: int,
    action: str,
    target_type: str,
    target_id: str | None,
    summary: str,
    payload: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            created_at=utcnow_naive(),
        )
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserResponse]:
    users = (
        await db.execute(select(User).order_by(User.created_at.desc(), User.id.desc()))
    ).scalars().all()
    return [build_user_response(user) for user in users]


@router.patch("/users/{user_id}", response_model=AdminUserUpdateResponse)
async def update_user(
    user_id: int,
    request: AdminUserUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserUpdateResponse:
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在。")

    changed = False
    if request.role is not None and request.role != user.role:
        user.role = request.role
        await reapply_user_retention(db, user.id, request.role, now=utcnow_naive())
        changed = True

    if request.new_password:
        validate_password_strength(request.new_password)
        user.password_hash = hash_password(request.new_password)
        user.token_version += 1
        changed = True

    if request.is_active is not None and request.is_active != user.is_active:
        user.is_active = request.is_active
        if not request.is_active:
            user.token_version += 1
        changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的字段。")

    add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="update_user",
        target_type="user",
        target_id=str(user.id),
        summary=f"更新用户 {user.username}",
        payload=request.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(user)
    return AdminUserUpdateResponse(message="用户更新成功。", user=build_user_response(user))


@router.get("/invite_codes", response_model=list[AdminInviteResponse])
async def list_invite_codes(
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminInviteResponse]:
    invites = (
        await db.execute(select(InviteCode).order_by(InviteCode.created_at.desc(), InviteCode.id.desc()))
    ).scalars().all()
    return [build_invite_response(invite) for invite in invites]


@router.post("/invite_codes", response_model=AdminInviteResponse)
async def create_invite_code(
    request: AdminInviteCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminInviteResponse:
    code = (request.code or generate_invite_code()).strip()
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码不能为空。")

    existing = (
        await db.execute(select(InviteCode).where(InviteCode.code == code))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码已存在。")

    invite = InviteCode(
        code=code,
        created_by_user_id=admin.id,
        max_uses=request.max_uses,
        used_count=0,
        expires_at=request.expires_at.replace(tzinfo=None) if request.expires_at else None,
        note=request.note,
        created_at=utcnow_naive(),
    )
    db.add(invite)
    add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="create_invite_code",
        target_type="invite_code",
        target_id=code,
        summary=f"创建邀请码 {code}",
        payload=request.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(invite)
    return build_invite_response(invite)


@router.delete("/invite_codes/{invite_id}", response_model=MessageResponse)
async def delete_invite_code(
    invite_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    invite = await db.get(InviteCode, invite_id)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="邀请码不存在。")
    code = invite.code
    await db.delete(invite)
    add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="delete_invite_code",
        target_type="invite_code",
        target_id=str(invite_id),
        summary=f"删除邀请码 {code}",
    )
    await db.commit()
    return MessageResponse(message="邀请码已删除。")
