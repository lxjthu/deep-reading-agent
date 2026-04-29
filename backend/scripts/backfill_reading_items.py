"""Backfill structured reading_items from existing reading markdown artifacts."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND_DIR = HERE.parent
PROJECT_ROOT = BACKEND_DIR.parent
for path in (str(PROJECT_ROOT), str(BACKEND_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from sqlalchemy import func, select  # noqa: E402

from db import AsyncSessionLocal  # noqa: E402
from db.models import Artifact, Job, JobBibEntry, ReadingItem  # noqa: E402
from routers.reading import build_long_reading_items, build_step_reading_items  # noqa: E402


STEP_DELIMITER_RE = re.compile(r"\n+---\n+", re.MULTILINE)
LONG_SECTION_RE = re.compile(
    r"<!--DIMENSIONS_START-->\s*(.*?)\s*<!--DIMENSIONS_END-->",
    re.DOTALL,
)
LONG_DIM_RE = re.compile(
    r"^###\s+(.+?)\s*$([\s\S]*?)(?=^###\s+.+?$|\Z)",
    re.MULTILINE,
)
STEP_RE = re.compile(
    r"^##\s+(第[一二三四五六七八九十]+步[：:].+?)\s*$([\s\S]*?)(?=^##\s+第[一二三四五六七八九十]+步[：:].+?$|\Z)",
    re.MULTILINE,
)


@dataclass
class BackfillStats:
    scanned_jobs: int = 0
    created_items: int = 0
    skipped_existing: int = 0
    skipped_missing_report: int = 0
    skipped_missing_target: int = 0
    failed_parse: int = 0


def strip_frontmatter(content: str) -> str:
    if content.startswith("---\n"):
        end = content.find("\n---\n", 4)
        if end != -1:
            return content[end + 5 :]
    return content


def get_results_root() -> Path:
    configured = os.getenv("RESULTS_ROOT_DIR")
    root = Path(configured) if configured else (PROJECT_ROOT / "deep_reading_results")
    if not root.is_absolute():
        root = (PROJECT_ROOT / root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def parse_long_report(content: str) -> dict[str, str]:
    cleaned = strip_frontmatter(content)
    match = LONG_SECTION_RE.search(cleaned)
    target = match.group(1) if match else cleaned
    results: dict[str, str] = {}
    for dim_match in LONG_DIM_RE.finditer(target):
        label = dim_match.group(1).strip()
        body = dim_match.group(2).strip()
        if label and body:
            results[label] = body
    return results


def parse_step_report(content: str) -> dict[str, str]:
    cleaned = strip_frontmatter(content)
    cleaned = STEP_DELIMITER_RE.sub("\n", cleaned)
    results: dict[str, str] = {}
    for step_match in STEP_RE.finditer(cleaned):
        label = step_match.group(1).strip()
        body = step_match.group(2).strip()
        if label and body and not label.endswith("精读报告"):
            results[label] = body
    return results


def build_items_for_job(job_type: str, report_content: str, params_json: str) -> list[dict]:
    params = json.loads(params_json or "{}")
    if job_type == "reading_long":
        results = parse_long_report(report_content)
        return build_long_reading_items(results, params.get("custom_question"))
    if job_type == "reading_quant":
        results = parse_step_report(report_content)
        return build_step_reading_items(results, mode="quant")
    if job_type == "reading_qual":
        results = parse_step_report(report_content)
        return build_step_reading_items(results, mode="qual")
    return []


async def backfill_reading_items(*, dry_run: bool = False, replace_existing: bool = False) -> BackfillStats:
    stats = BackfillStats()
    results_root = get_results_root()
    async with AsyncSessionLocal() as session:
        jobs = (
            await session.execute(
                select(Job).where(Job.job_type.in_(("reading_long", "reading_quant", "reading_qual")))
            )
        ).scalars().all()

        for job in jobs:
            stats.scanned_jobs += 1

            existing_count = (
                await session.execute(
                    select(func.count(ReadingItem.id)).where(ReadingItem.job_id == job.id)
                )
            ).scalar_one()
            if existing_count:
                if not replace_existing:
                    stats.skipped_existing += 1
                    continue
                await session.execute(
                    ReadingItem.__table__.delete().where(ReadingItem.job_id == job.id)
                )

            target_link = (
                await session.execute(
                    select(JobBibEntry).where(
                        JobBibEntry.job_id == job.id,
                        JobBibEntry.role == "target",
                    )
                )
            ).scalar_one_or_none()
            if target_link is None:
                stats.skipped_missing_target += 1
                continue

            artifact = (
                await session.execute(
                    select(Artifact).where(
                        Artifact.job_id == job.id,
                        Artifact.artifact_type == "reading_final",
                    )
                )
            ).scalar_one_or_none()
            if artifact is None:
                stats.skipped_missing_report += 1
                continue

            report_path = results_root / artifact.storage_path
            if not report_path.exists():
                stats.skipped_missing_report += 1
                continue

            items = build_items_for_job(
                job.job_type,
                report_path.read_text(encoding="utf-8"),
                job.params_json or "{}",
            )
            if not items:
                stats.failed_parse += 1
                continue

            stats.created_items += len(items)
            if dry_run:
                continue

            for item in items:
                session.add(
                    ReadingItem(
                        owner_user_id=job.owner_user_id,
                        bib_entry_id=target_link.bib_entry_id,
                        job_id=job.id,
                        mode=item["mode"],
                        section_type=item["section_type"],
                        parent_key=item.get("parent_key"),
                        item_key=item["item_key"],
                        item_label=item["item_label"],
                        sort_order=item.get("sort_order", 0),
                        content=item["content"],
                    )
                )

        if dry_run:
            await session.rollback()
        else:
            await session.commit()

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill reading_items from existing reading reports.")
    parser.add_argument("--dry-run", action="store_true", help="Parse existing reports without writing DB records.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing reading_items for matched jobs and rebuild them.",
    )
    args = parser.parse_args()
    stats = asyncio.run(backfill_reading_items(dry_run=args.dry_run, replace_existing=args.replace_existing))
    print(json.dumps(stats.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
