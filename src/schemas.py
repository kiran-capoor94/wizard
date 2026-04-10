import datetime
from pydantic import BaseModel, ConfigDict

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
    due_date: datetime.datetime | None
    source_id: str | None
    source_url: str | None
    last_note_type: NoteType | None  # most recent note type, or None
    last_note_preview: str | None  # first 300 chars of most recent note
    last_worked_at: datetime.datetime | None  # created_at of most recent note


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
    source_id: str | None

    @classmethod
    def from_model(cls, note) -> "NoteDetail":
        assert note.id is not None
        return cls(
            id=note.id,
            note_type=note.note_type,
            content=note.content,
            created_at=note.created_at,
            source_id=note.source_id,
        )


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
    existing_summary: str | None
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
