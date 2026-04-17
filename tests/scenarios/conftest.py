"""Scenario-specific fixtures: seed data helpers."""

import pytest
from sqlmodel import Session

from wizard.models import Task, TaskCategory, TaskPriority, TaskState, TaskStatus


@pytest.fixture
def seed_task(db_session: Session):
    """Factory fixture: creates a task with a TaskState and returns it."""

    def _create(
        name: str = "Test task",
        priority: TaskPriority = TaskPriority.MEDIUM,
        category: TaskCategory = TaskCategory.ISSUE,
        status: TaskStatus = TaskStatus.TODO,
        source_id: str | None = None,
        source_url: str | None = None,
        notion_id: str | None = None,
    ) -> Task:
        task = Task(
            name=name,
            priority=priority,
            category=category,
            status=status,
            source_id=source_id,
            source_url=source_url,
            notion_id=notion_id,
        )
        db_session.add(task)
        db_session.flush()
        db_session.refresh(task)
        assert task.id is not None

        task_state = TaskState(
            task_id=task.id,
            last_touched_at=task.created_at,
        )
        db_session.add(task_state)
        db_session.flush()
        return task

    return _create
