import datetime as _dt
import logging

from sqlalchemy import Integer
from sqlalchemy import update as _sql_update
from sqlmodel import Session, col, func, select

from ..models import Note, NoteType, Task, TaskState
from .note import build_rolling_summary

logger = logging.getLogger(__name__)


class TaskStateRepository:
    """Pre-computes derived signals per Task. Updated synchronously by
    create_task / save_note / update_task tools — never lazily on read.

    stale_days is computed at write time and stored. Status changes do NOT
    reset stale_days; only cognitive activity (note saves) advances it.
    """

    def create_for_task(self, db: Session, task: Task) -> TaskState:
        """Insert a fresh TaskState row for a newly created Task.
        All counts zero; stale_days computed from task.created_at."""
        assert task.id is not None, "Task must be flushed before creating TaskState"
        now = _dt.datetime.now()
        state = TaskState(
            task_id=task.id,
            note_count=0,
            decision_count=0,
            last_note_at=None,
            last_status_change_at=None,
            last_touched_at=task.created_at,
            stale_days=(now - task.created_at).days,
        )
        db.add(state)
        db.flush()
        db.refresh(state)
        return state

    def on_note_saved(self, db: Session, task_id: int) -> TaskState:
        """Re-query notes for the task and recompute note_count, decision_count,
        last_note_at, last_touched_at, stale_days, rolling_summary.
        Does NOT touch last_status_change_at."""
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state = self._get_or_create(db, task)

        notes = list(db.exec(select(Note).where(Note.task_id == task_id)).all())

        state.note_count = len(notes)
        state.decision_count = sum(1 for n in notes if n.note_type == NoteType.DECISION)
        state.last_note_at = max(n.created_at for n in notes) if notes else None
        state.last_touched_at = (
            state.last_note_at if state.last_note_at is not None else task.created_at
        )
        state.stale_days = (_dt.datetime.now() - state.last_touched_at).days
        state.rolling_summary = build_rolling_summary(notes)
        db.add(state)
        db.flush()
        db.refresh(state)
        return state

    def update_rolling_summary(self, db: Session, task_id: int, summary: str) -> None:
        """Overwrite rolling_summary for a task. Used by synthesis after transcript processing."""
        state = db.get(TaskState, task_id)
        if state is None:
            logger.warning(
                "update_rolling_summary: TaskState missing for task %d", task_id
            )
            return
        state.rolling_summary = summary
        db.add(state)
        db.flush()

    def on_status_changed(self, db: Session, task_id: int) -> TaskState:
        """Set last_status_change_at = now. Touches NO other field —
        status change is administrative, not cognitive. stale_days
        deliberately does not reset."""
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        state = self._get_or_create(db, task)
        state.last_status_change_at = _dt.datetime.now()
        db.add(state)
        db.flush()
        db.refresh(state)
        return state

    def refresh_stale_days(self, db: Session) -> None:
        """Recompute stale_days for all tasks based on current wall-clock time.

        Called at session_start so that what_am_i_missing sees up-to-date
        staleness rather than the value frozen at last note-save.

        Uses a single bulk UPDATE via SQLite's julianday() to avoid loading
        all TaskState rows into Python objects."""
        db.execute(
            _sql_update(TaskState).values(
                stale_days=func.cast(
                    func.julianday("now") - func.julianday(TaskState.last_touched_at),
                    Integer,
                )
            )
        )
        db.flush()

    def get_for_tasks(self, db: Session, task_ids: list[int]) -> list[TaskState]:
        if not task_ids:
            return []
        stmt = select(TaskState).where(col(TaskState.task_id).in_(task_ids))
        return list(db.exec(stmt).all())

    def _get_or_create(self, db: Session, task: Task) -> TaskState:
        """Defensive helper: returns the TaskState for `task`, creating one
        with zero counts if missing. Used internally by on_note_saved and
        on_status_changed to handle the gap window between deploy and
        backfill, or any task created before the migration ran."""
        if task.id is None:
            raise ValueError("Task must be flushed before TaskState can be retrieved")
        state = db.get(TaskState, task.id)
        if state is not None:
            return state
        logger.warning(
            "TaskState missing for task %d; creating defensively. "
            "This indicates the task pre-dates the data layer migration "
            "or was inserted outside the create_task tool.",
            task.id,
        )
        return self.create_for_task(db, task)

    def get_by_task_id(self, db: Session, task_id: int) -> TaskState | None:
        return db.get(TaskState, task_id)
