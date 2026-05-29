"""Standalone runner for the midnight normal-user cleanup job.

Usage:
    cd backend
    python -m scripts.run_cleanup_normal_users
    python -m scripts.run_cleanup_normal_users --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _load_env() -> None:
    env_path = os.environ.get("DEEP_READING_ENV")
    if env_path:
        load_dotenv(env_path)
        return

    for candidate in (PROJECT_ROOT / ".env.production", PROJECT_ROOT / ".env"):
        if candidate.exists():
            load_dotenv(candidate)
            return


_load_env()

from cleanup import cleanup_normal_user_data  # noqa: E402


async def _run(dry_run: bool | None) -> dict:
    return await cleanup_normal_user_data(dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the normal-user cleanup job without relying on the API process scheduler."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect what would be deleted without committing any database changes.",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Force a real cleanup run even if CLEANUP_DRY_RUN is enabled in the environment.",
    )
    args = parser.parse_args()

    if args.dry_run and args.no_dry_run:
        parser.error("--dry-run and --no-dry-run cannot be used together")

    explicit_dry_run = True if args.dry_run else False if args.no_dry_run else None

    try:
        result = asyncio.run(_run(explicit_dry_run))
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"[cleanup-runner] failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
