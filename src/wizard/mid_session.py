"""Background mid-session synthesis state."""
import asyncio

MID_SESSION_TASKS: dict[str, asyncio.Task] = {}


def cancel_mid_session_synthesis(agent_session_id: str) -> None:
    task = MID_SESSION_TASKS.pop(agent_session_id, None)
    if task:
        task.cancel()
