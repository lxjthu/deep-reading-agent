# 对比页三按钮后端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现对比页 AnswerCard 三按钮（编辑/点评/AI总结）的全部后端支撑：数据库表、ORM 模型、API 端点、reading-data 响应扩展。

**Architecture:** 在现有 `compare.py` 路由上新增 7 个端点（编辑覆盖 PUT/DELETE、点评 CRUD、AI 总结 POST），通过 Alembic migration 011 新增 `reading_item_edits` 和 `annotations` 两张表，扩展 `get_reading_data` 返回 edit/annotations/reading_item_id。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic + SQLite + DeepSeek API

**Spec:** `docs/COMPARE_CARD_ACTIONS_IMPL.md`

**前端已完成，无需修改。** 前端代码（AnswerCard、AccordionPanel、compare.css、useCompareData）已在 `c53b5b05` commit 中，API 调用路径和字段名均已固定。

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| 新增 | `backend/migrations/versions/011_add_edits_and_annotations.py` | 创建两张新表 + 扩展 prompt_type CHECK 约束 |
| 修改 | `backend/db/models.py` | 新增 `ReadingItemEdit`、`Annotation` 模型；修改 `PromptTemplate` CHECK 约束 |
| 修改 | `backend/prompt_registry.py` | 新增 `compare` 类型 + `ai_summary` 槽位 |
| 新增 | `prompts/compare/ai_summary.md` | AI 总结默认提示词 |
| 修改 | `backend/routers/compare.py` | 7 个新端点 + `build_compare_response` 扩展 |
| 修改 | `backend/cleanup.py` | 新表数据清理 |

---

## Task 1: 新增 ORM 模型（ReadingItemEdit + Annotation）

**Files:**
- Modify: `backend/db/models.py`

- [ ] **Step 1: 在 `backend/db/models.py` 中 `ReadingItem` 类之后（约 L514）新增两个模型**

在 `# Artifacts` 注释块之前插入：

```python
class ReadingItemEdit(Base):
    __tablename__ = "reading_item_edits"
    __table_args__ = (
        UniqueConstraint("reading_item_id", "owner_user_id", name="uq_rie_item_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reading_item_id: Mapped[int] = mapped_column(
        ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    edited_content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_rie_reading_item", ReadingItemEdit.reading_item_id)
Index("idx_rie_owner", ReadingItemEdit.owner_user_id)


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('compare_card','ai_summary','library_note')",
            name="ck_annotations_source_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    bib_entry_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="SET NULL"), nullable=True
    )
    selected_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_ai_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    color: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_annotations_owner", Annotation.owner_user_id)
Index("idx_annotations_source", Annotation.source_type, Annotation.source_id)
Index("idx_annotations_bib", Annotation.bib_entry_id)
```

- [ ] **Step 2: 修改 PromptTemplate 的 CHECK 约束，加入 `'compare'`**

将 `backend/db/models.py` 中 PromptTemplate 的 `ck_prompt_templates_type` 约束从：

```python
CheckConstraint(
    "prompt_type IN ('quant','qual','long','filter')",
    name="ck_prompt_templates_type",
),
```

改为：

```python
CheckConstraint(
    "prompt_type IN ('quant','qual','long','filter','compare')",
    name="ck_prompt_templates_type",
),
```

- [ ] **Step 3: 验证 import 无误**

Run: `cd backend && python -c "from db.models import ReadingItemEdit, Annotation; print('OK')"`

Expected: `OK`

---

## Task 2: 新增 Alembic Migration 011

**Files:**
- Create: `backend/migrations/versions/011_add_edits_and_annotations.py`

- [ ] **Step 1: 创建迁移文件**

创建 `backend/migrations/versions/011_add_edits_and_annotations.py`：

