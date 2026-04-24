import logging

import sentry_sdk
from fastmcp import Context
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation

from ..database import get_session
from ..deps import get_meeting_repo, get_note_repo, get_security, get_task_repo
from ..mcp_instance import mcp
from ..models import Meeting, MeetingCategory, Note, NoteType, TaskStatus
from ..repositories import MeetingRepository, NoteRepository, TaskRepository
from ..schemas import (
    GetMeetingResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
)
from ..security import SecurityService
from ..skills import SKILL_MEETING, load_skill_post

logger = logging.getLogger(__name__)


async def get_meeting(
    ctx: Context,
    meeting_id: int,
    meetings_repo: MeetingRepository = Depends(get_meeting_repo),
    tasks_repo: TaskRepository = Depends(get_task_repo),
) -> GetMeetingResponse:
    """Returns meeting transcript and linked open tasks.

    meeting_id: integer meeting ID from the unsummarised_meetings list
    returned by session_start. Call session_start first to get available IDs.
    """
    logger.info("get_meeting meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            meeting = meetings_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError(
                    "Internal error: meeting was not assigned an id after flush"
                )

            open_task_ids = [
                task.id
                for task in meeting.tasks
                if task.id is not None
                and task.status
                in (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED)
            ]
            linked_tasks = tasks_repo.get_task_contexts_by_ids(db, open_task_ids)

            return GetMeetingResponse(
                meeting_id=meeting.id,
                title=meeting.title,
                category=meeting.category,
                content=meeting.content,
                already_summarised=meeting.summary is not None,
                existing_summary=meeting.summary,
                open_tasks=linked_tasks,
                skill_instructions=load_skill_post(SKILL_MEETING),
            )
    except ValueError as e:
        logger.warning("get_meeting failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        sentry_sdk.capture_exception(e)
        raise


async def save_meeting_summary(
    ctx: Context,
    meeting_id: int,
    summary: str,
    task_ids: list[int] | None = None,
    meetings_repo: MeetingRepository = Depends(get_meeting_repo),
    sec: SecurityService = Depends(get_security),
    n_repo: NoteRepository = Depends(get_note_repo),
) -> SaveMeetingSummaryResponse:
    """Scrubs and persists the LLM-generated meeting summary."""
    logger.info("save_meeting_summary meeting_id=%d", meeting_id)
    try:
        with get_session() as db:
            session_id: int | None = await ctx.get_state("current_session_id")
            meeting = meetings_repo.get_by_id(db, meeting_id)
            if meeting.id is None:
                raise ToolError(
                    "Internal error: meeting was not assigned an id after flush"
                )

            if task_ids:
                task_names = [t.name for t in meeting.tasks if t.id in set(task_ids)]
                names_str = ", ".join(repr(n) for n in task_names) if task_names else str(task_ids)
                try:
                    result = await ctx.elicit(
                        f"Link {len(task_ids)} task(s) to this meeting summary? ({names_str})",
                        response_type=bool,
                    )
                    if isinstance(result, AcceptedElicitation) and result.data is False:
                        task_ids = None
                except Exception as e:
                    logger.debug("ctx.elicit unavailable for task link confirmation: %s", e)

            clean_summary = sec.scrub(summary).clean
            meeting.summary = clean_summary
            meetings_repo.save(db, meeting)

            note = Note(
                note_type=NoteType.DOCS,
                content=clean_summary,
                meeting_id=meeting.id,
                session_id=session_id,
                artifact_id=meeting.artifact_id,
                artifact_type="meeting",
            )
            saved = n_repo.save(db, note)
            if saved.id is None:
                raise ToolError(
                    "Internal error: note was not assigned an id after flush"
                )

            if task_ids:
                meetings_repo.link_tasks(db, meeting_id, task_ids)

            linked_ids = [t.id for t in meeting.tasks if t.id is not None]

            await ctx.info(f"Meeting {meeting.id} summary saved.")
            return SaveMeetingSummaryResponse(
                note_id=saved.id,
                tasks_linked=len(linked_ids),
            )
    except ValueError as e:
        logger.warning("save_meeting_summary failed: %s", e)
        raise ToolError(str(e)) from e
    except Exception as e:
        # Capture unexpected exceptions in Sentry
        sentry_sdk.capture_exception(e)
        raise


async def ingest_meeting(
    ctx: Context,
    title: str,
    content: str,
    source_id: str | None = None,
    source_type: str | None = None,
    source_url: str | None = None,
    category: MeetingCategory = MeetingCategory.GENERAL,
    meetings_repo: MeetingRepository = Depends(get_meeting_repo),
    sec: SecurityService = Depends(get_security),
) -> IngestMeetingResponse:
    """Accepts meeting data (e.g. from Krisp MCP), scrubs and stores locally."""
    logger.info("ingest_meeting source_id=%s", source_id)
    with get_session() as db:
        await ctx.report_progress(1, 2)
        clean_title = sec.scrub(title).clean
        clean_content = sec.scrub(content).clean

        meeting: Meeting | None = None
        already_existed = False
        if source_id:
            meeting = meetings_repo.get_by_source_id(db, source_id)
        if meeting:
            already_existed = True
            meeting.title = clean_title
            meeting.content = clean_content
            meetings_repo.save(db, meeting)
        else:
            meeting = Meeting(
                title=clean_title,
                content=clean_content,
                source_id=source_id,
                source_type=source_type,
                source_url=source_url,
                category=category,
            )
            meetings_repo.save(db, meeting)

        if meeting.id is None:
            raise ToolError(
                "Internal error: meeting was not assigned an id after flush"
            )

        await ctx.report_progress(2, 2)
        await ctx.info(f"Meeting {meeting.id} ingested (existed={already_existed}).")
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
