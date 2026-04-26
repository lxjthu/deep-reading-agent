"""Seed (or refresh) the built-in admin account.

Usage:
    cd backend
    python -m scripts.seed_admin
    # or, with overrides:
    ADMIN_USERNAME=admin ADMIN_PASSWORD='XIAojuan@0618wenxian' python -m scripts.seed_admin

Re-running is safe: if the admin user already exists, the script reports it
and exits without modifying the password (use ``--reset-password`` to overwrite).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

# Allow running both as `python -m scripts.seed_admin` (cwd=backend) and
# as `python backend/scripts/seed_admin.py` (cwd=repo root).
HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import select  # noqa: E402

from db import AsyncSessionLocal  # noqa: E402
from db.models import User  # noqa: E402

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "XIAojuan@0618wenxian"


async def seed(username: str, password: str, reset_password: bool) -> int:
    async with AsyncSessionLocal() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

        if existing is not None:
            if reset_password:
                existing.password_hash = pwd_context.hash(password)
                existing.role = "admin"
                existing.is_active = 1
                await session.commit()
                print(f"[seed_admin] reset password for existing admin '{username}' (id={existing.id})")
                return existing.id
            print(
                f"[seed_admin] admin '{username}' already exists (id={existing.id}); "
                "skipping. Pass --reset-password to overwrite."
            )
            return existing.id

        user = User(
            username=username,
            password_hash=pwd_context.hash(password),
            role="admin",
            is_active=1,
            created_at=datetime.utcnow(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        print(f"[seed_admin] created admin '{username}' (id={user.id})")
        return user.id


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the built-in admin account.")
    parser.add_argument(
        "--username",
        default=os.getenv("ADMIN_USERNAME", DEFAULT_USERNAME),
        help="Admin username (default: env ADMIN_USERNAME or 'admin').",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ADMIN_PASSWORD", DEFAULT_PASSWORD),
        help="Admin password (default: env ADMIN_PASSWORD or built-in value).",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="If admin already exists, overwrite the password.",
    )
    args = parser.parse_args()
    asyncio.run(seed(args.username, args.password, args.reset_password))


if __name__ == "__main__":
    main()