```python
"""add reading_item_edits + annotations tables, extend prompt_type check

Revision ID: 011_add_edits_and_annotations
Revises: 010_add_dim_set_is_shared
Create Date: 2026-05-15
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011_add_edits_and_annotations"
down_revision: Union[str, None] = "010_add_dim_set_is_shared"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_item_edits",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("reading_item_id", sa.Integer(), sa.ForeignKey("reading_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edited_content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.UniqueConstraint("reading_item_id", "owner_user_id", name="uq_rie_item_owner"),
    )
    op.create_index("idx_rie_reading_item", "reading_item_edits", ["reading_item_id"])
    op.create_index("idx_rie_owner", "reading_item_edits", ["owner_user_id"])

    op.create_table(
        "annotations",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_id", sa.String(), nullable=False),
        sa.Column("bib_entry_id", sa.String(), sa.ForeignKey("bib_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=True),
        sa.Column("char_end", sa.Integer(), nullable=True),
        sa.Column("is_ai_generated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("color", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.CheckConstraint(
            "source_type IN ('compare_card','ai_summary','library_note')",
            name="ck_annotations_source_type",
        ),
    )
    op.create_index("idx_annotations_owner", "annotations", ["owner_user_id"])
    op.create_index("idx_annotations_source", "annotations", ["source_type", "source_id"])
    op.create_index("idx_annotations_bib", "annotations", ["bib_entry_id"])

    op.drop_constraint("ck_prompt_templates_type", "prompt_templates", type_="check")
    op.create_check_constraint(
        "ck_prompt_templates_type",
        "prompt_templates",
        "prompt_type IN ('quant','qual','long','filter','compare')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_prompt_templates_type", "prompt_templates", type_="check")
    op.create_check_constraint(
        "ck_prompt_templates_type",
        "prompt_templates",
        "prompt_type IN ('quant','qual','long','filter')",
    )
    op.drop_index("idx_annotations_bib", "annotations")
    op.drop_index("idx_annotations_source", "annotations")
    op.drop_index("idx_annotations_owner", "annotations")
    op.drop_table("annotations")
    op.drop_index("idx_rie_owner", "reading_item_edits")
    op.drop_index("idx_rie_reading_item", "reading_item_edits")
    op.drop_table("reading_item_edits")
```

- [ ] **Step 2: 验证迁移脚本**

Run: `cd backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; cfg = Config('alembic.ini'); sd = ScriptDirectory.from_config(cfg); print('heads:', sd.get_heads())"`

Expected: `heads: ['011_add_edits_and_annotations']`

---

## Task 3: 注册 compare 提示词类型 + 默认提示词文件

**Files:**
- Modify: `backend/prompt_registry.py`
- Create: `prompts/compare/ai_summary.md`

- [ ] **Step 1: 在 `prompt_registry.py` 的 `PROMPT_TYPE_LABELS` 中新增 `compare`**

在 `"filter": "文献筛选",` 后面加：

```python
    "compare": "对比分析",
```

- [ ] **Step 2: 在 `PROMPT_REGISTRY` 中新增 `compare` 类型**

在 `"filter": {...}` 块之后加：

```python
    "compare": {
        "ai_summary": {
            "title": "AI 文本总结",
            "file_path": "prompts/compare/ai_summary.md",
        },
    },
```

- [ ] **Step 3: 在 `get_builtin_fallback` 函数中添加 compare 分支**

在 `if prompt_type == "qual":` 块之后加：

```python
    if prompt_type == "compare":
        return "你是一位学术文本总结助手。请将用户选中的学术文本片段总结为一句话。要求：1.保留核心信息 2.语言简洁，不超过50个汉字 3.使用学术语言 4.不要添加原文中没有的信息"
```

- [ ] **Step 4: 创建默认提示词文件 `prompts/compare/ai_summary.md`**

```
你是一位学术文本总结助手。请将用户选中的学术文本片段总结为一句话。

要求：
1. 保留核心信息（研究对象、方法、结论、关键数据等）
2. 语言简洁，不超过 50 个汉字
3. 使用学术语言，避免口语化
4. 不要添加原文中没有的信息

选中的文本：
{selected_text}
```

- [ ] **Step 5: 验证注册正确**

