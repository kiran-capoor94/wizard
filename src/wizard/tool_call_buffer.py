import asyncio
import logging

from .database import get_session
from .models import ToolCall

logger = logging.getLogger(__name__)

_DRAIN_INTERVAL = 30


class ToolCallBuffer:
    """Buffers ToolCall rows and persists them in batches.

    Enqueue on every tool call (no DB touch). A background drain task
    flushes every 30 seconds. flush_now() drains immediately — call it
    from session_end before the session closes.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[ToolCall] = asyncio.Queue()
        self._drain_task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background drain task. Call once at server startup."""
        if self._drain_task is None or self._drain_task.done():
            self._drain_task = asyncio.create_task(self._drain_loop())

    def enqueue(self, tool_name: str, session_id: int | None) -> None:
        self._queue.put_nowait(ToolCall(tool_name=tool_name, session_id=session_id))

    async def flush_now(self, db) -> None:
        """Drain all queued items into db. Caller owns the session/commit."""
        items: list[ToolCall] = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if items:
            db.add_all(items)
            db.flush()

    async def _drain_loop(self) -> None:
        while True:
            await asyncio.sleep(_DRAIN_INTERVAL)
            try:
                items: list[ToolCall] = []
                while not self._queue.empty():
                    try:
                        items.append(self._queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                if items:
                    with get_session() as db:
                        db.add_all(items)
            except Exception as e:
                logger.warning("ToolCallBuffer drain failed: %s", e)


tool_call_buffer = ToolCallBuffer()
