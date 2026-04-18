import datetime
import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from sqlmodel import select as sa_select

from .database import get_session
from .models import Note, ToolCall, WizardSession
from .schemas import SessionState

logger = logging.getLogger(__name__)


class ToolLoggingMiddleware(Middleware):
    """Middleware that logs tool invocations and records ToolCall rows."""

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> ToolResult:
        tool_name = context.message.name
        logger.info("%s ...", tool_name)

        session_id = None
        if context.fastmcp_context is not None:
            session_id = await context.fastmcp_context.get_state("current_session_id")

        with get_session() as db:
            db.add(ToolCall(tool_name=tool_name, session_id=session_id))
            db.flush()

        return await call_next(context)


class SessionStateMiddleware(Middleware):
    """Middleware that snapshots session state on every tool call.

    Updates WizardSession.last_active_at and incrementally builds
    a partial SessionState (working_set from notes) so that abandoned
    sessions have recoverable state.
    """

    _SKIP_TOOLS = frozenset({"session_start", "session_end"})

    async def on_call_tool(self, context: MiddlewareContext, call_next) -> ToolResult:
        result = await call_next(context)

        tool_name = context.message.name
        if tool_name in self._SKIP_TOOLS:
            return result

        try:
            if context.fastmcp_context is not None:
                session_id = await context.fastmcp_context.get_state(
                    "current_session_id"
                )
                if session_id is not None:
                    with get_session() as db:
                        self.snapshot_session_state(db, session_id)
        except Exception as e:
            logger.warning("SessionStateMiddleware failed: %s", e)

        return result

    def snapshot_session_state(self, db, session_id: int) -> None:
        """Update last_active_at and session_state on the WizardSession.

        Public so tests can call this directly (tests bypass the FastMCP
        middleware chain).
        """
        session = db.get(WizardSession, session_id)
        if session is None:
            return

        session.last_active_at = datetime.datetime.now()

        task_ids_rows = db.exec(
            sa_select(Note.task_id)
            .where(
                Note.session_id == session_id,
                Note.task_id != None,  # noqa: E711
            )
            .distinct()
        ).all()
        working_set = [tid for tid in task_ids_rows if tid is not None]

        state = SessionState(
            intent="",
            working_set=working_set,
            state_delta="",
            open_loops=[],
            next_actions=[],
            closure_status="interrupted",
        )
        session.session_state = state.model_dump_json()
        db.add(session)
        db.flush()