Run: `cd backend && python -c "from prompt_registry import PROMPT_TYPE_LABELS, PROMPT_REGISTRY; print('types:', list(PROMPT_TYPE_LABELS.keys())); print('compare slots:', list(PROMPT_REGISTRY.get('compare', {}).keys()))"`

Expected: `types: ['quant', 'qual', 'long', 'filter', 'compare']` 和 `compare slots: ['ai_summary']`

---

## Task 4: 扩展 build_compare_response — 返回 reading_item_id / edit / annotations

**Files:**
- Modify: `backend/routers/compare.py`

这一步让 `/api/compare/reading-data` 返回前端 AnswerCard 所需的 `reading_item_id`、`edit`、`annotations` 字段。

- [ ] **Step 1: 在 compare.py 顶部新增 import**

在现有 import 行中追加：

```python
from db.models import ReadingItemEdit, Annotation
```

（如果已在 `from db.models import ...` 行中则添加到导入列表）

- [ ] **Step 2: 修改 `get_reading_data` 端点（约 L268），在调用 `build_compare_response` 前批量查询 edits 和 annotations**

在 `return await build_compare_response(...)` 之前插入查询：

将：

```python
    return await build_compare_response(mode, bib_entries_items, bib_entries, user.id, db)
```

改为：

```python
    all_item_ids = [item.id for items in bib_entries_items.values() for item in items]

    edit_rows = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.owner_user_id == user.id,
                ReadingItemEdit.reading_item_id.in_(all_item_ids),
            )
        )
    ).scalars().all()
    edits_map: dict[int, ReadingItemEdit] = {e.reading_item_id: e for e in edit_rows}

    ann_rows = (
        await db.execute(
            select(Annotation).where(
                Annotation.owner_user_id == user.id,
                Annotation.source_type.in_(["compare_card", "ai_summary"]),
                Annotation.source_id.in_([str(iid) for iid in all_item_ids]),
            )
        )
    ).scalars().all()
    annotations_map: dict[int, list] = {}
    for ann in ann_rows:
        key = int(ann.source_id)
        annotations_map.setdefault(key, []).append(ann)

    return await build_compare_response(
        mode, bib_entries_items, bib_entries, user.id, db,
        edits_map=edits_map,
        annotations_map=annotations_map,
    )
```

- [ ] **Step 3: 修改 `build_compare_response` 函数签名，接受 edits_map 和 annotations_map**

将函数签名从：

```python
async def build_compare_response(
    mode: str,
    bib_entries_items: dict[str, list[ReadingItem]],
    bib_entries: dict[str, BibEntry],
    user_id: int,
    db: AsyncSession,
):
```

改为：

```python
async def build_compare_response(
    mode: str,
    bib_entries_items: dict[str, list[ReadingItem]],
    bib_entries: dict[str, BibEntry],
    user_id: int,
    db: AsyncSession,
    *,
    edits_map: dict[int, ReadingItemEdit] | None = None,
    annotations_map: dict[int, list] | None = None,
):
```

- [ ] **Step 4: 在 long 模式的 dim_dict 构建中追加 edit / annotations / reading_item_id**

在 `build_compare_response` 内部，long 模式的 `dim_dict` 构建代码（约 L206-214），当前为：

```python
                dim_dict = {
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                }
```

改为：

```python
                dim_dict: dict = {
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                }
                if edits_map and item.id in edits_map:
                    dim_dict["edit"] = {
                        "edited_content": edits_map[item.id].edited_content,
                        "updated_at": edits_map[item.id].updated_at.isoformat() if edits_map[item.id].updated_at else None,
                    }
                if annotations_map and item.id in annotations_map:
                    dim_dict["annotations"] = [
                        {
                            "id": a.id,
                            "source_type": a.source_type,
                            "selected_text": a.selected_text,
                            "note": a.note,
                            "char_start": a.char_start,
                            "char_end": a.char_end,
                            "is_ai_generated": a.is_ai_generated,
                            "color": a.color,
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in annotations_map[item.id]
                    ]
```

- [ ] **Step 5: 在 quant/qual 模式的 subQuestions 构建中追加 edit / annotations**

