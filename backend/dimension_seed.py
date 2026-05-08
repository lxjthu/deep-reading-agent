from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DimensionItem, DimensionSet, User
from new_architecture.analysis_dimensions import ANALYSIS_DIMENSIONS
from prompt_registry import load_prompt_from_file


async def ensure_default_dimension_sets(db: AsyncSession) -> None:
    users = (await db.execute(select(User))).scalars().all()
    for user in users:
        existing = (
            await db.execute(
                select(DimensionSet).where(
                    DimensionSet.owner_user_id == user.id,
                    DimensionSet.is_system == 1,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        default_set = DimensionSet(
            owner_user_id=user.id,
            name="默认维度集",
            is_default=1,
            is_system=1,
            sort_order=0,
        )
        db.add(default_set)
        await db.flush()
        for idx, (key, dim) in enumerate(ANALYSIS_DIMENSIONS.items()):
            prompt = load_prompt_from_file("long", key) or dim["system_prompt_addition"]
            item = DimensionItem(
                set_id=default_set.id,
                dim_key=key,
                dim_name=dim["name"],
                description=dim["description"],
                prompt_content=prompt,
                default_question=dim["default_questions"][0] if dim["default_questions"] else "",
                sort_order=idx,
                is_builtin=1 if key != "custom" else 0,
            )
            db.add(item)
    await db.commit()
