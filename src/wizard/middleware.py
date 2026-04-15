import logging

from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import CallToolResult

logger = logging.getLogger(__name__)


class ToolLoggingMiddleware(Middleware):
    """Middleware that logs all tool invocations."""

    async def on_call_tool(
        self, context: MiddlewareContext, call_next
    ) -> CallToolResult:
        tool_name = context.params.name
        logger.info(f"{tool_name} ...")
        return await call_next(context)
