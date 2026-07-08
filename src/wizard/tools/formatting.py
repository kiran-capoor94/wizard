"""Shared notification utilities for MCP tool responses."""

import asyncio
import contextlib
from typing import Any, Coroutine

import anyio


async def try_notify(coro: Coroutine[Any, Any, None]) -> None:
    """Run a ctx.info / ctx.report_progress / ctx.debug call, ignoring closed-transport errors."""
    with contextlib.suppress(anyio.ClosedResourceError, anyio.BrokenResourceError):
        await coro


_background_tasks: set[asyncio.Task] = set()


def spawn_background(coro: Coroutine[Any, Any, None]) -> None:
    """asyncio.create_task() without keeping a reference lets the event loop
    hold only a weak reference — the task can be garbage-collected mid-flight.
    Keep a strong reference until it completes."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
