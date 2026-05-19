"""Shared helpers for analysis result storage."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from db import PROJECT_ROOT


def _legacy_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return PROJECT_ROOT


def get_results_root() -> Path:
    """Return the writable result root for generated artifacts."""
    configured = os.getenv("RESULTS_ROOT_DIR") or os.getenv("RESULTS_DIR")
    if configured:
        root = Path(configured)
        if not root.is_absolute():
            root = (PROJECT_ROOT / root).resolve()
    else:
        root = PROJECT_ROOT / "deep_reading_results"
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_result_storage_path(absolute_path: Path) -> str:
    """Store artifact paths relative to the active result root when possible."""
    path = absolute_path.resolve()
    try:
        return path.relative_to(get_results_root().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def resolve_result_path(storage_path: str) -> Path:
    """Resolve an artifact storage path, preserving compatibility with old rows."""
    path = Path(storage_path)
    if path.is_absolute():
        return path

    candidates = [
        get_results_root() / path,
        PROJECT_ROOT / "deep_reading_results" / path,
        _legacy_project_root() / "deep_reading_results" / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
