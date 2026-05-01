"""Shared notification utilities for MCP tool responses."""

import contextlib
from typing import Any, Coroutine

import anyio


async def try_notify(coro: Coroutine[Any, Any, None]) -> None:
    """Run a ctx.info / ctx.report_progress / ctx.debug call, ignoring closed-transport errors."""
    with contextlib.suppress(anyio.ClosedResourceError, anyio.BrokenResourceError):
        await coro
