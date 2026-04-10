import datetime
from typing import Optional
from pydantic import BaseModel

from .models import NoteType, TaskCategory, TaskPriority, TaskStatus, MeetingCategory


class TaskContext(BaseModel):
    id: int
    name: str
    status: TaskStatus
    priority: TaskPriority
    category: TaskCategory
    due_date: Optional[datetime.datetime]
    source_id: Optional[str]
    source_url: Optional[str]
    last_note_type: Optional[NoteType]       # most recent note type, or None
    last_note_preview: Optional[str]         # first 120 chars of most recent note
    last_worked_at: Optional[datetime.datetime]  # created_at of most recent note


class MeetingContext(BaseModel):
    id: int
    title: str
    category: MeetingCategory
    created_at: datetime.datetime
    has_summary: bool                        # False means call get_meeting to summarise


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


class TaskStartResponse(BaseModel):
    task: TaskContext
    compounding: bool                        # True if prior notes exist for this task
    notes_by_type: dict[str, int]            # {"investigation": 3, "decision": 1}
    prior_notes: list[NoteDetail]            # all notes, oldest first


class SaveNoteResponse(BaseModel):
    note_id: int


class UpdateTaskStatusResponse(BaseModel):
    task_id: int
    new_status: TaskStatus
    write_back_succeeded: bool


class GetMeetingResponse(BaseModel):
    meeting_id: int
    title: str
    category: MeetingCategory
    content: str
    already_summarised: bool
    existing_summary: Optional[str]
    open_tasks: list[TaskContext]            # tasks linked to this meeting


class SaveMeetingSummaryResponse(BaseModel):
    note_id: int
    linked_task_ids: list[int]


class SessionEndResponse(BaseModel):
    note_id: int
