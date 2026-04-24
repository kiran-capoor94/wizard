"""Task mutation and interaction helpers."""

import datetime
import logging

from fastmcp import Context
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation

from ..models import Task, TaskPriority, TaskStatus
from ..security import SecurityService

logger = logging.getLogger(__name__)


async def elicit_mental_model(ctx: Context, sec: SecurityService) -> str | None:
    """Prompt for an optional mental model summary. Returns scrubbed text or None."""
    try:
        result = await ctx.elicit(
            "Optional: summarise what you now understand in 1-2 sentences "
            "(mental model). Press Enter to skip.",
            response_type=str,
        )
        if isinstance(result, AcceptedElicitation) and result.data:
            return sec.scrub(result.data).clean
    except Exception as e:
        logger.debug("ctx.elicit unavailable for mental_model: %s", e)
    return None


async def elicit_done_confirmation(ctx: Context, task_name: str) -> bool:
    """Prompt to confirm marking a task done. Returns True to proceed, False to abort."""
    try:
        result = await ctx.elicit(
            f"Mark {task_name!r} as done? This closes the task.",
            response_type=bool,
        )
        if isinstance(result, AcceptedElicitation):
            return bool(result.data)
    except Exception as e:
        logger.debug("ctx.elicit unavailable for done confirmation: %s", e)
    return True  # default: proceed if elicitation unavailable


async def check_duplicate_name(ctx: Context, name: str, existing_names: list[str]) -> str | None:
    """Return the matching existing task name if user declines creation, else None.

    Returns the matched name when the user declines or cancels (don't create).
    Returns None to proceed with creation.
    If elicitation is unavailable, defaults to creating (returns None).
    """
    name_lower = name.lower()
    matching = next(
        (n for n in existing_names if name_lower in n.lower() or n.lower() in name_lower),
        None,
    )
    if not matching:
        return None

    try:
        elicit_result = await ctx.elicit(
            f"A task named {matching!r} already exists. Create anyway?",
            response_type=bool,
        )
        if isinstance(elicit_result, AcceptedElicitation):
            return None if elicit_result.data else matching
        # Cancelled or rejected — treat as "don't create".
        return matching
    except Exception as e:
        logger.debug("ctx.elicit unavailable for duplicate check: %s", e)
        return None


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
    updated: list[str] = []
    if status is not None:
        task.status = status
        updated.append("status")
    if priority is not None:
        task.priority = priority
        updated.append("priority")
    if due_date is not None:
        try:
            due_date_dt = datetime.datetime.fromisoformat(
                due_date.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise ToolError(
                f"Invalid due_date format: {due_date}. Use ISO 8601."
            ) from exc
        task.due_date = due_date_dt
        updated.append("due_date")
    if name is not None:
        task.name = sec.scrub(name).clean
        updated.append("name")
    if source_url is not None:
        task.source_url = source_url
        updated.append("source_url")
    return updated
