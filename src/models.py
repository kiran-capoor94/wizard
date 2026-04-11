import datetime
from enum import Enum

from pydantic import ConfigDict
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
    notes: list["Note"] = Relationship(back_populates="session")


class Note(TimestampMixin, table=True):
    id: int | None = Field(default=None, primary_key=True)
    note_type: NoteType = Field(index=True)
    content: str
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
