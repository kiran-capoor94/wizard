import datetime
from enum import Enum
from typing import Optional

from pydantic import ConfigDict
from sqlmodel import Field, Relationship, SQLModel


class TimestampMixin(SQLModel):
    model_config = ConfigDict(validate_default=True, validate_assignment=True)

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
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    due_date: Optional[datetime.datetime] = None
    priority: TaskPriority = TaskPriority.MEDIUM
    category: TaskCategory = TaskCategory.ISSUE
    status: TaskStatus = TaskStatus.TODO
    notion_id: Optional[str] = Field(default=None, index=True)
    meetings: list["Meeting"] = Relationship(
        back_populates="tasks", link_model=MeetingTasks
    )
    source_id: Optional[str] = Field(
        default=None,
        index=True,
        unique=True,
        description="identifier of the external entity this task originated from",
    )
    source_type: Optional[str] = Field(default=None, index=True)
    source_url: Optional[str] = Field(default=None)


class Meeting(TimestampMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: str
    notion_id: Optional[str] = Field(default=None, index=True)
    category: MeetingCategory = MeetingCategory.GENERAL
    summary: Optional[str] = None
    tasks: list[Task] = Relationship(back_populates="meetings", link_model=MeetingTasks)
    source_id: Optional[str] = Field(
        default=None,
        index=True,
        unique=True,
        description="identifier of the external entity this meeting relates to",
    )
    source_type: Optional[str] = Field(default=None, index=True)
    source_url: Optional[str] = Field(default=None)


class WizardSession(TimestampMixin, table=True):
    __tablename__ = "wizardsession"

    id: Optional[int] = Field(default=None, primary_key=True)
    summary: Optional[str] = None
    notes: list["Note"] = Relationship(back_populates="session")


class Note(TimestampMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    note_type: NoteType = Field(index=True)
    content: str
    source_id: Optional[str] = Field(
        default=None,
        index=True,
        description="identifier of the external entity this note is about",
    )
    source_type: Optional[str] = Field(default=None, index=True)
    session_id: Optional[int] = Field(default=None, foreign_key="wizardsession.id")
    source_url: Optional[str] = Field(default=None)
    task_id: Optional[int] = Field(default=None, foreign_key="task.id")
    meeting_id: Optional[int] = Field(default=None, foreign_key="meeting.id")
    session: Optional[WizardSession] = Relationship(back_populates="notes")
