"""Auth router for registration, login, JWT refresh, and account self-service."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user, get_user_by_id
from auth.schemas import (
    ChangePasswordRequest,
    LoginResponse,
    MessageResponse,
    RefreshRequest,
    RefreshResponse,
    RegisterRequest,
    RegisterResponse,
    UserResponse,
)
from auth.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    validate_password_strength,
    verify_password,
)
from db import get_db
from db.models import InviteCode, User


router = APIRouter()


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def build_warning_message(role: str) -> str | None:
    if role == "normal":
        return (
            "您是免费试用账户，上传文件、文献档案和精读结果将于每天 0 点自动清空；"
            "浏览器本地保存的 API Key 不受影响。"
        )
    return None


def build_user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        warning_msg=build_warning_message(user.role),
    )


def unauthorized(detail: str = "用户名或密码错误。") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegisterResponse:
    username = request.username.strip()
    invite_code_value = request.invite_code.strip() if request.invite_code else None

    if not username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名不能为空。")

    validate_password_strength(request.password)

    existing_user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if existing_user is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在。")

    if request.email:
        existing_email = (
            await db.execute(select(User).where(User.email == str(request.email)))
        ).scalar_one_or_none()
        if existing_email is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被使用。")

    role = "normal"
    invite: InviteCode | None = None
    if invite_code_value:
        invite = (
            await db.execute(select(InviteCode).where(InviteCode.code == invite_code_value))
        ).scalar_one_or_none()
        if invite is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码无效。")
        now = utcnow_naive()
        if invite.expires_at is not None and invite.expires_at <= now:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码已过期。")
        if invite.used_count >= invite.max_uses:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码已使用完毕。")
        role = "vip"

    user = User(
        username=username,
        email=str(request.email) if request.email else None,
        password_hash=hash_password(request.password),
        role=role,
        is_active=1,
        token_version=0,
        created_at=utcnow_naive(),
    )
    db.add(user)
    if invite is not None:
        invite.used_count += 1

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="注册失败，用户名或邮箱可能已存在。",
        ) from exc

    await db.refresh(user)
    return RegisterResponse(
        message="注册成功。",
        user=build_user_response(user),
    )


@router.post("/login", response_model=LoginResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    username = form_data.username.strip()
    user = (
        await db.execute(select(User).where(User.username == username))
    ).scalar_one_or_none()
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise unauthorized()
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="用户已被停用。")

    user.last_login_at = utcnow_naive()
    await db.commit()

    return LoginResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id, user.token_version),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    request: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> RefreshResponse:
    try:
        payload = decode_token(request.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("wrong token type")
        user_id = int(payload.get("sub", ""))
        token_version = int(payload.get("token_version", -1))
    except (TypeError, ValueError):
        raise unauthorized("Refresh token 无效或已过期。")

    user = await get_user_by_id(user_id, db)
    if user is None or not user.is_active:
        raise unauthorized("Refresh token 无效或已过期。")
    if user.token_version != token_version:
        raise unauthorized("Refresh token 已失效。")

    return RefreshResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user)) -> UserResponse:
    return build_user_response(user)


@router.post("/change_password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    if not verify_password(request.old_password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误。")

    validate_password_strength(request.new_password)
    user.password_hash = hash_password(request.new_password)
    user.token_version += 1
    await db.commit()
    return MessageResponse(message="密码修改成功，请重新登录。")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    user.token_version += 1
    await db.commit()
    return MessageResponse(message="已退出登录，旧 refresh token 已失效。")
