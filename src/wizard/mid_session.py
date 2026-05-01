"""Background mid-session synthesis state."""
import asyncio

MID_SESSION_TASKS: dict[str, asyncio.Task[None]] = {}
_lock = asyncio.Lock()


async def register_mid_session_task(agent_session_id: str, task: asyncio.Task[None]) -> None:
    async with _lock:
        existing = MID_SESSION_TASKS.pop(agent_session_id, None)
        if existing:
            existing.cancel()
        MID_SESSION_TASKS[agent_session_id] = task


def cancel_mid_session_synthesis(agent_session_id: str) -> None:
    # dict.pop() is atomic under asyncio's single-threaded model; no await
    # between pop and cancel means no lock is needed here.
    task = MID_SESSION_TASKS.pop(agent_session_id, None)
    if task:
        task.cancel()
