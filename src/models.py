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
    PRESENTATION = "presentation"
    RETRO = "retro"
    ONE_ON_ONE = "one_on_one"
    TRAINING = "training"


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
    meetings: list["Meeting"] = Relationship(
        back_populates="tasks", link_model=MeetingTasks
    )


class Meeting(TimestampMixin, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    content: str
    category: MeetingCategory = MeetingCategory.STANDUP
    summary: Optional[str] = None
    tasks: list[Task] = Relationship(
        back_populates="meetings", link_model=MeetingTasks
    )
