import datetime as _dt
import logging

from sqlalchemy import Integer
from sqlalchemy import update as _sql_update
from sqlmodel import Session, case, col, func, select

from .models import (
    Meeting,
    Note,
    NoteType,
    Task,
    TaskPriority,
    TaskState,
    TaskStatus,
    WizardSession,
)
from .schemas import MeetingContext, TaskContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_PRIORITY_ORDER = case(
    (col(Task.priority) == TaskPriority.HIGH, 0),
    (col(Task.priority) == TaskPriority.MEDIUM, 1),
    else_=2,
)


# ---------------------------------------------------------------------------
# TaskRepository
# ---------------------------------------------------------------------------


class TaskRepository:

    @staticmethod
    def _latest_note_subquery():
        """Scalar sub-select: created_at of the most recent Note for a given Task."""
        return (
            select(func.max(Note.created_at))
            .where(Note.task_id == Task.id)
            .correlate(Task)
            .scalar_subquery()
            .label("last_worked_at")
        )

    def get(self, db: Session, task_id: int) -> Task | None:
        return db.get(Task, task_id)

    def get_by_id(self, db: Session, task_id: int) -> Task:
        task = db.get(Task, task_id)
        if task is None:
            logger.warning("Task %d not found", task_id)
            raise ValueError(f"Task {task_id} not found")
        return task

    def list_paginated(
        self,
        db: Session,
        status_filter: list[str] | None = None,
        source_type_filter: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        stmt = select(Task)
        if status_filter:
            stmt = stmt.where(Task.status.in_(status_filter))
        if source_type_filter:
            stmt = stmt.where(Task.source_type == source_type_filter)
        stmt = stmt.order_by(Task.id.desc()).offset(offset).limit(limit)
        return list(db.exec(stmt).all())

    def get_by_source_id(self, db: Session, source_id: str) -> Task | None:
        return db.exec(select(Task).where(Task.source_id == source_id)).first()

    def get_open_task_contexts(self, db: Session, limit: int | None = None) -> list[TaskContext]:
        """Open tasks (TODO / IN_PROGRESS) sorted by priority then last-worked desc."""
        return self._query_task_contexts(
            db,
            col(Task.status).in_(
                [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            ),  # pyright: ignore[reportAttributeAccessIssue]
            limit=limit,
        )

    def get_blocked_task_contexts(self, db: Session, limit: int | None = None) -> list[TaskContext]:
        """Blocked tasks sorted by priority then last-worked desc."""
        return self._query_task_contexts(db, Task.status == TaskStatus.BLOCKED, limit=limit)

    def get_workable_task_contexts(
        self, db: Session, include_blocked: bool = False, limit: int | None = None
    ) -> list[TaskContext]:
        """Open + in_progress tasks with task_state joined. Optionally includes blocked."""
        statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
        if include_blocked:
            statuses.append(TaskStatus.BLOCKED)
        return self._query_task_contexts(
            db,
            col(Task.status).in_(statuses),  # pyright: ignore[reportAttributeAccessIssue]
            limit=limit,
        )

    def count_open_tasks(self, db: Session) -> int:
        """Total count of TODO and IN_PROGRESS tasks."""
        stmt = (
            select(func.count())
            .select_from(Task)
            .where(col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        )
        return db.execute(stmt).scalar_one()

    def _query_task_contexts(
        self, db: Session, *where, limit: int | None = None
    ) -> list[TaskContext]:
        last_worked = self._latest_note_subquery()
        stmt = (
            select(Task, last_worked)
            .where(*where)
            .order_by(_PRIORITY_ORDER, func.coalesce(last_worked, 0).desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = db.execute(stmt).all()
        if not rows:
            return []

        tasks: list[Task] = [row[0] for row in rows]
        task_ids = [t.id for t in tasks if t.id is not None]

        # Batch load TaskStates — one query replaces N db.get calls
        task_states: dict[int, TaskState] = {}
        if task_ids:
            for ts in db.execute(
                select(TaskState).where(col(TaskState.task_id).in_(task_ids))
            ).scalars().all():
                task_states[ts.task_id] = ts

        latest_notes = self._batch_load_latest_notes(db, tasks)

        results: list[TaskContext] = []
        for task in tasks:
            tid = task.id
            results.append(TaskContext.from_model(
                task,
                task_states.get(tid) if tid is not None else None,
                latest_notes.get(tid) if tid is not None else None,
            ))
        return results

    def get_task_context(self, db: Session, task: Task) -> TaskContext:
        """Fetch related state and build a TaskContext for a known task."""
        task_state = db.get(TaskState, task.id)
        latest = self._batch_load_latest_notes(db, [task]).get(task.id)
        return TaskContext.from_model(task, task_state, latest)

    def get_task_contexts_by_ids(
        self, db: Session, task_ids: list[int]
    ) -> list[TaskContext]:
        """Batch-load Tasks, TaskStates, and latest notes for a set of IDs."""
        if not task_ids:
            return []
        tasks = list(
            db.execute(select(Task).where(col(Task.id).in_(task_ids))).scalars().all()
        )
        if not tasks:
            return []

        states: dict[int, TaskState] = {}
        for ts in db.execute(
            select(TaskState).where(col(TaskState.task_id).in_(task_ids))
        ).scalars().all():
            states[ts.task_id] = ts

        latest_notes = self._batch_load_latest_notes(db, tasks)

        # Preserve the order of task_ids
        tasks_by_id = {t.id: t for t in tasks}
        results: list[TaskContext] = []
        for tid in task_ids:
            t = tasks_by_id.get(tid)
            if t is not None:
                results.append(TaskContext.from_model(
                    t,
                    states.get(tid),
                    latest_notes.get(tid),
                ))
        return results

    def _batch_load_latest_notes(
        self, db: Session, tasks: list[Task]
    ) -> dict[int, Note]:
        """Batch-load the latest note per task. Returns {task_id: latest_note}."""
        task_ids = [t.id for t in tasks if t.id is not None]
        if not task_ids:
            return {}

        latest: dict[int, Note] = {}
        for n in db.execute(
            select(Note)
            .where(col(Note.task_id).in_(task_ids))
            .order_by(col(Note.created_at).desc())
        ).scalars().all():
            if n.task_id is not None and n.task_id not in latest:
                latest[n.task_id] = n
        return latest


# ---------------------------------------------------------------------------
# MeetingRepository
# ---------------------------------------------------------------------------


class MeetingRepository:
    def get_by_source_id(self, db: Session, source_id: str) -> Meeting | None:
        return db.exec(select(Meeting).where(Meeting.source_id == source_id)).first()

    def get_by_id(self, db: Session, meeting_id: int) -> Meeting:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            logger.warning("Meeting %d not found", meeting_id)
            raise ValueError(f"Meeting {meeting_id} not found")
        return meeting

    def get_unsummarised_contexts(self, db: Session) -> list[MeetingContext]:
        stmt = select(Meeting).where(Meeting.summary == None)  # noqa: E711
        results: list[MeetingContext] = []
        for m in db.exec(stmt).all():
            if m.id is None:
                raise ValueError(f"Meeting row returned without an id: {m}")
            results.append(
                MeetingContext(
                    id=m.id,
                    title=m.title,
                    category=m.category,
                    created_at=m.created_at,
                    already_summarised=False,
                    source_url=m.source_url,
                    source_type=m.source_type,
                )
            )
        return results


# ---------------------------------------------------------------------------
# NoteRepository
# ---------------------------------------------------------------------------


class NoteRepository:
    def save(self, db: Session, note: Note) -> Note:
        db.add(note)
        db.flush()
        db.refresh(note)
        return note

    def get_for_task(
        self,
        db: Session,
        task_id: int | None,
        ascending: bool = False,
    ) -> list[Note]:
        if task_id is None:
            return []
        order = col(Note.created_at).asc() if ascending else col(Note.created_at).desc()
        return list(db.exec(select(Note).where(Note.task_id == task_id).order_by(order)).all())

    def get_notes_grouped_by_task(
        self, db: Session, session_id: int
    ) -> dict[int, list[Note]]:
        """Return notes for a session grouped by task_id, ordered by created_at asc."""
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(col(Note.created_at).asc())
        )
        all_notes = list(db.execute(stmt).scalars().all())
        by_task: dict[int, list[Note]] = {}
        for n in all_notes:
            if n.task_id is not None:
                by_task.setdefault(n.task_id, []).append(n)
        return by_task

    def count_investigations(self, db: Session, task_id: int) -> int:
        """Count investigation notes for a task."""
        stmt = (
            select(func.count())
            .select_from(Note)
            .where(Note.task_id == task_id)
            .where(Note.note_type == NoteType.INVESTIGATION)
        )
        return db.exec(stmt).one()

    def has_mental_model(self, db: Session, task_id: int) -> bool:
        """Check if any note for this task has a mental_model."""
        stmt = (
            select(Note)
            .where(Note.task_id == task_id)
            .where(Note.mental_model.is_not(None))  # type: ignore[union-attr]
            .limit(1)
        )
        return db.exec(stmt).first() is not None

    def list_for_session(self, db: Session, session_id: int) -> list[Note]:
        stmt = (
            select(Note).where(Note.session_id == session_id).order_by(col(Note.created_at).asc())
        )
        return list(db.exec(stmt).all())

    def count_for_session(self, db: Session, session_id: int) -> int:
        return db.exec(
            select(func.count()).select_from(Note).where(Note.session_id == session_id)
        ).one()

    def count_for_sessions(self, db: Session, session_ids: list[int]) -> dict[int, int]:
        """Batch-count notes per session. Returns {session_id: count}."""
        if not session_ids:
            return {}
        stmt = (
            select(Note.session_id, func.count().label("cnt"))
            .where(col(Note.session_id).in_(session_ids))
            .group_by(Note.session_id)
        )
        return {row[0]: row[1] for row in db.execute(stmt).all()}


# ---------------------------------------------------------------------------
# TaskStateRepository
# ---------------------------------------------------------------------------


class TaskStateRepository:
    """Pre-computes derived signals per Task. Updated synchronously by
    create_task / save_note / update_task_status tools — never lazily on read.

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
        last_note_at, last_touched_at, stale_days. Does NOT touch last_status_change_at."""
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state = self._get_or_create(db, task)

        notes = list(db.exec(select(Note).where(Note.task_id == task_id)).all())

        state.note_count = len(notes)
        state.decision_count = sum(
            1 for n in notes if n.note_type == NoteType.DECISION
        )
        state.last_note_at = (
            max(n.created_at for n in notes) if notes else None
        )
        state.last_touched_at = (
            state.last_note_at if state.last_note_at is not None else task.created_at
        )
        state.stale_days = (_dt.datetime.now() - state.last_touched_at).days
        db.add(state)
        db.flush()
        db.refresh(state)
        return state

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


# ---------------------------------------------------------------------------
# SessionRepository
# ---------------------------------------------------------------------------


class SessionRepository:
    def list_paginated(
        self,
        db: Session,
        closure_status_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WizardSession]:
        stmt = select(WizardSession)
        if closure_status_filter:
            stmt = stmt.where(WizardSession.closed_by == closure_status_filter)
        stmt = stmt.order_by(col(WizardSession.created_at).desc()).offset(offset).limit(limit)
        return list(db.exec(stmt).all())

    def count(self, db: Session, closure_status_filter: str | None = None) -> int:
        stmt = select(func.count()).select_from(WizardSession)
        if closure_status_filter:
            stmt = stmt.where(WizardSession.closed_by == closure_status_filter)
        return db.exec(stmt).one()

    def get(self, db: Session, session_id: int) -> WizardSession | None:
        return db.exec(select(WizardSession).where(WizardSession.id == session_id)).first()


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def find_latest_session_with_notes(db: Session) -> WizardSession | None:
    """Most recent WizardSession that has at least one associated Note."""
    subq = select(Note).where(Note.session_id == WizardSession.id).exists()
    stmt = (
        select(WizardSession)
        .where(subq)
        .order_by(col(WizardSession.created_at).desc())
        .limit(1)
    )
    results = db.execute(stmt).scalars().all()
    return results[0] if results else None
