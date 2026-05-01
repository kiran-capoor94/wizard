"""Scenario: TaskRepository.get_open_task_index sorts by relevance score."""

import datetime

import pytest

from wizard.models import Task, TaskPriority, TaskState, TaskStatus
from wizard.repositories.task import TaskRepository


@pytest.fixture
def repo():
    return TaskRepository()


def _make_task(db_session, name: str, status: TaskStatus = TaskStatus.TODO) -> Task:
    task = Task(name=name, priority=TaskPriority.MEDIUM, status=status)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)
    return task


def _make_task_state(
    db_session,
    task: Task,
    note_count: int = 0,
    decision_count: int = 0,
    stale_days: int = 0,
    last_note_at: datetime.datetime | None = None,
) -> TaskState:
    state = TaskState(
        task_id=task.id,
        note_count=note_count,
        decision_count=decision_count,
        stale_days=stale_days,
        last_note_at=last_note_at,
        last_touched_at=last_note_at or datetime.datetime.now(),
    )
    db_session.add(state)
    db_session.flush()
    return state


class TestTaskIndexScoring:
    def test_in_progress_with_decisions_ranks_above_stale_todo(self, db_session, repo):
        """in_progress + stale_days=0 scores 70 pts (stale_days +40, IN_PROGRESS +30); todo + stale_days=5 scores 0 pts."""
        stale_todo = _make_task(db_session, "Stale todo task", TaskStatus.TODO)
        _make_task_state(db_session, stale_todo, stale_days=5)

        active = _make_task(db_session, "Active in-progress task", TaskStatus.IN_PROGRESS)
        _make_task_state(db_session, active, decision_count=1, stale_days=0)

        index = repo.get_open_task_index(db_session)
        ids = [e.id for e in index]

        assert ids.index(active.id) < ids.index(stale_todo.id)

    def test_today_touched_ranks_above_older_task(self, db_session, repo):
        """stale_days=0 scores +40 pts; stale_days=3 scores 0 pts — today-touched wins."""
        older = _make_task(db_session, "Older todo task", TaskStatus.TODO)
        _make_task_state(db_session, older, stale_days=3)

        recent = _make_task(db_session, "Recently touched task", TaskStatus.TODO)
        _make_task_state(db_session, recent, stale_days=0)

        index = repo.get_open_task_index(db_session)
        ids = [e.id for e in index]

        assert ids.index(recent.id) < ids.index(older.id)

    def test_note_count_and_decision_signals_add_points(self, db_session, repo):
        """note_count >= 3 (+15) and decision note present (+15) add to score."""
        from wizard.models import Note, NoteType

        plain = _make_task(db_session, "Task with no notes", TaskStatus.TODO)
        _make_task_state(db_session, plain, stale_days=1)

        rich = _make_task(db_session, "Task with notes and decision", TaskStatus.TODO)
        _make_task_state(db_session, rich, stale_days=1)

        # Seed 3 notes including 1 decision to trigger both +15 bonuses
        for i in range(2):
            note = Note(
                note_type=NoteType.INVESTIGATION,
                content=f"Investigation note {i}",
                task_id=rich.id,
            )
            db_session.add(note)
        decision = Note(
            note_type=NoteType.DECISION,
            content="Decided to use adapter pattern",
            task_id=rich.id,
        )
        db_session.add(decision)
        db_session.flush()

        index = repo.get_open_task_index(db_session)
        ids = [e.id for e in index]

        assert ids.index(rich.id) < ids.index(plain.id)
