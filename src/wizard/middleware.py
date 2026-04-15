import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult

logger = logging.getLogger(__name__)


class ToolLoggingMiddleware(Middleware):
    """Middleware that logs all tool invocations."""

    async def on_call_tool(
        self, context: MiddlewareContext, call_next
    ) -> ToolResult:
        tool_name = context.message.name
        logger.info("%s ...", tool_name)
        return await call_next(context)
