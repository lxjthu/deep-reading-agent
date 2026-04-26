"""Password hashing, JWT handling, and auth-related validation."""
from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from jose import JWTError, jwt
from passlib.context import CryptContext


env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(env_path)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")


def _get_env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc


def get_jwt_secret_key() -> str:
    return os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me")


def get_jwt_algorithm() -> str:
    return os.getenv("JWT_ALGORITHM", "HS256")


def get_access_token_expire_minutes() -> int:
    return _get_env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)


def get_refresh_token_expire_days() -> int:
    return _get_env_int("REFRESH_TOKEN_EXPIRE_DAYS", 30)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def validate_password_strength(password: str) -> None:
    if not PASSWORD_PATTERN.match(password):
        raise ValueError("密码必须至少 8 位，且同时包含字母和数字。")


def _base_claims(user_id: int, token_type: str) -> Dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "sub": str(user_id),
        "type": token_type,
        "iat": int(now.timestamp()),
    }


def create_access_token(user_id: int) -> str:
    now = datetime.now(UTC)
    payload = _base_claims(user_id, "access")
    payload["exp"] = int(
        (now + timedelta(minutes=get_access_token_expire_minutes())).timestamp()
    )
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=get_jwt_algorithm())


def create_refresh_token(user_id: int, token_version: int) -> str:
    now = datetime.now(UTC)
    payload = _base_claims(user_id, "refresh")
    payload["token_version"] = token_version
    payload["exp"] = int(
        (now + timedelta(days=get_refresh_token_expire_days())).timestamp()
    )
    return jwt.encode(payload, get_jwt_secret_key(), algorithm=get_jwt_algorithm())


def decode_token(token: str) -> Dict[str, Any]:
    try:
        return jwt.decode(
            token,
            get_jwt_secret_key(),
            algorithms=[get_jwt_algorithm()],
        )
    except JWTError as exc:
        raise ValueError("Token 无效或已过期。") from exc
