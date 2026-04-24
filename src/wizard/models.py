import datetime
import uuid as _uuid
from enum import Enum

from pydantic import ConfigDict, field_validator
from sqlalchemy import Column, ForeignKey, Integer, Text
from sqlmodel import Field, Relationship, SQLModel


class TimestampMixin(SQLModel):
    # SQLModel metaclass types model_config as SQLModelConfig — ConfigDict is valid at
    # runtime but mismatches the declared type. Upstream typing gap in sqlmodel.
    model_config = ConfigDict(  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]
        validate_default=True, validate_assignment=True
    )

    created_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, index=True
    )
    # onupdate fires via SQLAlchemy ORM only — not a DB-level trigger.
    # Raw SQL updates will not refresh this field.
    updated_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now,
        sa_column_kwargs={"onupdate": datetime.datetime.now},
        nullable=False,
    )

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def _strip_timezone(cls, v: object) -> object:
        # pydantic v2 with validate_default=True converts naive datetime.now()
        # to UTC-aware. SQLite stores and returns naive datetimes only.
        # Strip timezone so in-memory objects are always consistent with
        # what comes back from the DB after a round-trip.
        if isinstance(v, datetime.datetime) and v.tzinfo is not None:
            return v.replace(tzinfo=None)
        return v


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskCategory(str, Enum):
    ISSUE = "issue"
    BUG = "bug"
    INVESTIGATION = "investigation"


class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    ARCHIVED = "archived"


class MeetingCategory(str, Enum):
    STANDUP = "standup"
    PLANNING = "planning"
    RETRO = "retro"
    ONE_ON_ONE = "one_on_one"
    GENERAL = "general"


class NoteType(str, Enum):
    INVESTIGATION = "investigation"
    DECISION = "decision"
    DOCS = "docs"
    LEARNINGS = "learnings"
    SESSION_SUMMARY = "session_summary"


class MeetingTasks(SQLModel, table=True):
    meeting_id: int = Field(foreign_key="meeting.id", primary_key=True)
    task_id: int = Field(foreign_key="task.id", primary_key=True)


