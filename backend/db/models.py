"""SQLAlchemy 2.0 ORM models for the multi-user system.

Mirrors the schema described in docs/DATABASE_SCHEMA.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


# --------------------------------------------------------------------------
# Account & invitations
# --------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('admin','vip','normal')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    email: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    vip_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    token_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_users_role", User.role)


class InviteCode(Base):
    __tablename__ = "invite_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_invite_codes_code", InviteCode.code)


class UserSettings(Base):
    """Reserved for future preferences. v1 unused."""
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferences_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


class UserFeedback(Base):
    __tablename__ = "user_feedback"
    __table_args__ = (
        CheckConstraint(
            "feedback_type IN ('bug','feature','question','data_issue','translation','reading_quality','other')",
            name="ck_user_feedback_type",
        ),
        CheckConstraint(
            "status IN ('open','triaged','in_progress','resolved','closed','reopened')",
            name="ck_user_feedback_status",
        ),
        CheckConstraint(
            "priority IN ('P0','P1','P2','P3')",
            name="ck_user_feedback_priority",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    feedback_type: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open", server_default="open")
    priority: Mapped[str] = mapped_column(String, nullable=False, default="P3", server_default="P3")
    route: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    app_version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    related_job_id: Mapped[Optional[str]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    related_file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"), nullable=True)
    related_bib_entry_id: Mapped[Optional[str]] = mapped_column(ForeignKey("bib_entries.id"), nullable=True)
    related_artifact_id: Mapped[Optional[int]] = mapped_column(ForeignKey("artifacts.id"), nullable=True)
    assigned_admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    public_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    internal_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_user_feedback_owner", UserFeedback.owner_user_id)
Index("idx_user_feedback_status", UserFeedback.status)
Index("idx_user_feedback_priority", UserFeedback.priority)
Index("idx_user_feedback_created", UserFeedback.created_at)
Index("idx_user_feedback_job", UserFeedback.related_job_id)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('created','status_changed','priority_changed','assigned','commented','public_replied','closed','reopened')",
            name="ck_feedback_events_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feedback_id: Mapped[int] = mapped_column(
        ForeignKey("user_feedback.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_feedback_events_feedback", FeedbackEvent.feedback_id)
Index("idx_feedback_events_actor", FeedbackEvent.actor_user_id)


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_admin_audit_admin", AdminAuditLog.admin_user_id)
Index("idx_admin_audit_target", AdminAuditLog.target_type, AdminAuditLog.target_id)
Index("idx_admin_audit_created", AdminAuditLog.created_at)


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','archived')",
            name="ck_agent_sessions_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", server_default="active")
    last_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_agent_sessions_owner", AgentSession.owner_user_id)
Index("idx_agent_sessions_updated", AgentSession.updated_at)
Index("idx_agent_sessions_expires", AgentSession.expires_at)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user','assistant','tool','system')",
            name="ck_agent_messages_role",
        ),
        CheckConstraint(
            "event_type IN ('message','tool_call','tool_result','proposal','confirmation','error')",
            name="ck_agent_messages_event_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_agent_messages_session", AgentMessage.session_id)
Index("idx_agent_messages_owner", AgentMessage.owner_user_id)
Index("idx_agent_messages_expires", AgentMessage.expires_at)


class AgentActionProposal(Base):
    __tablename__ = "agent_action_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','confirmed','rejected','expired','executed','failed')",
            name="ck_agent_proposals_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    arguments_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    preview_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    result_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_agent_proposals_session", AgentActionProposal.session_id)
Index("idx_agent_proposals_status", AgentActionProposal.status)
Index("idx_agent_proposals_owner", AgentActionProposal.owner_user_id)
Index("idx_agent_proposals_expires", AgentActionProposal.expires_at)


# --------------------------------------------------------------------------
# Prompt templates
# --------------------------------------------------------------------------

class PromptTemplate(Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('system','user')",
            name="ck_prompt_templates_scope",
        ),
        CheckConstraint(
            "prompt_type IN ('quant','qual','long','filter','compare','synthesis','ai_template','translation','library_chat','card_note')",
            name="ck_prompt_templates_type",
        ),
        UniqueConstraint(
            "owner_user_id",
            "prompt_type",
            "prompt_key",
            name="uq_prompt_templates_owner_type_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    scope: Mapped[str] = mapped_column(String, nullable=False)
    prompt_type: Mapped[str] = mapped_column(String, nullable=False)
    prompt_key: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_prompt_templates_scope", PromptTemplate.scope)
Index("idx_prompt_templates_owner", PromptTemplate.owner_user_id)
Index("idx_prompt_templates_type_key", PromptTemplate.prompt_type, PromptTemplate.prompt_key)


# --------------------------------------------------------------------------
# Files & batches
# --------------------------------------------------------------------------

class UploadBatch(Base):
    __tablename__ = "upload_batches"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('single','folder','multi_select')",
            name="ck_upload_batches_source_type",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    total_files: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_upload_batches_owner", UploadBatch.owner_user_id)


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        CheckConstraint(
            "file_type IN ('pdf','bibliography','markdown','docx','txt')",
            name="ck_files_file_type",
        ),
        UniqueConstraint("owner_user_id", "md5", name="uq_files_owner_md5"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False)
    file_type: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    md5: Mapped[str] = mapped_column(String, nullable=False)
    batch_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("upload_batches.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_files_owner", File.owner_user_id)
Index("idx_files_expires", File.expires_at)
Index("idx_files_batch", File.batch_id)


# --------------------------------------------------------------------------
# Jobs (filter / reading_* / compare / synthesis)
# --------------------------------------------------------------------------

class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('filter','reading_long','reading_quant','reading_qual',"
            "'compare','synthesis','reference_trace','translation','translate_abstracts')",
            name="ck_jobs_job_type",
        ),
        CheckConstraint(
            "status IN ('pending','running','success','failed','canceled')",
            name="ck_jobs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending", server_default="pending")
    input_file_id: Mapped[Optional[str]] = mapped_column(ForeignKey("files.id"), nullable=True)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}", server_default="{}")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    current_stage: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    batch_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_jobs_owner", Job.owner_user_id)
Index("idx_jobs_status", Job.status)
Index("idx_jobs_type", Job.job_type)
Index("idx_jobs_expires", Job.expires_at)


# --------------------------------------------------------------------------
# Bibliography entries (the hub)
# --------------------------------------------------------------------------

class BibEntry(Base):
    __tablename__ = "bib_entries"
    __table_args__ = (
        CheckConstraint(
            "source_db IN ('wos','cnki','scopus','manual','pdf_extracted',"
            "'md_extracted','other')",
            name="ck_bib_source_db",
        ),
        CheckConstraint(
            "reading_status IN ('none','has_pdf','reading','read')",
            name="ck_bib_reading_status",
        ),
        CheckConstraint(
            "metadata_completeness IN ('full','partial','minimal')",
            name="ck_bib_metadata_completeness",
        ),
        CheckConstraint(
            "language IS NULL OR language IN ('en','zh','other')",
            name="ck_bib_language",
        ),
        UniqueConstraint("owner_user_id", "dedup_key", name="uq_bib_dedup"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Bibliographic metadata
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    abstract_cn: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)
    keywords_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    venue_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    citation_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    volume: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pages: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Provenance
    source_db: Mapped[str] = mapped_column(String, nullable=False)
    source_filter_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("jobs.id"), nullable=True
    )

    # Linked physical file (PDF or MD)
    source_file_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    markdown_source_file_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )

    # User annotations
    user_tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    user_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_pinned: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # State
    reading_status: Mapped[str] = mapped_column(
        String, nullable=False, default="none", server_default="none"
    )
    metadata_completeness: Mapped[str] = mapped_column(
        String, nullable=False, default="partial", server_default="partial"
    )

    # Dedup
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_bib_owner", BibEntry.owner_user_id)
Index("idx_bib_status", BibEntry.reading_status)
Index("idx_bib_doi", BibEntry.doi)
Index("idx_bib_expires", BibEntry.expires_at)
Index("idx_bib_markdown_source", BibEntry.markdown_source_file_id)


# --------------------------------------------------------------------------
# Many-to-many associations
# --------------------------------------------------------------------------

class BibFilterLink(Base):
    """Records that a bib_entry was scored by a filter job."""
    __tablename__ = "bib_filter_links"
    __table_args__ = (
        UniqueConstraint("bib_entry_id", "filter_job_id", name="uq_bib_filter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    filter_job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    passed: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Optional[float]] = mapped_column(nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_bfl_bib", BibFilterLink.bib_entry_id)
Index("idx_bfl_filter", BibFilterLink.filter_job_id)


class BibReference(Base):
    __tablename__ = "bib_references"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    reference_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    authors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    journal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    volume: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    issue: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    pages: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dedup_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    matched_bib_entry_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("bib_entries.id"),
        nullable=True,
    )
    match_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    match_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_bib_refs_owner", BibReference.owner_user_id)
Index("idx_bib_refs_source_bib", BibReference.source_bib_entry_id)
Index("idx_bib_refs_source_job", BibReference.source_job_id)
Index("idx_bib_refs_matched_bib", BibReference.matched_bib_entry_id)
Index("idx_bib_refs_doi", BibReference.doi)
Index("idx_bib_refs_dedup", BibReference.dedup_key)


class BibReferenceCitation(Base):
    __tablename__ = "bib_reference_citations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    bib_reference_id: Mapped[str] = mapped_column(
        ForeignKey("bib_references.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_job_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    citation_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    page_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    section_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    paragraph_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    quote_text: Mapped[str] = mapped_column(Text, nullable=False)
    quote_text_zh: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    char_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    match_method: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_brc_owner", BibReferenceCitation.owner_user_id)
Index("idx_brc_source_bib", BibReferenceCitation.source_bib_entry_id)
Index("idx_brc_reference", BibReferenceCitation.bib_reference_id)
Index("idx_brc_source_job", BibReferenceCitation.source_job_id)


class JobBibEntry(Base):
    """Associates a job (reading/compare/synthesis) with one or more bib entries."""
    __tablename__ = "job_bib_entries"
    __table_args__ = (
        CheckConstraint(
            "role IN ('target','compare_member','synthesis_member','reference_source')",
            name="ck_jbe_role",
        ),
        UniqueConstraint("job_id", "bib_entry_id", "role", name="uq_jbe_unique"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


Index("idx_jbe_job", JobBibEntry.job_id)
Index("idx_jbe_bib", JobBibEntry.bib_entry_id)


# --------------------------------------------------------------------------
# Structured reading outputs
# --------------------------------------------------------------------------

class ReadingItem(Base):
    """Structured reading result items for compare/library queries."""
    __tablename__ = "reading_items"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('long','quant','qual')",
            name="ck_reading_items_mode",
        ),
        CheckConstraint(
            "section_type IN ('dimension','step','subquestion','custom')",
            name="ck_reading_items_section_type",
        ),
        UniqueConstraint("job_id", "item_key", name="uq_reading_items_job_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String, nullable=False)
    section_type: Mapped[str] = mapped_column(String, nullable=False)
    parent_key: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    item_key: Mapped[str] = mapped_column(String, nullable=False)
    item_label: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_reading_items_owner", ReadingItem.owner_user_id)
Index("idx_reading_items_bib", ReadingItem.bib_entry_id)
Index("idx_reading_items_job", ReadingItem.job_id)
Index("idx_reading_items_mode", ReadingItem.mode)
Index("idx_reading_items_parent", ReadingItem.parent_key)


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


class CardNote(Base):
    __tablename__ = "card_notes"
    __table_args__ = (
        CheckConstraint(
            "source_version IN ('original','translated')",
            name="ck_card_notes_source_version",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    source_bib_entry_id: Mapped[str] = mapped_column(
        ForeignKey("bib_entries.id", ondelete="CASCADE"), nullable=False
    )
    source_version: Mapped[str] = mapped_column(String, nullable=False)
    source_markdown_file_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    source_translation_artifact_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("artifacts.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]", server_default="[]")
    selected_text: Mapped[str] = mapped_column(Text, nullable=False)
    context_before: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_after: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    user_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_card_notes_owner", CardNote.owner_user_id)
Index("idx_card_notes_bib", CardNote.source_bib_entry_id)
Index("idx_card_notes_created", CardNote.created_at)
Index("idx_card_notes_expires", CardNote.expires_at)
Index("idx_card_notes_translation", CardNote.source_translation_artifact_id)


# --------------------------------------------------------------------------
# Artifacts (job outputs)
# --------------------------------------------------------------------------

class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "artifact_type IN ('reading_step','reading_final','reading_extract',"
            "'filter_excel','compare_excel','compare_md','synthesis_md',"
            "'references_excel','references_with_citations_excel',"
            "'citation_trace_md','references_json','translation_md','translation_glossary')",
            name="ck_artifacts_artifact_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    storage_path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


Index("idx_artifacts_job", Artifact.job_id)
Index("idx_artifacts_owner", Artifact.owner_user_id)
Index("idx_artifacts_expires", Artifact.expires_at)


# --------------------------------------------------------------------------
# Dimension sets (user-customizable analysis dimensions)
# --------------------------------------------------------------------------

class DimensionSet(Base):
    __tablename__ = "dimension_sets"
    __table_args__ = (
        UniqueConstraint("owner_user_id", "name", name="uq_dim_sets_owner_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_system: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_shared: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_available_for_reading: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )

    owner = relationship("User", lazy="joined")


Index("idx_dim_sets_owner", DimensionSet.owner_user_id)
Index("idx_dim_sets_shared", DimensionSet.is_shared)
Index("idx_dim_sets_default", DimensionSet.owner_user_id, DimensionSet.is_default)


class DimensionItem(Base):
    __tablename__ = "dimension_items"
    __table_args__ = (
        UniqueConstraint("set_id", "dim_key", name="uq_dim_items_set_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    set_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_sets.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    group_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_dim_items_set", DimensionItem.set_id)
Index("idx_dim_items_builtin", DimensionItem.set_id, DimensionItem.is_builtin)


# --------------------------------------------------------------------------
# Dimension templates (system preset templates for template market)
# --------------------------------------------------------------------------

class DimensionTemplate(Base):
    __tablename__ = "dimension_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String, nullable=False)
    dim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_config: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_featured: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_dim_templates_category", DimensionTemplate.category)
Index("idx_dim_templates_featured", DimensionTemplate.is_featured)


class TemplateItem(Base):
    __tablename__ = "template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "dim_key", name="uq_template_items_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("dimension_templates.id", ondelete="CASCADE"), nullable=False
    )
    dim_key: Mapped[str] = mapped_column(String, nullable=False)
    dim_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt_content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    default_question: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    group_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )


Index("idx_template_items_template", TemplateItem.template_id)
