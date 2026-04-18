"""Helper functions for task tools."""

import logging

from fastmcp.exceptions import ToolError

from ..models import Task, TaskPriority, TaskStatus
from ..security import SecurityService
from ..services import WriteBackService, WriteBackStatus

logger = logging.getLogger(__name__)


def apply_task_fields(
    task: Task,
    sec: SecurityService,
    *,
    status: TaskStatus | None,
    priority: TaskPriority | None,
    due_date: str | None,
    name: str | None,
    source_url: str | None,
) -> list[str]:
    """Apply non-None field values to a Task model. Returns list of updated field names."""
    import datetime

    updated: list[str] = []
    if status is not None:
        task.status = status
        updated.append("status")
    if priority is not None:
        task.priority = priority
        updated.append("priority")
    if due_date is not None:
        try:
            due_date_dt = datetime.datetime.fromisoformat(due_date.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ToolError(f"Invalid due_date format: {due_date}. Use ISO 8601.") from exc
        task.due_date = due_date_dt
        updated.append("due_date")
    if name is not None:
        task.name = sec.scrub(name).clean
        updated.append("name")
    if source_url is not None:
        task.source_url = source_url
        updated.append("source_url")
    return updated


def dispatch_writebacks(
    task: Task,
    updated_fields: list[str],
    wb: WriteBackService,
) -> tuple[WriteBackStatus | None, WriteBackStatus | None, WriteBackStatus | None]:
    """Push changed fields to Jira/Notion. Returns (status_wb, due_date_wb, priority_wb)."""
    status_writeback = None
    due_date_writeback = None
    priority_writeback = None
    if "status" in updated_fields:
        jira_wb = wb.push_task_status(task)
        notion_wb = wb.push_task_status_to_notion(task)
        status_writeback = WriteBackStatus(
            ok=jira_wb.ok and notion_wb.ok,
            error=", ".join(filter(None, [jira_wb.error, notion_wb.error])),
            page_id=None,
        )
    if "due_date" in updated_fields:
        due_date_writeback = wb.push_task_due_date(task)
    if "priority" in updated_fields:
        priority_writeback = wb.push_task_priority(task)
    return status_writeback, due_date_writeback, priority_writeback