在 `build_compare_response` 内部，非 long 模式的 subQuestions 追加代码（约 L222-227），当前为：

```python
                steps[step_name]["subQuestions"].append({
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                })
```

改为：

```python
                sq: dict = {
                    "id": item.item_key,
                    "label": item.item_label,
                    "content": item.content or "",
                    "reading_item_id": item.id,
                }
                if edits_map and item.id in edits_map:
                    sq["edit"] = {
                        "edited_content": edits_map[item.id].edited_content,
                        "updated_at": edits_map[item.id].updated_at.isoformat() if edits_map[item.id].updated_at else None,
                    }
                if annotations_map and item.id in annotations_map:
                    sq["annotations"] = [
                        {
                            "id": a.id,
                            "source_type": a.source_type,
                            "selected_text": a.selected_text,
                            "note": a.note,
                            "char_start": a.char_start,
                            "char_end": a.char_end,
                            "is_ai_generated": a.is_ai_generated,
                            "color": a.color,
                            "created_at": a.created_at.isoformat() if a.created_at else None,
                        }
                        for a in annotations_map[item.id]
                    ]
                steps[step_name]["subQuestions"].append(sq)
```

- [ ] **Step 6: 验证语法正确**

Run: `cd backend && python -c "from routers.compare import router; print('routes:', len(router.routes))"`

Expected: 输出数字（当前应为 7），无报错

---

## Task 5: 新增编辑覆盖 API（PUT / DELETE）

**Files:**
- Modify: `backend/routers/compare.py`

前端调用方式：
- `PUT /api/compare/reading-items/{item_id}/edit` body: `{ edited_content: string }`
- `DELETE /api/compare/reading-items/{item_id}/edit`

- [ ] **Step 1: 在 compare.py 末尾追加编辑覆盖端点**

在文件最后一个端点之后追加：

```python
@router.put("/reading-items/{item_id}/edit")
async def save_reading_item_edit(
    item_id: int,
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ri = await db.get(ReadingItem, item_id)
    if not ri or ri.owner_user_id != user.id:
        raise HTTPException(404, "ReadingItem not found")
    content = body.get("edited_content", "")
    existing = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.reading_item_id == item_id,
                ReadingItemEdit.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.edited_content = content
        existing.updated_at = datetime.now(UTC)
    else:
        db.add(ReadingItemEdit(
            reading_item_id=item_id,
            owner_user_id=user.id,
            edited_content=content,
        ))
    await db.commit()
    return {"ok": True}


@router.delete("/reading-items/{item_id}/edit")
async def delete_reading_item_edit(
    item_id: int,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ri = await db.get(ReadingItem, item_id)
    if not ri or ri.owner_user_id != user.id:
        raise HTTPException(404, "ReadingItem not found")
    existing = (
        await db.execute(
            select(ReadingItemEdit).where(
                ReadingItemEdit.reading_item_id == item_id,
                ReadingItemEdit.owner_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        await db.delete(existing)
        await db.commit()
    return {"ok": True}
```

- [ ] **Step 2: 验证路由注册**

Run: `cd backend && python -c "from routers.compare import router; [print(r.path, list(r.methods)) for r in router.routes]"`

Expected: 列表中包含 `/reading-items/{item_id}/edit` 的 PUT 和 DELETE

---

## Task 6: 新增点评 CRUD API + AI 总结 API

**Files:**
- Modify: `backend/routers/compare.py`

前端调用方式：
- `POST /api/compare/annotations` body: `{ source_type, source_id, selected_text, note, color, bib_entry_id?, char_start?, char_end? }`
- `GET /api/compare/annotations?source_type=&source_id=&is_ai=`
- `PUT /api/compare/annotations/{id}` body: `{ note?, color? }`
- `DELETE /api/compare/annotations/{id}`
- `POST /api/compare/ai-summary` body: `{ text, api_key, reading_item_id, bib_entry_id?, char_start?, char_end? }`

- [ ] **Step 1: 在 compare.py 末尾追加 annotations CRUD 端点**

