import datetime
from enum import Enum

from pydantic import ConfigDict, field_validator
from sqlalchemy import Column, ForeignKey, Integer
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
    notion_id: str | None = Field(default=None, index=True)
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


class Meeting(TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    title: str
    content: str
    notion_id: str | None = Field(default=None, index=True)
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


class WizardSession(TimestampMixin, table=True):
    # SQLAlchemy types __tablename__ as declared_attr — string literal is valid at
    # runtime but mismatches the declared type. Upstream typing gap in sqlalchemy.
    __tablename__ = "wizardsession"  # pyright: ignore[reportAssignmentType, reportIncompatibleVariableOverride]

    id: int | None = Field(default=None, primary_key=True)
    summary: str | None = None
    daily_page_id: str | None = None
    session_state: str | None = Field(
        default=None,
        description=(
            "JSON-serialised SessionState (see schemas.SessionState). "
            "Null until session_end (M2) populates it. "
            "Read by resume_session (M3)."
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
    source_id: str | None = Field(
        default=None,
        index=True,
        description="identifier of the external entity this note is about",
    )
    source_type: str | None = Field(default=None, index=True)
    session_id: int | None = Field(default=None, foreign_key="wizardsession.id")
    source_url: str | None = Field(default=None)
    task_id: int | None = Field(default=None, foreign_key="task.id")
    meeting_id: int | None = Field(default=None, foreign_key="meeting.id")
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
