import logging

from sqlmodel import Session, case, col, func, select

from ..models import Note, Task, TaskPriority, TaskState, TaskStatus
from ..schemas import TaskContext, TaskIndexEntry

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

    def upsert_by_source_id(
        self,
        db: Session,
        source_id: str,
        name: str,
        priority: TaskPriority,
        source_url: str | None,
    ) -> Task | None:
        """Update existing task by source_id if found; return it, or None if not found.

        Does not update done/archived tasks' name or priority.
        """
        existing = self.get_by_source_id(db, source_id)
        if not existing:
            return None
        if existing.status in (TaskStatus.DONE, TaskStatus.ARCHIVED):
            return None
        existing.name = name
        existing.priority = priority
        if source_url and not existing.source_url:
            existing.source_url = source_url
        self.save(db, existing)
        return existing

    def get_active_task_names(self, db: Session) -> list[str]:
        """Return names of all non-done, non-archived tasks."""
        rows = db.exec(
            select(Task.name).where(
                col(Task.status).not_in([TaskStatus.DONE, TaskStatus.ARCHIVED])
            )
        ).all()
        return [r for r in rows if r is not None]

    def get_by_name(self, db: Session, name: str) -> Task | None:
        """Return the first task with an exact name match."""
        rows = db.exec(select(Task).where(Task.name == name)).all()
        return rows[0] if rows else None

    def get_names_by_ids(self, db: Session, task_ids: list[int]) -> list[str]:
        """Return task names for the given IDs, preserving input order where found."""
        rows = db.exec(select(Task.id, Task.name).where(col(Task.id).in_(task_ids))).all()
        name_by_id = {row[0]: row[1] for row in rows if row[0] is not None and row[1] is not None}
        return [name_by_id[tid] for tid in task_ids if tid in name_by_id]

    def get_open_task_contexts(
        self, db: Session, limit: int | None = None
    ) -> list[TaskContext]:
        """Open tasks for resources.py (OpenTasksResource).

        Use get_open_task_index for session_start.
        """
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
        """Blocked tasks for resources.py (BlockedTasksResource).

        Use get_blocked_task_index for session_start.
        """
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

    def _load_task_scaffolding(
        self, db: Session, *where, limit: int | None = None
    ) -> tuple[list[Task], dict[int, TaskState], dict[int, Note]]:
        """Batch-load tasks with states and latest notes. Shared by index and context queries."""
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
            return [], {}, {}

        tasks: list[Task] = [row[0] for row in rows]
        task_ids = [t.id for t in tasks if t.id is not None]

        task_states: dict[int, TaskState] = {}
        if task_ids:
            for ts in db.exec(
                select(TaskState).where(col(TaskState.task_id).in_(task_ids))
            ).all():
                task_states[ts.task_id] = ts

        latest_notes = self._batch_load_latest_notes(db, tasks)
        return tasks, task_states, latest_notes

    def _query_task_contexts(
        self, db: Session, *where, limit: int | None = None
    ) -> list[TaskContext]:
        tasks, task_states, latest_notes = self._load_task_scaffolding(
            db, *where, limit=limit
        )
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

    def _batch_load_notes_by_type(
        self,
        db: Session,
        task_ids: list[int],
    ) -> dict[int, dict[str, int]]:
        """Return {task_id: {note_type_str: count}} for active notes on given tasks."""
        if not task_ids:
            return {}
        rows = db.execute(
            select(Note.task_id, Note.note_type, func.count())
            .where(col(Note.task_id).in_(task_ids))
            .where(Note.status == "active")
            .group_by(Note.task_id, Note.note_type)
        ).all()
        result: dict[int, dict[str, int]] = {}
        for task_id, note_type, count in rows:
            if task_id is not None:
                result.setdefault(task_id, {})[note_type] = count
        return result

    def _query_task_index(
        self,
        db: Session,
        *where,
        limit: int | None = None,
    ) -> list[TaskIndexEntry]:
        """Build compact TaskIndexEntry list for session_start index."""
        tasks, task_states, latest_notes = self._load_task_scaffolding(
            db, *where, limit=limit
        )
        task_ids = [t.id for t in tasks if t.id is not None]
        notes_by_type = self._batch_load_notes_by_type(db, task_ids)

        results: list[TaskIndexEntry] = []
        for task in tasks:
            tid = task.id
            if tid is None:
                continue
            ts = task_states.get(tid)
            latest = latest_notes.get(tid)
            nbt = notes_by_type.get(tid, {})
            results.append(TaskIndexEntry(
                id=tid,
                name=task.name,
                status=task.status,
                priority=task.priority,
                note_count=sum(nbt.values()),
                notes_by_type=nbt,
                last_note_hint=latest.content[:80] if latest else None,
                last_worked_at=ts.last_note_at if ts else None,
                stale_days=ts.stale_days if ts else 0,
            ))
        return results

    def get_open_task_index(
        self,
        db: Session,
        limit: int | None = None,
    ) -> list[TaskIndexEntry]:
        """Compact index of open tasks for session_start."""
        return self._query_task_index(
            db,
            col(Task.status).in_(  # pyright: ignore[reportAttributeAccessIssue]
                [TaskStatus.TODO, TaskStatus.IN_PROGRESS]
            ),
            limit=limit,
        )

    def get_blocked_task_index(
        self,
        db: Session,
        limit: int | None = None,
    ) -> list[TaskIndexEntry]:
        """Compact index of blocked tasks for session_start."""
        return self._query_task_index(
            db, Task.status == TaskStatus.BLOCKED, limit=limit
        )