class Task(TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    due_date: datetime.datetime | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    category: TaskCategory = TaskCategory.ISSUE
    status: TaskStatus = TaskStatus.TODO
    meetings: list["Meeting"] = Relationship(
        back_populates="tasks", link_model=MeetingTasks
    )
    source_id: str | None = Field(
        default=None,
        index=True,
        unique=True,
        description="identifier of the external entity this task originated from",
    )
    source_type: str | None = Field(default=None, index=True)
    source_url: str | None = Field(default=None)
    artifact_id: str | None = Field(
        default_factory=lambda: str(_uuid.uuid4()), unique=True, index=True
    )
    persistence: str = Field(default="persistent")
    workspace: str | None = Field(default=None)


class Meeting(TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    content: str
    category: MeetingCategory = MeetingCategory.GENERAL
    summary: str | None = None
    tasks: list[Task] = Relationship(back_populates="meetings", link_model=MeetingTasks)
    source_id: str | None = Field(
        default=None,
        index=True,
        unique=True,
        description="identifier of the external entity this meeting relates to",
    )
    source_type: str | None = Field(default=None, index=True)
    source_url: str | None = Field(default=None)
    artifact_id: str | None = Field(
        default_factory=lambda: str(_uuid.uuid4()), unique=True, index=True
    )
    persistence: str = Field(default="persistent")
    workspace: str | None = Field(default=None)


class WizardSession(TimestampMixin, table=True):
    # SQLAlchemy types __tablename__ as declared_attr — string literal is valid at
    # runtime but mismatches the declared type. Upstream typing gap in sqlalchemy.
    __tablename__ = "wizardsession"  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    summary: str | None = None
    session_state: str | None = Field(
        default=None,
        description=(
            "JSON-serialised SessionState (see schemas.SessionState). "
            "Null until session_end (M2) populates it. "
            "Read by resume_session (M3)."
        ),
    )
    last_active_at: datetime.datetime | None = Field(default=None)
    closed_by: str | None = Field(
        default=None,
        description=(
            "Who closed this session: 'user' (session_end), "
            "'auto' (SessionCloser), or None (still open/abandoned)"
        ),
    )
    transcript_path: str | None = Field(
        default=None,
        description="Absolute path to the agent's conversation transcript file.",
    )
    agent: str | None = Field(
        default=None,
        description=(
            "Agent that produced this session: 'claude-code', 'codex', 'gemini', 'opencode'."
        ),
    )
    agent_session_id: str | None = Field(
        default=None,
        index=True,
        description="UUID assigned by the agent runtime (e.g. Claude Code session_id).",
    )
    continued_from_id: int | None = Field(
        default=None,
        index=True,
        description="Wizard session ID this session continues from (unclean prior close).",
    )
    active_mode: str | None = Field(
        default=None,
        description="Skill name of the active mode for this session, e.g. 'socratic-mentor'.",
    )
    is_synthesised: bool = Field(
        default=False,
        description="True once Synthesiser has processed transcript_path into notes.",
    )
    artifact_id: str | None = Field(
        default_factory=lambda: str(_uuid.uuid4()), unique=True, index=True
    )
    persistence: str = Field(default="ephemeral")
    workspace: str | None = Field(default=None)
    synthesis_status: str = Field(
        default="pending",
        description=(
            "Synthesis lifecycle: 'pending' | 'complete' | 'partial_failure'. "
            "partial_failure covers both partial success (some notes saved, some chunks failed) "
            "and total failure (no notes saved). Retry with wizard capture --close --session-id."
        ),
    )
    transcript_raw: str | None = Field(
        default=None,
        sa_type=Text(),
        description=(
            "Raw JSONL content of all synthesised transcript files, persisted at capture "
            "time so re-synthesis remains possible after the agent deletes the file."
        ),
    )
    notes: list["Note"] = Relationship(back_populates="session")


class Note(TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    note_type: NoteType = Field(index=True)
    content: str
    mental_model: str | None = Field(
        default=None,
        description=(
            "1-2 sentence causal abstraction written by the engineer. "
            "Soft cap 1500 chars at the application display layer."
        ),
    )
    session_id: int | None = Field(default=None, foreign_key="wizardsession.id")
    task_id: int | None = Field(default=None, foreign_key="task.id")
    meeting_id: int | None = Field(default=None, foreign_key="meeting.id")
    # Artifact identity layer (v3) — single anchor replacing polymorphic FKs above.
    # Old FKs are kept as a safety net during migration.
    artifact_id: str | None = Field(default=None, index=True)
    artifact_type: str | None = Field(default=None)  # 'task'|'session'|'meeting' — debug only
    # Synthesis provenance
    synthesis_content_hash: str | None = Field(default=None, index=True)
    synthesis_session_id: int | None = Field(default=None)
    transcript_offset_start: int | None = Field(default=None)
    transcript_offset_end: int | None = Field(default=None)
    synthesis_confidence: float | None = Field(default=None)
    source_note_ids: str | None = Field(default=None)  # JSON array of note IDs
    # Conflict / lifecycle state
    supersedes_note_id: int | None = Field(default=None)
    # 'active' | 'superseded' | 'contradicted' | 'archived' | 'invalid' | 'unclassified'
    status: str = Field(default="active")
    reference_count: int = Field(default=0)
    session: WizardSession | None = Relationship(back_populates="notes")


class ToolCall(SQLModel, table=True):
    """Telemetry — append-only, never updated. No TimestampMixin because
    updated_at is meaningless and called_at is more intention-revealing
    than created_at for a log record."""

    id: int | None = Field(default=None, primary_key=True)
    session_id: int | None = Field(default=None, foreign_key="wizardsession.id")
    tool_name: str
    called_at: datetime.datetime = Field(
        default_factory=datetime.datetime.now, index=True
    )


class TaskState(TimestampMixin, table=True):
    """Derived signals per Task. One-to-one with Task. Updated synchronously
    by TaskStateRepository on note save, status change, and task creation.
    Never recomputed on read.

    stale_days reflects cognitive activity (notes) only — status changes
    deliberately do NOT reset it. last_status_change_at is tracked separately
    for any query that needs to distinguish administrative from cognitive
    activity.
    """

    __tablename__ = "task_state"  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]

    task_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("task.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    note_count: int = Field(default=0, nullable=False)
    decision_count: int = Field(default=0, nullable=False)
    last_note_at: datetime.datetime | None = Field(default=None)
    last_status_change_at: datetime.datetime | None = Field(default=None)
    last_touched_at: datetime.datetime = Field(nullable=False)
    stale_days: int = Field(default=0, nullable=False)
    rolling_summary: str | None = Field(
        default=None,
        sa_type=Text(),
        description=(
            "Synthesised overview of all prior notes, built from mental_models. "
            "Updated on every note save. Used by task_start for tiered context delivery."
        ),
    )
