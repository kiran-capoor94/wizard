from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus
from wizard.repositories import TaskRepository
from wizard.schemas import TaskRecommendation, WorkRecommendationResponse


def test_task_recommendation_fields():
    rec = TaskRecommendation(
        task_id=1,
        name="Fix auth bug",
        priority="high",
        status="in_progress",
        score=0.87,
        reason="High priority with active momentum",
        momentum="active",
        last_note_preview="Investigating the race condition in token refresh",
    )
    assert rec.task_id == 1
    assert rec.momentum == "active"
    assert rec.last_note_preview is not None


def test_work_recommendation_response_allows_none_recommended():
    resp = WorkRecommendationResponse(
        recommended_task=None,
        alternatives=[],
        skipped_blocked=0,
        message="No open tasks",
    )
    assert resp.recommended_task is None
    assert resp.message == "No open tasks"


def test_get_workable_task_contexts_excludes_done(db_session):
    t1 = Task(name="Open", status=TaskStatus.TODO, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Done", status=TaskStatus.DONE, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Done" not in names


def test_get_workable_task_contexts_excludes_blocked_by_default(db_session):
    t1 = Task(name="Open", status=TaskStatus.TODO, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Blocked", status=TaskStatus.BLOCKED, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Blocked" not in names


def test_get_workable_task_contexts_includes_blocked_when_requested(db_session):
    t1 = Task(name="Open", status=TaskStatus.TODO, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Blocked", status=TaskStatus.BLOCKED, priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session, include_blocked=True)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Blocked" in names
