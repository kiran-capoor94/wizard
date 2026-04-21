import logging

from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from sqlmodel import col, select

from ..database import get_session
from ..deps import get_meeting_repo, get_note_repo, get_security, get_task_repo
from ..mcp_instance import mcp
from ..models import Meeting, MeetingCategory, MeetingTasks, Note, NoteType, TaskStatus
from ..repositories import MeetingRepository, NoteRepository, TaskRepository
from ..schemas import (
    GetMeetingResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
)
from ..security import SecurityService
from ..skills import SKILL_MEETING, load_skill

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
        with get_session() as db:
            meeting = m_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError(
                    "Internal error: meeting was not assigned an id after flush"
                )

            open_task_ids = [
                t.id
                for t in meeting.tasks
                if t.id is not None
                and t.status
                in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
            ]
            linked_tasks = t_repo.get_task_contexts_by_ids(db, open_task_ids)

            return GetMeetingResponse(
                meeting_id=meeting.id,
                title=meeting.title,
                category=meeting.category,
                content=meeting.content,
                already_summarised=meeting.summary is not None,
                existing_summary=meeting.summary,
                open_tasks=linked_tasks,
                skill_instructions=load_skill(SKILL_MEETING),
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
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary."""
    logger.info("save_meeting_summary meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            meeting = m_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError(
                    "Internal error: meeting was not assigned an id after flush"
                )

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
                raise ToolError(
                    "Internal error: note was not assigned an id after flush"
                )

            if task_ids:
                existing_links = {
                    mt.task_id
                    for mt in db.exec(
                        select(MeetingTasks).where(
                            MeetingTasks.meeting_id == meeting.id,
                            col(MeetingTasks.task_id).in_(task_ids),
                        )
                    ).all()
                }
                for tid in task_ids:
                    if tid not in existing_links:
                        db.add(MeetingTasks(meeting_id=meeting.id, task_id=tid))

            db.flush()
            linked_ids = [t.id for t in meeting.tasks if t.id is not None]

            return SaveMeetingSummaryResponse(
                note_id=saved.id,
                tasks_linked=len(linked_ids),
            )
    except ValueError as e:
        logger.warning("save_meeting_summary failed: %s", e)
        raise ToolError(str(e)) from e


async def ingest_meeting(
    ctx: Context,
    title: str,
    content: str,
    source_id: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
    m_repo: MeetingRepository = Depends(get_meeting_repo),
    sec: SecurityService = Depends(get_security),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs and stores locally."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with get_session() as db:
        clean_title = sec.scrub(title).clean
        clean_content = sec.scrub(content).clean

        meeting: Meeting | None = None
        already_existed = False
        if source_id:
            meeting = m_repo.get_by_source_id(db, source_id)
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
                source_type=source_type,
                source_url=source_url,
                category=category,
            )
            db.add(meeting)

        db.flush()
        db.refresh(meeting)
        if meeting.id is None:
            raise ToolError(
                "Internal error: meeting was not assigned an id after flush"
            )

        return IngestMeetingResponse(
            meeting_id=meeting.id,
            already_existed=already_existed,
        )


# ---------------------------------------------------------------------------
# Register tools with MCP
# ---------------------------------------------------------------------------

mcp.tool()(get_meeting)
mcp.tool()(save_meeting_summary)
mcp.tool()(ingest_meeting)
