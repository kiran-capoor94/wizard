import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, WrapSerializer

from .models import (
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskState,
    TaskStatus,
    MeetingCategory,
)


def _ensure_utc_z(v, handler) -> str:
    """Serialize datetime as UTC ISO-8601 string with 'Z' suffix.

    Naive datetimes are treated as UTC (SQLite always strips timezone).
    Offset-aware datetimes are converted to UTC before formatting.
    """
    result = handler(v)
    if not isinstance(result, str):
        return result
    if result.endswith("Z"):
        return result
    if isinstance(v, datetime.datetime) and v.tzinfo is not None:
        utc_dt = v.astimezone(datetime.timezone.utc)
        return utc_dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    return result + "Z"


UTCDateTime = Annotated[
    datetime.datetime,
    WrapSerializer(_ensure_utc_z, when_used="json"),
    Field(json_schema_extra={"format": "date-time"}),
]


class SessionState(BaseModel):
    """Six-field structured session state written by session_end (M2)
    and read by resume_session (M3). Stored as JSON in
    wizardsession.session_state. Defined here in M1 so M2 can lift it
    verbatim without a duplicate schema."""

    intent: str
    working_set: list[int] = Field(default_factory=list)
    state_delta: str
    open_loops: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    closure_status: Literal["clean", "interrupted", "blocked"]
    tool_registry: str | None = None


# --- Integration response models (typed outputs from Jira/Notion clients) ---


class JiraTaskData(BaseModel):
    key: str
    summary: str
    status: str
    priority: str
    issue_type: str
    url: str = ""


class NotionTaskData(BaseModel):
    notion_id: str
    name: str | None = None
    status: str | None = None
    priority: str | None = None
    due_date: str | None = None
    jira_url: str | None = None
    jira_key: str | None = None


class NotionMeetingData(BaseModel):
    notion_id: str
    title: str | None = None
    categories: list[str] = []
    summary: str | None = None
    krisp_url: str | None = None
    date: str | None = None


# --- Notion API property models (parse raw Notion property dicts) ---


class NotionPropertyValue(BaseModel):
    model_config = ConfigDict(extra="ignore")


class NotionTitle(NotionPropertyValue):
    title: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.title[0].get("plain_text") if self.title else None


class NotionRichText(NotionPropertyValue):
    rich_text: list[dict] = []

    @property
    def text(self) -> str | None:
        return self.rich_text[0].get("plain_text") if self.rich_text else None


class NotionSelect(NotionPropertyValue):
    select: dict | None = None

    @property
    def name(self) -> str | None:
        return self.select.get("name") if self.select else None


class NotionMultiSelect(NotionPropertyValue):
    multi_select: list[dict] = []

    @property
    def names(self) -> list[str]:
        return [item["name"] for item in self.multi_select if "name" in item]


class NotionUrl(NotionPropertyValue):
    url: str | None = None


class NotionDate(NotionPropertyValue):
    date: dict | None = None

    @property
    def start(self) -> str | None:
        return self.date.get("start") if self.date else None


class NotionStatus(NotionPropertyValue):
    status: dict | None = None

    @property
    def name(self) -> str | None:
        return self.status.get("name") if self.status else None


# --- Resource response models (read-only data exposed via FastMCP URIs) ---


class SessionResource(BaseModel):
    session_id: int | None
    open_task_count: int
    blocked_task_count: int


class TaskContextResource(BaseModel):
    task: "TaskContext"
    notes: list["NoteDetail"]


class OpenTasksResource(BaseModel):
    tasks: list["TaskContext"]


class BlockedTasksResource(BaseModel):
    tasks: list["TaskContext"]


class ConfigResource(BaseModel):
    jira_enabled: bool
    notion_enabled: bool
    scrubbing_enabled: bool
    database_path: str


class SourceSyncStatus(BaseModel):
    source: str
    ok: bool
    error: str | None = None


class WriteBackStatus(BaseModel):
    ok: bool
    error: str | None = None
    page_id: str | None = None


