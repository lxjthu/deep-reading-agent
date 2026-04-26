"""FastAPI auth dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.security import decode_token
from db import get_db
from db.models import User


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _credentials_exception(detail: str = "认证失败。") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_user_by_id(user_id: int, db: AsyncSession) -> User | None:
    return (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()


async def current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise _credentials_exception("Token 类型错误。")
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise _credentials_exception("Token 无效或已过期。")

    user = await get_user_by_id(user_id, db)
    if user is None:
        raise _credentials_exception("用户不存在。")
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被停用。",
        )
    return user


async def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


async def require_vip_or_admin(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "vip"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="VIP required")
    return user
