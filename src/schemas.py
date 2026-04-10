import datetime
from typing import Optional
from pydantic import BaseModel

from .models import NoteType, TaskCategory, TaskPriority, TaskStatus, MeetingCategory

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


class SourceSyncStatus(BaseModel):
    source: str
    ok: bool
    error: Optional[str] = None


class WriteBackStatus(BaseModel):
    ok: bool
    error: Optional[str] = None
    page_id: Optional[str] = None


class TaskContext(BaseModel):
    id: int
    name: str
    status: TaskStatus
    priority: TaskPriority
    category: TaskCategory
    due_date: Optional[datetime.datetime]
    source_id: Optional[str]
    source_url: Optional[str]
    last_note_type: Optional[NoteType]  # most recent note type, or None
    last_note_preview: Optional[str]  # first 300 chars of most recent note
    last_worked_at: Optional[datetime.datetime]  # created_at of most recent note


class MeetingContext(BaseModel):
    id: int
    title: str
    category: MeetingCategory
    created_at: datetime.datetime
    has_summary: bool  # False means call get_meeting to summarise


class NoteDetail(BaseModel):
    id: int
    note_type: NoteType
    content: str
    created_at: datetime.datetime
    source_id: Optional[str]


class SessionStartResponse(BaseModel):
    session_id: int
    open_tasks: list[TaskContext]
    blocked_tasks: list[TaskContext]
    unsummarised_meetings: list[MeetingContext]
    sync_results: list[SourceSyncStatus]


class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: bool  # True if prior notes exist for this task
    notes_by_type: dict[str, int]  # {"investigation": 3, "decision": 1}
    prior_notes: list[NoteDetail]  # all notes, oldest first


class SaveNoteResponse(BaseModel):
    note_id: int


class UpdateTaskStatusResponse(BaseModel):
    task_id: int
    new_status: TaskStatus
    jira_write_back: WriteBackStatus
    notion_write_back: WriteBackStatus


class GetMeetingResponse(BaseModel):
    meeting_id: int
    title: str
    category: MeetingCategory
    content: str
    already_summarised: bool
    existing_summary: Optional[str]
    open_tasks: list[TaskContext]  # tasks linked to this meeting


class SaveMeetingSummaryResponse(BaseModel):
    note_id: int
    linked_task_ids: list[int]
    notion_write_back: WriteBackStatus


class SessionEndResponse(BaseModel):
    note_id: int
    notion_write_back: WriteBackStatus


class IngestMeetingResponse(BaseModel):
    meeting_id: int
    already_existed: bool
    notion_write_back: WriteBackStatus


class CreateTaskResponse(BaseModel):
    task_id: int
    notion_write_back: WriteBackStatus
