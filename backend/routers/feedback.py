"""User feedback APIs and admin feedback management."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import current_user, require_admin
from db import get_db
from db.models import AdminAuditLog, FeedbackEvent, User, UserFeedback

router = APIRouter()

FEEDBACK_TYPES = {"bug", "feature", "question", "data_issue", "translation", "reading_quality", "other"}
FEEDBACK_STATUSES = {"open", "triaged", "in_progress", "resolved", "closed", "reopened"}
FEEDBACK_PRIORITIES = {"P0", "P1", "P2", "P3"}


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class FeedbackCreateRequest(BaseModel):
    feedback_type: str = Field(pattern="^(bug|feature|question|data_issue|translation|reading_quality|other)$")
    title: str = Field(min_length=2, max_length=160)
    content: str = Field(min_length=2, max_length=5000)
    route: Optional[str] = Field(default=None, max_length=300)
    app_version: Optional[str] = Field(default=None, max_length=80)
    related_job_id: Optional[str] = Field(default=None, max_length=80)
    related_file_id: Optional[str] = Field(default=None, max_length=80)
    related_bib_entry_id: Optional[str] = Field(default=None, max_length=80)
    related_artifact_id: Optional[int] = None


class FeedbackUpdateRequest(BaseModel):
    status: Optional[str] = Field(
        default=None,
        pattern="^(open|triaged|in_progress|resolved|closed|reopened)$",
    )
    priority: Optional[str] = Field(default=None, pattern="^(P0|P1|P2|P3)$")
    assigned_admin_id: Optional[int] = None
    public_reply: Optional[str] = Field(default=None, max_length=5000)
    internal_note: Optional[str] = Field(default=None, max_length=5000)


class FeedbackEventCreateRequest(BaseModel):
    note: str = Field(min_length=1, max_length=5000)
    public: bool = False


class FeedbackOwnerResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    role: str


class FeedbackEventResponse(BaseModel):
    id: int
    actor_user_id: Optional[int]
    event_type: str
    old_value: Optional[str]
    new_value: Optional[str]
    note: Optional[str]
    created_at: datetime


class FeedbackResponse(BaseModel):
    id: int
    owner_user_id: int
    owner: Optional[FeedbackOwnerResponse] = None
    feedback_type: str
    title: str
    content: str
    status: str
    priority: str
    route: Optional[str]
    app_version: Optional[str]
    related_job_id: Optional[str]
    related_file_id: Optional[str]
    related_bib_entry_id: Optional[str]
    related_artifact_id: Optional[int]
    assigned_admin_id: Optional[int]
    public_reply: Optional[str]
    internal_note: Optional[str] = None
    resolved_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    events: list[FeedbackEventResponse] = []


class AdminFeedbackListResponse(BaseModel):
    items: list[FeedbackResponse]
    total: int
    open_count: int


def build_owner_response(user: User | None) -> FeedbackOwnerResponse | None:
    if user is None:
        return None
    return FeedbackOwnerResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
    )


def build_event_response(event: FeedbackEvent) -> FeedbackEventResponse:
    return FeedbackEventResponse(
        id=event.id,
        actor_user_id=event.actor_user_id,
        event_type=event.event_type,
        old_value=event.old_value,
        new_value=event.new_value,
        note=event.note,
        created_at=event.created_at,
    )


def build_feedback_response(
    feedback: UserFeedback,
    *,
    owner: User | None = None,
    events: list[FeedbackEvent] | None = None,
    include_internal: bool = False,
) -> FeedbackResponse:
    return FeedbackResponse(
        id=feedback.id,
        owner_user_id=feedback.owner_user_id,
        owner=build_owner_response(owner),
        feedback_type=feedback.feedback_type,
        title=feedback.title,
        content=feedback.content,
        status=feedback.status,
        priority=feedback.priority,
        route=feedback.route,
        app_version=feedback.app_version,
        related_job_id=feedback.related_job_id,
        related_file_id=feedback.related_file_id,
        related_bib_entry_id=feedback.related_bib_entry_id,
        related_artifact_id=feedback.related_artifact_id,
        assigned_admin_id=feedback.assigned_admin_id,
        public_reply=feedback.public_reply,
        internal_note=feedback.internal_note if include_internal else None,
        resolved_at=feedback.resolved_at,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
        events=[build_event_response(event) for event in (events or [])],
    )


async def add_feedback_event(
    db: AsyncSession,
    *,
    feedback_id: int,
    actor_user_id: int | None,
    event_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
    note: str | None = None,
) -> None:
    db.add(
        FeedbackEvent(
            feedback_id=feedback_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            note=note,
            created_at=utcnow_naive(),
        )
    )


async def add_admin_audit(
    db: AsyncSession,
    *,
    admin_user_id: int,
    action: str,
    target_type: str,
    target_id: str | None,
    summary: str,
    payload: dict | None = None,
) -> None:
    db.add(
        AdminAuditLog(
            admin_user_id=admin_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            summary=summary,
            payload_json=json.dumps(payload or {}, ensure_ascii=False),
            created_at=utcnow_naive(),
        )
    )


@router.post("", response_model=FeedbackResponse)
async def create_feedback(
    payload: FeedbackCreateRequest,
    request: Request,
    user_agent: Optional[str] = Header(default=None),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    feedback = UserFeedback(
        owner_user_id=user.id,
        feedback_type=payload.feedback_type,
        title=payload.title.strip(),
        content=payload.content.strip(),
        route=payload.route,
        user_agent=user_agent or request.headers.get("user-agent"),
        app_version=payload.app_version,
        related_job_id=payload.related_job_id,
        related_file_id=payload.related_file_id,
        related_bib_entry_id=payload.related_bib_entry_id,
        related_artifact_id=payload.related_artifact_id,
        created_at=utcnow_naive(),
        updated_at=utcnow_naive(),
    )
    db.add(feedback)
    await db.flush()
    await add_feedback_event(
        db,
        feedback_id=feedback.id,
        actor_user_id=user.id,
        event_type="created",
        note="用户提交反馈",
    )
    await db.commit()
    await db.refresh(feedback)
    return build_feedback_response(feedback)


@router.get("/my", response_model=list[FeedbackResponse])
async def list_my_feedback(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
) -> list[FeedbackResponse]:
    feedback_items = (
        await db.execute(
            select(UserFeedback)
            .where(UserFeedback.owner_user_id == user.id)
            .order_by(desc(UserFeedback.updated_at), desc(UserFeedback.id))
        )
    ).scalars().all()
    return [build_feedback_response(item) for item in feedback_items]


@router.get("/admin", response_model=AdminFeedbackListResponse)
async def admin_list_feedback(
    status_filter: Optional[str] = None,
    priority: Optional[str] = None,
    feedback_type: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 100,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminFeedbackListResponse:
    del admin
    conditions = []
    if status_filter and status_filter != "all":
        if status_filter not in FEEDBACK_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的反馈状态。")
        conditions.append(UserFeedback.status == status_filter)
    if priority and priority != "all":
        if priority not in FEEDBACK_PRIORITIES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的优先级。")
        conditions.append(UserFeedback.priority == priority)
    if feedback_type and feedback_type != "all":
        if feedback_type not in FEEDBACK_TYPES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的反馈类型。")
        conditions.append(UserFeedback.feedback_type == feedback_type)
    if q:
        keyword = f"%{q.strip()}%"
        conditions.append(or_(UserFeedback.title.like(keyword), UserFeedback.content.like(keyword)))

    query = select(UserFeedback, User).join(User, User.id == UserFeedback.owner_user_id)
    count_query = select(func.count()).select_from(UserFeedback)
    if conditions:
        query = query.where(*conditions)
        count_query = count_query.where(*conditions)

    rows = (
        await db.execute(
            query.order_by(desc(UserFeedback.updated_at), desc(UserFeedback.id)).limit(max(1, min(limit, 300)))
        )
    ).all()
    total = (await db.execute(count_query)).scalar_one()
    open_count = (
        await db.execute(
            select(func.count()).select_from(UserFeedback).where(
                UserFeedback.status.in_(["open", "triaged", "in_progress", "reopened"])
            )
        )
    ).scalar_one()
    return AdminFeedbackListResponse(
        items=[build_feedback_response(feedback, owner=owner, include_internal=True) for feedback, owner in rows],
        total=total,
        open_count=open_count,
    )


@router.get("/admin/{feedback_id}", response_model=FeedbackResponse)
async def admin_get_feedback(
    feedback_id: int,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    row = (
        await db.execute(
            select(UserFeedback, User)
            .join(User, User.id == UserFeedback.owner_user_id)
            .where(UserFeedback.id == feedback_id)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在。")
    feedback, owner = row
    events = (
        await db.execute(
            select(FeedbackEvent)
            .where(FeedbackEvent.feedback_id == feedback_id)
            .order_by(FeedbackEvent.created_at.asc(), FeedbackEvent.id.asc())
        )
    ).scalars().all()
    return build_feedback_response(feedback, owner=owner, events=events, include_internal=True)


@router.patch("/admin/{feedback_id}", response_model=FeedbackResponse)
async def admin_update_feedback(
    feedback_id: int,
    payload: FeedbackUpdateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    feedback = await db.get(UserFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在。")

    changed = False
    now = utcnow_naive()
    if payload.status is not None and payload.status != feedback.status:
        old = feedback.status
        feedback.status = payload.status
        feedback.resolved_at = now if payload.status in {"resolved", "closed"} else None
        await add_feedback_event(
            db,
            feedback_id=feedback.id,
            actor_user_id=admin.id,
            event_type="status_changed",
            old_value=old,
            new_value=payload.status,
        )
        changed = True

    if payload.priority is not None and payload.priority != feedback.priority:
        old = feedback.priority
        feedback.priority = payload.priority
        await add_feedback_event(
            db,
            feedback_id=feedback.id,
            actor_user_id=admin.id,
            event_type="priority_changed",
            old_value=old,
            new_value=payload.priority,
        )
        changed = True

    if payload.assigned_admin_id is not None and payload.assigned_admin_id != feedback.assigned_admin_id:
        old = str(feedback.assigned_admin_id) if feedback.assigned_admin_id is not None else None
        feedback.assigned_admin_id = payload.assigned_admin_id
        await add_feedback_event(
            db,
            feedback_id=feedback.id,
            actor_user_id=admin.id,
            event_type="assigned",
            old_value=old,
            new_value=str(payload.assigned_admin_id),
        )
        changed = True

    if payload.public_reply is not None and payload.public_reply != (feedback.public_reply or ""):
        feedback.public_reply = payload.public_reply.strip() or None
        await add_feedback_event(
            db,
            feedback_id=feedback.id,
            actor_user_id=admin.id,
            event_type="public_replied",
            note=feedback.public_reply,
        )
        changed = True

    if payload.internal_note is not None and payload.internal_note != (feedback.internal_note or ""):
        feedback.internal_note = payload.internal_note.strip() or None
        await add_feedback_event(
            db,
            feedback_id=feedback.id,
            actor_user_id=admin.id,
            event_type="commented",
            note=feedback.internal_note,
        )
        changed = True

    if not changed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="没有可更新的字段。")

    feedback.updated_at = now
    await add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="update_feedback",
        target_type="feedback",
        target_id=str(feedback.id),
        summary=f"更新反馈 #{feedback.id}",
        payload=payload.model_dump(exclude_none=True),
    )
    await db.commit()
    await db.refresh(feedback)
    owner = await db.get(User, feedback.owner_user_id)
    return build_feedback_response(feedback, owner=owner, include_internal=True)


@router.post("/admin/{feedback_id}/events", response_model=FeedbackResponse)
async def admin_add_feedback_event(
    feedback_id: int,
    payload: FeedbackEventCreateRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    feedback = await db.get(UserFeedback, feedback_id)
    if feedback is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="反馈不存在。")

    note = payload.note.strip()
    if payload.public:
        feedback.public_reply = note
        event_type = "public_replied"
    else:
        feedback.internal_note = note
        event_type = "commented"
    feedback.updated_at = utcnow_naive()
    await add_feedback_event(
        db,
        feedback_id=feedback.id,
        actor_user_id=admin.id,
        event_type=event_type,
        note=note,
    )
    await add_admin_audit(
        db,
        admin_user_id=admin.id,
        action="comment_feedback",
        target_type="feedback",
        target_id=str(feedback.id),
        summary=f"评论反馈 #{feedback.id}",
        payload={"public": payload.public},
    )
    await db.commit()
    await db.refresh(feedback)
    owner = await db.get(User, feedback.owner_user_id)
    events = (
        await db.execute(
            select(FeedbackEvent)
            .where(FeedbackEvent.feedback_id == feedback_id)
            .order_by(FeedbackEvent.created_at.asc(), FeedbackEvent.id.asc())
        )
    ).scalars().all()
    return build_feedback_response(feedback, owner=owner, events=events, include_internal=True)
