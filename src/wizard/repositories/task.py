import logging

from sqlmodel import Session, case, col, func, select

from ..models import Note, Task, TaskPriority, TaskState, TaskStatus
from ..schemas import TaskContext

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = case(
    (col(Task.priority) == TaskPriority.HIGH, 0),
    (col(Task.priority) == TaskPriority.MEDIUM, 1),
    else_=2,
)


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

    def save(self, db: Session, task: Task) -> Task:
        """Persist a Task to the database."""
        db.add(task)
        db.flush()
        db.refresh(task)
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
            stmt = stmt.where(col(Task.status).in_(status_filter))
        if source_type_filter:
            stmt = stmt.where(Task.source_type == source_type_filter)
        stmt = stmt.order_by(col(Task.id).desc()).offset(offset).limit(limit)
        return list(db.exec(stmt).all())

    def get_by_source_id(self, db: Session, source_id: str) -> Task | None:
        return db.exec(select(Task).where(Task.source_id == source_id)).first()

    def get_open_task_contexts(
        self, db: Session, limit: int | None = None
    ) -> list[TaskContext]:
        """Open tasks (TODO / IN_PROGRESS) sorted by priority then last-worked desc."""
        return self._query_task_contexts(
            db,
            col(Task.status).in_(
                [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            ),  # pyright: ignore[reportAttributeAccessIssue]
            limit=limit,
        )

    def get_blocked_task_contexts(
        self, db: Session, limit: int | None = None
    ) -> list[TaskContext]:
        """Blocked tasks sorted by priority then last-worked desc."""
        return self._query_task_contexts(
            db, Task.status == TaskStatus.BLOCKED, limit=limit
        )

    def get_workable_task_contexts(
        self, db: Session, include_blocked: bool = False, limit: int | None = None
    ) -> list[TaskContext]:
        """Open + in_progress tasks with task_state joined. Optionally includes blocked."""
        statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
        if include_blocked:
            statuses.append(TaskStatus.BLOCKED)
        return self._query_task_contexts(
            db,
            col(Task.status).in_(
                statuses
            ),  # pyright: ignore[reportAttributeAccessIssue]
            limit=limit,
        )

    def count_open_tasks(self, db: Session) -> int:
        """Total count of TODO and IN_PROGRESS tasks."""
        stmt = (
            select(func.count())
            .select_from(Task)
            .where(col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
        )
        return db.exec(stmt).one()

    def get_open_tasks_compact(
        self, db: Session, limit: int = 40
    ) -> list[tuple[int, str]]:
        """Return (id, name) pairs for open tasks. Used by synthesis for task matching."""
        stmt = (
            select(Task.id, Task.name)
            .where(col(Task.status).in_([TaskStatus.TODO, TaskStatus.IN_PROGRESS]))
            .order_by(_PRIORITY_ORDER)
            .limit(limit)
        )
        return [(row[0], row[1]) for row in db.execute(stmt).all()]  # type: ignore

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
        rows = db.execute(stmt).all()  # type: ignore
        if not rows:
            return []

        tasks: list[Task] = [row[0] for row in rows]
        task_ids = [t.id for t in tasks if t.id is not None]

        task_states: dict[int, TaskState] = {}
        if task_ids:
            for ts in db.exec(
                select(TaskState).where(col(TaskState.task_id).in_(task_ids))
            ).all():
                task_states[ts.task_id] = ts

        latest_notes = self._batch_load_latest_notes(db, tasks)

        results: list[TaskContext] = []
        for task in tasks:
            tid = task.id
            results.append(
                TaskContext.from_model(
                    task,
                    task_states.get(tid) if tid is not None else None,
                    latest_notes.get(tid) if tid is not None else None,
                )
            )
        return results

    def get_task_context(self, db: Session, task: Task) -> TaskContext:
        """Fetch related state and build a TaskContext for a known task."""
        task_id = task.id
        assert task_id is not None, "Task must be persisted before fetching context"
        task_state = db.get(TaskState, task_id)
        latest = self._batch_load_latest_notes(db, [task]).get(task_id)
        return TaskContext.from_model(task, task_state, latest)

    def get_task_contexts_by_ids(
        self, db: Session, task_ids: list[int]
    ) -> list[TaskContext]:
        """Batch-load Tasks, TaskStates, and latest notes for a set of IDs."""
        if not task_ids:
            return []
        tasks = list(db.exec(select(Task).where(col(Task.id).in_(task_ids))).all())
        if not tasks:
            return []

        states: dict[int, TaskState] = {}
        for ts in db.exec(
            select(TaskState).where(col(TaskState.task_id).in_(task_ids))
        ).all():
            states[ts.task_id] = ts

        latest_notes = self._batch_load_latest_notes(db, tasks)

        tasks_by_id = {t.id: t for t in tasks}
        results: list[TaskContext] = []
        for tid in task_ids:
            t = tasks_by_id.get(tid)
            if t is not None:
                results.append(
                    TaskContext.from_model(
                        t,
                        states.get(tid),
                        latest_notes.get(tid),
                    )
                )
        return results

    def _batch_load_latest_notes(
        self, db: Session, tasks: list[Task]
    ) -> dict[int, Note]:
        """Batch-load the latest note per task. Returns {task_id: latest_note}."""
        task_ids = [t.id for t in tasks if t.id is not None]
        if not task_ids:
            return {}

        latest: dict[int, Note] = {}
        for n in db.exec(
            select(Note)
            .where(col(Note.task_id).in_(task_ids))
            .order_by(col(Note.created_at).desc())
        ).all():
            if n.task_id is not None and n.task_id not in latest:
                latest[n.task_id] = n
        return latest
