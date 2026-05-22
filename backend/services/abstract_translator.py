"""Batch abstract translation service using DeepSeek."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from openai import OpenAI


_SYSTEM_PROMPT = """你是一位学术翻译专家。将英文学术摘要翻译为中文。
要求：
1. 保持学术术语的准确性
2. 保留关键数据和方法信息
3. 语言流畅自然
4. 直接输出翻译结果，不要添加前缀或说明"""

MAX_RETRIES = 2
TIMEOUT = 120


def _translate_one(
    abstract: str,
    api_key: str,
    model: str = "deepseek-v4-flash",
) -> str:
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                extra_body={"thinking": {"type": "disabled"}},
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"请翻译以下学术摘要：\n\n{abstract}"},
                ],
                max_tokens=2000,
                timeout=TIMEOUT,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(3)
    raise last_err


def run_batch_translate(
    job_id: str,
    user_id: int,
    entry_ids: list[str],
    api_key: str,
    log_cb: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    model: str = "deepseek-v4-flash",
    max_workers: int = 5,
):
    """Background thread: translate abstracts for given entry_ids.

    Updates Job progress in database as it goes.
    Results are written directly to BibEntry.abstract_cn.
    """
    import asyncio
    import sys
    import os

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from db import AsyncSessionLocal
    from db.models import BibEntry, Job
    from sqlalchemy import select

    async def _run():
        total = len(entry_ids)
        translated = 0
        skipped = 0
        failed = 0
        errors: list[str] = []

        async with AsyncSessionLocal() as db:
            entries_result = await db.execute(
                select(BibEntry).where(
                    BibEntry.id.in_(entry_ids),
                    BibEntry.owner_user_id == user_id,
                )
            )
            entries = list(entries_result.scalars().all())

            to_translate = []
            for e in entries:
                if not e.abstract or not e.abstract.strip():
                    skipped += 1
                    continue
                to_translate.append(e)

            actual_total = len(to_translate)
            if log_cb:
                log_cb(f"共 {actual_total} 条待翻译（跳过 {skipped} 条无摘要）")

            if actual_total == 0:
                job_result = await db.execute(select(Job).where(Job.id == job_id))
                job = job_result.scalar_one_or_none()
                if job:
                    job.status = "success"
                    job.progress = 100
                    job.current_stage = "无待翻译条目"
                    job.params_json = json.dumps({
                        "total": total, "translated": 0, "skipped": skipped, "failed": 0, "errors": []
                    }, ensure_ascii=False)
                    await db.commit()
                return

            def translate_entry(entry: BibEntry):
                if cancel_check and cancel_check():
                    return entry, None, "cancelled"
                try:
                    cn = _translate_one(entry.abstract, api_key, model)
                    return entry, cn, None
                except Exception as exc:
                    return entry, None, str(exc)

            done_count = 0
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {pool.submit(translate_entry, e): e for e in to_translate}
                for future in as_completed(futures):
                    if cancel_check and cancel_check():
                        break
                    entry, cn, err = future.result()
                    done_count += 1

                    if err:
                        failed += 1
                        errors.append(f"{entry.title[:30]}: {err}")
                        if log_cb:
                            log_cb(f"❌ 翻译失败: {entry.title[:40]}")
                    else:
                        entry.abstract_cn = cn
                        translated += 1
                        if log_cb:
                            log_cb(f"✅ [{translated}/{actual_total}] {entry.title[:40]}")

                    progress = int(done_count / actual_total * 100)
                    job_result = await db.execute(select(Job).where(Job.id == job_id))
                    job = job_result.scalar_one_or_none()
                    if job:
                        job.progress = progress
                        job.current_stage = f"已翻译 {translated}/{actual_total}，失败 {failed}"
                        await db.commit()

            await db.commit()

            job_result = await db.execute(select(Job).where(Job.id == job_id))
            job = job_result.scalar_one_or_none()
            if job:
                job.status = "success" if translated > 0 else "failed"
                job.progress = 100
                job.current_stage = f"完成：翻译 {translated}，跳过 {skipped}，失败 {failed}"
                job.params_json = json.dumps({
                    "total": total,
                    "translated": translated,
                    "skipped": skipped,
                    "failed": failed,
                    "errors": errors[:10],
                }, ensure_ascii=False)
                await db.commit()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    finally:
        loop.close()
