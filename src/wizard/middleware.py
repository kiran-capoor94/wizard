import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

from .database import get_session
from .models import ToolCall

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
