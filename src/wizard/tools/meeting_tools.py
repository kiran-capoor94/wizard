import logging

from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from sqlmodel import select

from ..deps import (
    get_meeting_repo,
    get_note_repo,
    get_security,
    get_task_repo,
    get_writeback,
)
from ..mcp_instance import mcp
from ..models import (
    Meeting,
    MeetingCategory,
    MeetingTasks,
    Note,
    NoteType,
    TaskStatus,
)
from ..repositories import (
    MeetingRepository,
    NoteRepository,
    TaskRepository,
)
from ..schemas import (
    GetMeetingResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
)
from ..security import SecurityService
from ..services import WriteBackService
from . import _helpers
from ._helpers import _log_tool_call

logger = logging.getLogger(__name__)


async def get_meeting(
    ctx: Context,
    meeting_id: int,
    m_repo: MeetingRepository = Depends(get_meeting_repo),
    t_repo: TaskRepository = Depends(get_task_repo),
) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks.

    meeting_id: integer meeting ID from the unsummarised_meetings list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("get_meeting meeting_id=%d", meeting_id)
    try:
        with _helpers.get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "get_meeting", session_id=session_id)
            meeting = m_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError("Internal error: meeting was not assigned an id after flush")

            linked_tasks = [
                t_repo.build_task_context(db, t)
                for t in meeting.tasks
                if t.status
                in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
            ]

            return GetMeetingResponse(
                meeting_id=meeting.id,
                title=meeting.title,
                category=meeting.category,
                content=meeting.content,
                already_summarised=meeting.summary is not None,
                existing_summary=meeting.summary,
                open_tasks=linked_tasks,
            )
    except ValueError as e:
        logger.warning("get_meeting failed: %s", e)
        raise ToolError(str(e)) from e


async def save_meeting_summary(
    ctx: Context,
    meeting_id: int,
    summary: str,
    task_ids: list[int] | None = None,
    m_repo: MeetingRepository = Depends(get_meeting_repo),
    sec: SecurityService = Depends(get_security),
    n_repo: NoteRepository = Depends(get_note_repo),
    wb: WriteBackService = Depends(get_writeback),
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary. Attempts Notion write-back."""
    logger.info("save_meeting_summary meeting_id=%d", meeting_id)
    try:
        with _helpers.get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "save_meeting_summary", session_id=session_id)
            meeting = m_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError("Internal error: meeting was not assigned an id after flush")

            clean_summary = sec.scrub(summary).clean
            meeting.summary = clean_summary
            db.add(meeting)

            note = Note(
                note_type=NoteType.DOCS,
                content=clean_summary,
                meeting_id=meeting.id,
                session_id=session_id,
            )
            saved = n_repo.save(db, note)
            if saved.id is None:
                raise ToolError("Internal error: note was not assigned an id after flush")

            if task_ids:
                for tid in task_ids:
                    existing_link = db.exec(
                        select(MeetingTasks).where(
                            MeetingTasks.meeting_id == meeting.id,
                            MeetingTasks.task_id == tid,
                        )
                    ).first()
                    if not existing_link:
                        db.add(MeetingTasks(meeting_id=meeting.id, task_id=tid))

            db.flush()
            wb_result = wb.push_meeting_summary(meeting)

            linked_ids = [t.id for t in meeting.tasks if t.id is not None]

            return SaveMeetingSummaryResponse(
                note_id=saved.id,
                tasks_linked=len(linked_ids),
                notion_write_back=wb_result,
            )
    except ValueError as e:
        logger.warning("save_meeting_summary failed: %s", e)
        raise ToolError(str(e)) from e


async def ingest_meeting(
    ctx: Context,
    title: str,
    content: str,
    source_id: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
    sec: SecurityService = Depends(get_security),
    wb: WriteBackService = Depends(get_writeback),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs, stores, writes to Notion."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with _helpers.get_session() as db:
        session_id: int | None = await ctx.get_state("current_session_id")
        await _log_tool_call(db, "ingest_meeting", session_id=session_id)
        clean_title = sec.scrub(title).clean
        clean_content = sec.scrub(content).clean

        meeting: Meeting | None = None
        already_existed = False
        if source_id:
            meeting = db.exec(
                select(Meeting).where(Meeting.source_id == source_id)
            ).first()
        if meeting:
            already_existed = True
            meeting.title = clean_title
            meeting.content = clean_content
            db.add(meeting)
        else:
            meeting = Meeting(
                title=clean_title,
                content=clean_content,
                source_id=source_id,
                source_type="TRANSCRIPT" if source_id else None,
                source_url=source_url,
                category=category,
            )
            db.add(meeting)

        db.flush()
        db.refresh(meeting)
        if meeting.id is None:
            raise ToolError("Internal error: meeting was not assigned an id after flush")

        wb_result = wb.push_meeting_to_notion(meeting)
        if wb_result.page_id:
            meeting.notion_id = wb_result.page_id
            db.flush()

        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
            notion_write_back=wb_result,
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(get_meeting)
mcp.tool()(save_meeting_summary)
mcp.tool()(ingest_meeting)
