import logging

from sqlmodel import Session

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


async def _log_tool_call(
    db: Session, tool_name: str, session_id: int | None = None
) -> None:
    from ..models import ToolCall

    db.add(ToolCall(tool_name=tool_name, session_id=session_id))
    db.flush()
