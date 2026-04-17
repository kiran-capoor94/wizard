import datetime as _dt
import logging

from sqlmodel import Session, and_, case, col, func, select, or_

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


def _latest_note_subquery():
    """Scalar sub-select: created_at of the most recent Note for a given Task."""
    return (
        select(func.max(Note.created_at))
        .where(
            or_(
                Note.task_id == Task.id,
                and_(
                    Note.source_id == Task.source_id,
                    Note.source_type == "JIRA",
                ),
            )
        )
        .correlate(Task)
        .scalar_subquery()
        .label("last_worked_at")
    )


def _task_context_from_row(
    task: Task,
    task_state: TaskState | None,
    latest_note: Note | None = None,
) -> TaskContext:
    return TaskContext.from_model(task, task_state, latest_note)


# ---------------------------------------------------------------------------
# TaskRepository
# ---------------------------------------------------------------------------


class TaskRepository:
    def get_by_id(self, db: Session, task_id: int) -> Task:
        task = db.get(Task, task_id)
        if task is None:
            logger.warning("Task %d not found", task_id)
            raise ValueError(f"Task {task_id} not found")
        return task

    def get_open_task_contexts(self, db: Session) -> list[TaskContext]:
        """Open tasks (TODO / IN_PROGRESS) sorted by priority then last-worked desc."""
        return self._query_task_contexts(
            db,
            col(Task.status).in_(
                [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            ),  # pyright: ignore[reportAttributeAccessIssue]
        )

    def get_blocked_task_contexts(self, db: Session) -> list[TaskContext]:
        """Blocked tasks sorted by priority then last-worked desc."""
        return self._query_task_contexts(db, Task.status == TaskStatus.BLOCKED)

    def _query_task_contexts(self, db: Session, *where) -> list[TaskContext]:
        last_worked = _latest_note_subquery()
        stmt = (
            select(Task, last_worked)
            .where(*where)
            .order_by(_PRIORITY_ORDER, func.coalesce(last_worked, 0).desc())
        )
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

        # Batch load latest note per task — one query replaces N _latest_note_for calls
        jira_source_ids = [t.source_id for t in tasks if t.source_id is not None]
        source_id_to_task_id: dict[str, int] = {
            t.source_id: t.id
            for t in tasks
            if t.source_id is not None and t.id is not None
        }
        note_conditions: list = []
        if task_ids:
            note_conditions.append(col(Note.task_id).in_(task_ids))
        if jira_source_ids:
            note_conditions.append(
                and_(col(Note.source_id).in_(jira_source_ids), Note.source_type == "JIRA")
            )
        latest_notes: dict[int, Note] = {}
        if note_conditions:
            for n in db.execute(
                select(Note)
                .where(or_(*note_conditions))
                .order_by(col(Note.created_at).desc())
            ).scalars().all():
                if n.task_id is not None:
                    if n.task_id not in latest_notes:
                        latest_notes[n.task_id] = n
                elif n.source_id is not None and n.source_type == "JIRA":
                    tid = source_id_to_task_id.get(n.source_id)
                    if tid is not None and tid not in latest_notes:
                        latest_notes[tid] = n

        results: list[TaskContext] = []
        for task in tasks:
            tid = task.id
            results.append(_task_context_from_row(
                task,
                task_states.get(tid) if tid is not None else None,
                latest_notes.get(tid) if tid is not None else None,
            ))
        return results

    def build_task_context(self, db: Session, task: Task) -> TaskContext:
        """Build a single TaskContext for a known task."""
        task_state = db.get(TaskState, task.id)
        latest = self._latest_note_for(db, task)
        return _task_context_from_row(task, task_state, latest)

    def _latest_note_for(self, db: Session, task: Task) -> Note | None:
        conditions = []
        if task.id is not None:
            conditions.append(Note.task_id == task.id)
        if task.source_id is not None:
            conditions.append(
                and_(Note.source_id == task.source_id, Note.source_type == "JIRA")
            )
        if not conditions:
            return None
        stmt = (
            select(Note)
            .where(or_(*conditions))
            .order_by(col(Note.created_at).desc())
            .limit(1)
        )
        return db.exec(stmt).first()


# ---------------------------------------------------------------------------
# MeetingRepository
# ---------------------------------------------------------------------------


class MeetingRepository:
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
        source_id: str | None,
    ) -> list[Note]:
        conditions = []
        if task_id is not None:
            conditions.append(Note.task_id == task_id)
        if source_id is not None:
            conditions.append(
                and_(Note.source_id == source_id, Note.source_type == "JIRA")
            )
        if not conditions:
            return []
        stmt = (
            select(Note).where(or_(*conditions)).order_by(col(Note.created_at).desc())
        )
        return list(db.exec(stmt).all())

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
        """Re-query notes for the task (dual-lookup: by task_id OR by Jira
        source_id) and recompute note_count, decision_count, last_note_at,
        last_touched_at, stale_days. Does NOT touch last_status_change_at."""
        task = db.get(Task, task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        state = self._get_or_create(db, task)

        conditions: list = [Note.task_id == task_id]
        if task.source_id is not None:
            conditions.append(
                and_(Note.source_id == task.source_id, Note.source_type == "JIRA")
            )
        notes = list(db.exec(select(Note).where(or_(*conditions))).all())

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
        staleness rather than the value frozen at last note-save."""
        now = _dt.datetime.now()
        for state in db.exec(select(TaskState)).all():
            state.stale_days = (now - state.last_touched_at).days
            db.add(state)
        db.flush()

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
