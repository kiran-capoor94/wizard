import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, WrapSerializer

from .models import (
    MeetingCategory,
    Note,
    NoteType,
    Task,
    TaskCategory,
    TaskPriority,
    TaskState,
    TaskStatus,
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
    """Structured session state written by session_end (M2)
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
    knowledge_store_type: str
    scrubbing_enabled: bool
    database_path: str


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
            raise ValueError("Cannot build TaskContext from an unpersisted Task (id is None)")
        return cls(
            id=task.id,
            name=task.name,
            status=task.status,
            priority=task.priority,
            category=task.category,
            due_date=task.due_date,
            source_id=task.source_id,
            source_url=task.source_url,
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
    mental_model: str | None = None

    @classmethod
    def from_model(cls, note) -> "NoteDetail":
        if note.id is None:
            raise ValueError("Cannot build NoteDetail from an unpersisted Note (id is None)")
        return cls(
            id=note.id,
            note_type=note.note_type,
            content=note.content,
            created_at=note.created_at,
            mental_model=note.mental_model,
        )


class AutoCloseSummary(BaseModel):
    """Structured output from LLM sampling when auto-closing an abandoned session."""

    summary: str
    intent: str
    open_loops: list[str] = Field(default_factory=list)


class ClosedSessionSummary(BaseModel):
    """Result of auto-closing one abandoned session. Included in SessionStartResponse."""

    session_id: int
    summary: str
    closed_via: str  # "sampling", "synthetic", "fallback"
    task_ids: list[int] = Field(default_factory=list)
    note_count: int


class PriorSessionSummary(BaseModel):
    """A recently-closed session surfaced as prior context in session_start."""

    session_id: int
    summary: str
    closed_at: UTCDateTime
    task_ids: list[int] = Field(default_factory=list)


class SessionStartResponse(BaseModel):
    session_id: int
    continued_from_id: int | None = None
    open_tasks: str = ""        # TOON-encoded; see encode_task_contexts
    blocked_tasks: str = ""     # TOON-encoded; see encode_task_contexts
    unsummarised_meetings: list[MeetingContext]
    wizard_context: dict | None = None
    skill_instructions: str | None = None
    closed_sessions: list[ClosedSessionSummary] = Field(default_factory=list)
    open_tasks_total: int = 0
    source: str = "startup"
    prior_summaries: list[PriorSessionSummary] = Field(default_factory=list)


class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: bool  # True if prior notes exist for this task
    notes_by_type: dict[str, int]  # {"investigation": 3, "decision": 1}
    prior_notes: list[NoteDetail]  # 3 most recent notes, oldest first
    total_notes: int = 0  # total note count including older notes not returned
    older_notes_available: bool = False  # True if note_count > 3; use rewind_task for full history
    rolling_summary: str | None = None  # synthesised from mental_models of all notes
    latest_mental_model: str | None = None
    skill_instructions: str | None = None


class SaveNoteResponse(BaseModel):
    note_id: int
    mental_model_saved: bool


class UpdateTaskResponse(BaseModel):
    task_id: int
    updated_fields: list[str]
    task_state_updated: bool = False


class GetMeetingResponse(BaseModel):
    meeting_id: int
    title: str
    category: MeetingCategory
    content: str
    already_summarised: bool
    existing_summary: str | None
    open_tasks: list[TaskContext]  # tasks linked to this meeting
    skill_instructions: str | None = None


class SaveMeetingSummaryResponse(BaseModel):
    note_id: int
    tasks_linked: int


class SessionEndResponse(BaseModel):
    note_id: int
    session_state_saved: bool = False
    closure_status: str | None = None
    open_loops_count: int = 0
    next_actions_count: int = 0
    intent: str | None = None
    skill_instructions: str | None = None


class IngestMeetingResponse(BaseModel):
    meeting_id: int
    already_existed: bool


class CreateTaskResponse(BaseModel):
    task_id: int
    already_existed: bool = False


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
    continued_from_id: int | None = None
    session_state: SessionState | None
    working_set_tasks: list[TaskContext]
    prior_notes: list[ResumedTaskNotes]
    unsummarised_meetings: list[MeetingContext]
    skill_instructions: str | None = None


class SynthesisNote(BaseModel):
    """One note produced by transcript synthesis."""

    task_id: int | None = None
    note_type: str  # "investigation" | "decision" | "docs" | "learnings"
    content: str
    mental_model: str | None = None


class SynthesisResult(BaseModel):
    """Result of synthesising a transcript into notes."""

    notes_created: int
    task_ids_touched: list[int] = Field(default_factory=list)
    synthesised_via: str  # "sampling" | "synthetic" | "fallback"


# --- Query response types (pagination-friendly read models) ---


class TaskSummary(BaseModel):
    id: int
    name: str
    status: str
    priority: str
    category: str
    source_id: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    stale_days: int = 0
    note_count: int = 0
    due_date: datetime.datetime | None = None
    last_worked_at: datetime.datetime | None = None


class GetTasksResponse(BaseModel):
    items: list[TaskSummary]
    next_cursor: str | None = None
    total_returned: int


class TaskDetailResponse(BaseModel):
    task: TaskSummary
    notes: list[NoteDetail]
    latest_mental_model: str | None = None


class SessionSummary(BaseModel):
    id: int
    created_at: datetime.datetime
    updated_at: datetime.datetime | None = None
    closure_status: str | None = None
    intent: str | None = None
    note_count: int = 0


class GetSessionsResponse(BaseModel):
    items: list[SessionSummary]
    next_cursor: str | None = None
    total_returned: int


class SessionDetailResponse(BaseModel):
    session: SessionSummary
    session_state: SessionState | None = None
    notes: list[NoteDetail]


class TaskRecommendation(BaseModel):
    task_id: int
    name: str
    priority: str
    status: str
    score: float
    reason: str
    momentum: Literal["new", "active", "cooling", "cold"]
    last_note_preview: str | None


class WorkRecommendationResponse(BaseModel):
    recommended_task: TaskRecommendation | None
    alternatives: list[TaskRecommendation]
    skipped_blocked: int
    message: str | None = None