```python
@router.post("/annotations")
async def create_annotation(
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann_id = str(uuid.uuid4())
    db.add(Annotation(
        id=ann_id,
        owner_user_id=user.id,
        source_type=body.get("source_type", "compare_card"),
        source_id=str(body.get("source_id", "")),
        bib_entry_id=body.get("bib_entry_id"),
        selected_text=body.get("selected_text"),
        note=body.get("note", ""),
        char_start=body.get("char_start"),
        char_end=body.get("char_end"),
        is_ai_generated=0,
        color=body.get("color"),
    ))
    await db.commit()
    return {"id": ann_id}


@router.get("/annotations")
async def list_annotations(
    source_type: Optional[str] = None,
    source_id: Optional[str] = None,
    is_ai: Optional[int] = None,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Annotation).where(Annotation.owner_user_id == user.id)
    if source_type:
        stmt = stmt.where(Annotation.source_type == source_type)
    if source_id:
        stmt = stmt.where(Annotation.source_id == source_id)
    if is_ai is not None:
        stmt = stmt.where(Annotation.is_ai_generated == is_ai)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": a.id,
            "source_type": a.source_type,
            "source_id": a.source_id,
            "selected_text": a.selected_text,
            "note": a.note,
            "char_start": a.char_start,
            "char_end": a.char_end,
            "is_ai_generated": a.is_ai_generated,
            "color": a.color,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in rows
    ]


@router.put("/annotations/{ann_id}")
async def update_annotation(
    ann_id: str,
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann = await db.get(Annotation, ann_id)
    if not ann or ann.owner_user_id != user.id:
        raise HTTPException(404, "Annotation not found")
    if "note" in body:
        ann.note = body["note"]
    if "color" in body:
        ann.color = body["color"]
    ann.updated_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}


@router.delete("/annotations/{ann_id}")
async def delete_annotation(
    ann_id: str,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    ann = await db.get(Annotation, ann_id)
    if not ann or ann.owner_user_id != user.id:
        raise HTTPException(404, "Annotation not found")
    await db.delete(ann)
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 2: 在 compare.py 末尾追加 AI 总结端点**

需要在文件顶部确认已有 `from backend.utils.api_key import validate_deepseek_key` 和 `import uuid`。

```python
@router.post("/ai-summary")
async def ai_summary(
    body: dict,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    text = body.get("text", "")
    api_key = body.get("api_key", "")
    reading_item_id = body.get("reading_item_id")

    if not text.strip() or not api_key:
        raise HTTPException(400, "text and api_key required")

    validate_deepseek_key(api_key)

    from prompt_service import get_prompt_payload
    payload = await get_prompt_payload(
        db, prompt_type="compare", prompt_key="ai_summary", user_id=user.id
    )
    prompt_text = payload.effective_content.replace("{selected_text}", text)

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=120.0)
    response = client.chat.completions.create(
        model="deepseek-v4-flash",
        extra_body={"thinking": {"type": "disabled"}},
        messages=[
            {"role": "system", "content": "你是一位学术文本总结助手。"},
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    summary = response.choices[0].message.content.strip()

    ann_id = str(uuid.uuid4())
    db.add(Annotation(
        id=ann_id,
        owner_user_id=user.id,
        source_type="ai_summary",
        source_id=str(reading_item_id) if reading_item_id else "",
        bib_entry_id=body.get("bib_entry_id"),
        selected_text=text,
        note=summary,
        char_start=body.get("char_start"),
        char_end=body.get("char_end"),
        is_ai_generated=1,
    ))
    await db.commit()

    return {"summary": summary, "annotation_id": ann_id}
```

- [ ] **Step 3: 验证全部路由注册**

Run: `cd backend && python -c "from routers.compare import router; [print(r.path, list(r.methods)) for r in router.routes]"`

Expected: 共 14 个端点，包含 `/annotations` 的 GET/POST/PUT/DELETE、`/ai-summary` 的 POST、`/reading-items/{item_id}/edit` 的 PUT/DELETE

---

## Task 7: 清理逻辑扩展

**Files:**
- Modify: `backend/cleanup.py`

- [ ] **Step 1: 在 cleanup.py 中补充 ReadingItemEdit 和 Annotation 的清理**

在过期清理函数（`cleanup_expired`）中，删 ReadingItem 之前先删关联的 ReadingItemEdit 和 Annotation。

在 `from db.models import ...` 行中追加 `ReadingItemEdit, Annotation`。

在删 expired ReadingItems 的循环中（约 L156），`await db.delete(job)` 之前插入对应清理逻辑。

类似地，在 `cleanup_normal_users` 中删 bib/reading_item 时也需级联清理 ReadingItemEdit 和 Annotation。具体位置：删除 ReadingItem 相关数据的代码块之前，加上：

```python
    await db.execute(sa_delete(ReadingItemEdit).where(ReadingItemEdit.owner_user_id.in_(normal_user_ids)))
    await db.execute(sa_delete(Annotation).where(Annotation.owner_user_id.in_(normal_user_ids)))
```

以及过期清理中：

```python
    await db.execute(sa_delete(ReadingItemEdit).where(ReadingItemEdit.reading_item_id.in_([item.id for item in expired_items])))
    await db.execute(sa_delete(Annotation).where(Annotation.source_id.in_([str(item.id) for item in expired_items])))
```

（注：具体位置和变量名需对照 cleanup.py 当前代码调整）

---

## Task 8: 提交 + 推送 + 远端验证

- [ ] **Step 1: 本地语法验证**

Run: `cd backend && python -c "from routers.compare import router; from db.models import ReadingItemEdit, Annotation; print('All OK, routes:', len(router.routes))"`

- [ ] **Step 2: 提交**

```bash
git add backend/db/models.py backend/migrations/versions/011_add_edits_and_annotations.py backend/prompt_registry.py prompts/compare/ai_summary.md backend/routers/compare.py backend/cleanup.py
git commit -m "feat: 对比页三按钮后端 — ReadingItemEdit/Annotation 模型 + 7个API端点 + reading-data 扩展"
```

- [ ] **Step 3: 推送**

```bash
git push origin online
```

- [ ] **Step 4: 远端部署后验证**

SSH 到服务器：

```bash
cd /root/.openclaw/workspace/deep-reading-agent
source venv/bin/activate
cd backend && alembic upgrade head   # 创建新表
cd .. && bash deploy.sh              # 完整部署
```

验证端点存在：

```bash
curl -s http://localhost:8000/docs | grep -o "annotations\|reading-items.*edit\|ai-summary"
```

前端刷新对比页，确认三按钮显示、编辑/点评/AI总结功能正常。

---

## Self-Review

**1. Spec 覆盖检查：**

| Spec 条目 | 对应 Task |
|-----------|-----------|
| `reading_item_edits` 表 | Task 1 (models) + Task 2 (migration) |
| `annotations` 表 | Task 1 (models) + Task 2 (migration) |
| `prompt_templates` CHECK 扩展 | Task 1 (models) + Task 2 (migration) |
| `compare.ai_summary` 提示词注册 | Task 3 |
| 默认提示词文件 | Task 3 |
| 编辑覆盖 PUT/DELETE API | Task 5 |
| 点评 CRUD API | Task 6 |
| AI 总结 API | Task 6 |
| reading-data 响应扩展 | Task 4 |
| 清理逻辑 | Task 7 |

**2. Placeholder 扫描：** 无 TBD/TODO，所有代码块完整。

**3. 类型一致性：**
- 前端 AnswerCard 期望的字段：`reading_item_id`(int)、`edit.edited_content`(str)、`edit.updated_at`(str)、`annotations[].id/selected_text/note/char_start/char_end/is_ai_generated/color/created_at` — 后端响应字段名和类型完全匹配。
- 前端 API 调用路径：`/api/compare/annotations`、`/api/compare/reading-items/{id}/edit`、`/api/compare/ai-summary` — 后端端点路径完全匹配。