class TaskContext(BaseModel):
    id: int
    name: str
    status: TaskStatus
    priority: TaskPriority
    category: TaskCategory
    due_date: UTCDateTime | None
    source_id: str | None
    source_url: str | None
    last_note_type: NoteType | None  # most recent note type, or None
    last_note_preview: str | None  # first 300 chars of most recent note
    last_worked_at: UTCDateTime | None  # created_at of most recent note
    notion_id: str | None = None
    stale_days: int = 0
    note_count: int = 0
    decision_count: int = 0

    @classmethod
    def from_model(
        cls,
        task: Task,
        task_state: TaskState | None,
        latest_note: Note | None = None,
    ) -> "TaskContext":
        if task.id is None:
            raise ValueError(
                "Cannot build TaskContext from an unpersisted Task (id is None)"
            )
        return cls(
            id=task.id,
            name=task.name,
            status=task.status,
            priority=task.priority,
            category=task.category,
            due_date=task.due_date,
            source_id=task.source_id,
            source_url=task.source_url,
            notion_id=task.notion_id,
            last_note_type=latest_note.note_type if latest_note else None,
            last_note_preview=latest_note.content[:300] if latest_note else None,
            last_worked_at=task_state.last_note_at if task_state else None,
            stale_days=task_state.stale_days if task_state else 0,
            note_count=task_state.note_count if task_state else 0,
            decision_count=task_state.decision_count if task_state else 0,
        )


class MeetingContext(BaseModel):
    id: int
    title: str
    category: MeetingCategory
    created_at: UTCDateTime
    already_summarised: bool
    source_url: str | None = None
    source_type: str | None = None


class TimelineEntry(BaseModel):
    note_id: int
    created_at: UTCDateTime
    note_type: NoteType
    preview: str  # content[:200]
    mental_model: str | None


class RewindSummary(BaseModel):
    total_notes: int
    duration_days: int  # 0 if fewer than 2 notes
    last_activity: UTCDateTime


class RewindResponse(BaseModel):
    task: TaskContext
    timeline: list[TimelineEntry]  # sorted oldest first; empty list, never null
    summary: RewindSummary


class NoteDetail(BaseModel):
    id: int
    note_type: NoteType
    content: str
    created_at: UTCDateTime
    source_id: str | None
    mental_model: str | None = None

    @classmethod
    def from_model(cls, note) -> "NoteDetail":
        if note.id is None:
            raise ValueError(
                "Cannot build NoteDetail from an unpersisted Note (id is None)"
            )
        return cls(
            id=note.id,
            note_type=note.note_type,
            content=note.content,
            created_at=note.created_at,
            source_id=note.source_id,
            mental_model=note.mental_model,
        )


class DailyPageResult(BaseModel):
    page_id: str
    created: bool
    archived_count: int


class SessionStartResponse(BaseModel):
    session_id: int
    open_tasks: list[TaskContext]
    blocked_tasks: list[TaskContext]
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]
    daily_page: DailyPageResult | None = None


class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: bool  # True if prior notes exist for this task
    notes_by_type: dict[str, int]  # {"investigation": 3, "decision": 1}
    prior_notes: list[NoteDetail]  # all notes, oldest first
    latest_mental_model: str | None = None


class SaveNoteResponse(BaseModel):
    note_id: int
    mental_model_saved: bool


class UpdateTaskStatusResponse(BaseModel):
    task_id: int
    new_status: TaskStatus
    jira_write_back: WriteBackStatus
    notion_write_back: WriteBackStatus
    task_state_updated: bool = True
    deprecation_warning: str | None = (
        "Use update_task instead. Run 'wizard update' to upgrade."
    )


class UpdateTaskResponse(BaseModel):
    task_id: int
    updated_fields: list[str]
    status_writeback: WriteBackStatus | None = None
    due_date_writeback: WriteBackStatus | None = None
    priority_writeback: WriteBackStatus | None = None
    task_state_updated: bool = False


class GetMeetingResponse(BaseModel):
    meeting_id: int
    title: str
    category: MeetingCategory
    content: str
    already_summarised: bool
    existing_summary: str | None
    open_tasks: list[TaskContext]  # tasks linked to this meeting


class SaveMeetingSummaryResponse(BaseModel):
    note_id: int
    tasks_linked: int
    notion_write_back: WriteBackStatus


class SessionEndResponse(BaseModel):
    note_id: int
    notion_write_back: WriteBackStatus
    session_state_saved: bool = False
    closure_status: str | None = None
    open_loops_count: int = 0
    next_actions_count: int = 0
    intent: str | None = None


class IngestMeetingResponse(BaseModel):
    meeting_id: int
    already_existed: bool
    notion_write_back: WriteBackStatus


class CreateTaskResponse(BaseModel):
    task_id: int
    notion_write_back: WriteBackStatus


class Signal(BaseModel):
    type: str
    severity: Literal["high", "medium", "low"]
    message: str


class MissingResponse(BaseModel):
    signals: list[Signal]


class ResumedTaskNotes(BaseModel):
    task: TaskContext
    notes: list[NoteDetail]
    latest_mental_model: str | None


class ResumeSessionResponse(BaseModel):
    session_id: int
    resumed_from_session_id: int
    session_state: SessionState | None
    working_set_tasks: list[TaskContext]
    prior_notes: list[ResumedTaskNotes]
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]
    daily_page: DailyPageResult | None
