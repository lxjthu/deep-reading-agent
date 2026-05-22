from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PromptTemplate
from prompt_registry import (
    PROMPT_TYPE_LABELS,
    get_builtin_fallback,
    get_prompt_definition,
    iter_prompt_slots,
    load_prompt_from_file,
)


@dataclass
class PromptPayload:
    prompt_type: str
    prompt_key: str
    title: str
    effective_content: str
    system_content: str
    user_content: str
    source: str
    has_system_default: bool
    has_user_override: bool


async def ensure_builtin_prompt_templates(db: AsyncSession) -> None:
    existing_rows = (
        await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.scope == "system",
                PromptTemplate.owner_user_id.is_(None),
            )
        )
    ).scalars().all()
    existing = {(row.prompt_type, row.prompt_key): row for row in existing_rows}

    changed = False
    for slot in iter_prompt_slots():
        key = (slot["type"], slot["key"])
        content = load_prompt_from_file(slot["type"], slot["key"]) or get_builtin_fallback(
            slot["type"], slot["key"]
        )
        row = existing.get(key)
        if row is None:
            db.add(
                PromptTemplate(
                    owner_user_id=None,
                    scope="system",
                    prompt_type=slot["type"],
                    prompt_key=slot["key"],
                    title=slot["title"],
                    content=content,
                    updated_by_user_id=None,
                )
            )
            changed = True
            continue

        if row.updated_by_user_id is None and (
            row.title != slot["title"] or row.content != content
        ):
            row.title = slot["title"]
            row.content = content
            changed = True

    if changed:
        await db.commit()


async def _get_template_row(
    db: AsyncSession,
    *,
    prompt_type: str,
    prompt_key: str,
    owner_user_id: int | None,
    scope: str,
) -> PromptTemplate | None:
    return (
        await db.execute(
            select(PromptTemplate).where(
                PromptTemplate.prompt_type == prompt_type,
                PromptTemplate.prompt_key == prompt_key,
                PromptTemplate.owner_user_id == owner_user_id,
                PromptTemplate.scope == scope,
            ).limit(1)
        )
    ).scalar_one_or_none()


async def get_prompt_payload(
    db: AsyncSession,
    *,
    prompt_type: str,
    prompt_key: str,
    user_id: int,
) -> PromptPayload:
    get_prompt_definition(prompt_type, prompt_key)
    await ensure_builtin_prompt_templates(db)

    system_row = await _get_template_row(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        owner_user_id=None,
        scope="system",
    )
    user_row = await _get_template_row(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        owner_user_id=user_id,
        scope="user",
    )

    file_fallback = load_prompt_from_file(prompt_type, prompt_key)
    builtin_fallback = get_builtin_fallback(prompt_type, prompt_key)

    system_content = (
        system_row.content
        if system_row is not None
        else (file_fallback or builtin_fallback)
    )
    user_content = user_row.content if user_row is not None else ""

    if user_row is not None and user_row.content.strip():
        effective_content = user_row.content
        source = "user_override"
    elif system_row is not None and system_row.content.strip():
        effective_content = system_row.content
        source = "system_default"
    elif file_fallback:
        effective_content = file_fallback
        source = "file_fallback"
    else:
        effective_content = builtin_fallback
        source = "builtin_fallback"

    return PromptPayload(
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        title=get_prompt_definition(prompt_type, prompt_key)["title"],
        effective_content=effective_content,
        system_content=system_content,
        user_content=user_content,
        source=source,
        has_system_default=system_row is not None,
        has_user_override=user_row is not None,
    )


async def get_catalog(db: AsyncSession, *, user_id: int) -> list[dict]:
    await ensure_builtin_prompt_templates(db)
    catalog: list[dict] = []
    for prompt_type, type_label in PROMPT_TYPE_LABELS.items():
        items: list[dict] = []
        for slot in [slot for slot in iter_prompt_slots() if slot["type"] == prompt_type]:
            payload = await get_prompt_payload(
                db,
                prompt_type=prompt_type,
                prompt_key=slot["key"],
                user_id=user_id,
            )
            items.append(
                {
                    "key": slot["key"],
                    "title": slot["title"],
                    "source": payload.source,
                    "has_system_default": payload.has_system_default,
                    "has_user_override": payload.has_user_override,
                }
            )
        catalog.append({"type": prompt_type, "label": type_label, "items": items})
    return catalog


async def get_effective_prompt_text(
    db: AsyncSession,
    *,
    user_id: int,
    prompt_type: str,
    prompt_key: str,
) -> str:
    payload = await get_prompt_payload(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        user_id=user_id,
    )
    return payload.effective_content


async def get_effective_prompt_map(
    db: AsyncSession,
    *,
    user_id: int,
    prompt_type: str,
) -> dict[str, str]:
    if prompt_type not in PROMPT_TYPE_LABELS:
        raise KeyError(f"invalid prompt type: {prompt_type}")
    result: dict[str, str] = {}
    for slot in [slot for slot in iter_prompt_slots() if slot["type"] == prompt_type]:
        result[slot["key"]] = await get_effective_prompt_text(
            db,
            user_id=user_id,
            prompt_type=prompt_type,
            prompt_key=slot["key"],
        )
    return result


async def upsert_user_prompt(
    db: AsyncSession,
    *,
    user_id: int,
    prompt_type: str,
    prompt_key: str,
    content: str,
) -> None:
    definition = get_prompt_definition(prompt_type, prompt_key)
    await ensure_builtin_prompt_templates(db)
    row = await _get_template_row(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        owner_user_id=user_id,
        scope="user",
    )
    if row is None:
        row = PromptTemplate(
            owner_user_id=user_id,
            scope="user",
            prompt_type=prompt_type,
            prompt_key=prompt_key,
            title=definition["title"],
            content=content,
            updated_by_user_id=user_id,
        )
        db.add(row)
    else:
        row.title = definition["title"]
        row.content = content
        row.updated_by_user_id = user_id
    await db.commit()


async def delete_user_prompt(
    db: AsyncSession,
    *,
    user_id: int,
    prompt_type: str,
    prompt_key: str,
) -> bool:
    get_prompt_definition(prompt_type, prompt_key)
    row = await _get_template_row(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        owner_user_id=user_id,
        scope="user",
    )
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


async def upsert_system_prompt(
    db: AsyncSession,
    *,
    admin_user_id: int,
    prompt_type: str,
    prompt_key: str,
    content: str,
) -> None:
    definition = get_prompt_definition(prompt_type, prompt_key)
    await ensure_builtin_prompt_templates(db)
    row = await _get_template_row(
        db,
        prompt_type=prompt_type,
        prompt_key=prompt_key,
        owner_user_id=None,
        scope="system",
    )
    if row is None:
        row = PromptTemplate(
            owner_user_id=None,
            scope="system",
            prompt_type=prompt_type,
            prompt_key=prompt_key,
            title=definition["title"],
            content=content,
            updated_by_user_id=admin_user_id,
        )
        db.add(row)
    else:
        row.title = definition["title"]
        row.content = content
        row.updated_by_user_id = admin_user_id
    await db.commit()
