import logging

from sqlmodel import Session, case, col, func, select, or_

from .models import (
    Meeting,
    Note,
    Task,
    TaskPriority,
    TaskStatus,
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
                Note.source_id == Task.source_id,
            )
        )
        .correlate(Task)
        .scalar_subquery()
        .label("last_worked_at")
    )


def _task_context_from_row(
    task: Task, last_worked_at, latest_note: Note | None
) -> TaskContext:
    assert task.id is not None
    return TaskContext(
        id=task.id,
        name=task.name,
        status=task.status,
        priority=task.priority,
        category=task.category,
        due_date=task.due_date,
        source_id=task.source_id,
        source_url=task.source_url,
        last_note_type=latest_note.note_type if latest_note else None,
        last_note_preview=latest_note.content[:300] if latest_note else None,
        last_worked_at=last_worked_at,
    )


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
        rows = db.exec(stmt).all()

        results: list[TaskContext] = []
        for task, lw_at in rows:
            latest = self._latest_note_for(db, task)
            results.append(_task_context_from_row(task, lw_at, latest))
        return results

    def build_task_context(self, db: Session, task: Task) -> TaskContext:
        """Build a single TaskContext for a known task."""
        latest = self._latest_note_for(db, task)
        return _task_context_from_row(
            task,
            latest.created_at if latest else None,
            latest,
        )

    def _latest_note_for(self, db: Session, task: Task) -> Note | None:
        conditions = []
        if task.id is not None:
            conditions.append(Note.task_id == task.id)
        if task.source_id is not None:
            conditions.append(Note.source_id == task.source_id)
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
            assert m.id is not None
            results.append(
                MeetingContext(
                    id=m.id,
                    title=m.title,
                    category=m.category,
                    created_at=m.created_at,
                    has_summary=False,
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
            conditions.append(Note.source_id == source_id)
        if not conditions:
            return []
        stmt = (
            select(Note).where(or_(*conditions)).order_by(col(Note.created_at).desc())
        )
        return list(db.exec(stmt).all())
