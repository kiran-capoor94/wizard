"""Compact, read-only session brief for proactive recall injection (SessionStart hook)."""
from __future__ import annotations

from sqlmodel import Session, create_engine

from .models import TaskStatus
from .repositories import SessionRepository, TaskRepository

_BRIEF_MAX_LINES = 25
_SUMMARY_MAX_CHARS = 160
_TOP_TASKS = 5


def render_brief(db: Session) -> str:
    """Render a compact memory brief from an open DB session. '' when nothing to show."""
    t_repo = TaskRepository()
    s_repo = SessionRepository()

    open_total = t_repo.count_open_tasks(db)
    open_index = t_repo.get_open_task_index(db, limit=_TOP_TASKS)
    blocked = t_repo.get_blocked_task_index(db)
    # No live session exists yet at SessionStart-hook time; pass -1 so nothing is excluded.
    summaries = s_repo.get_prior_summaries(db, current_session_id=-1)

    if open_total == 0 and not blocked and not summaries:
        return ""

    lines: list[str] = [
        f"[wizard memory] {open_total} open task(s), {len(blocked)} blocked."
    ]
    for e in open_index:
        tag = "in-progress" if e.status == TaskStatus.IN_PROGRESS else f"stale {e.stale_days}d"
        lines.append(f"  - #{e.id} {e.name} ({tag})")
    if summaries:
        summary = summaries[0].summary.replace("\n", " ").strip()[:_SUMMARY_MAX_CHARS]
        lines.append(f"Last session: {summary}")

    return "\n".join(lines[:_BRIEF_MAX_LINES])


def build_session_brief(db_path: str) -> str:
    """Open db_path READ-ONLY and render the brief. Returns '' on any error/empty DB.

    Never raises — this feeds a hook that must not interrupt the agent.
    """
    try:
        engine = create_engine(
            f"sqlite:///{db_path}?mode=ro", connect_args={"uri": True}
        )
        with Session(engine) as db:
            return render_brief(db)
    except Exception:
        return ""
