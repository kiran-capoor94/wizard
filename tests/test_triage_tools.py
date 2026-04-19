import pytest

from tests.fakes import FakeContext
from wizard.models import (
    Task,
    TaskCategory,
)
from wizard.models import (
    TaskPriority as ModelTaskPriority,
)
from wizard.models import (
    TaskStatus as ModelTaskStatus,
)
from wizard.repositories import TaskRepository
from wizard.schemas import (
    TaskContext,
    TaskPriority,
    TaskRecommendation,
    TaskStatus,
    WorkRecommendationResponse,
)
from wizard.tools.triage_tools import (
    _classify_momentum,
    _fallback_reason,
    _score_task,
    what_should_i_work_on,
)


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
    t1 = Task(name="Open", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Done", status=ModelTaskStatus.DONE, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Done" not in names


def test_get_workable_task_contexts_excludes_blocked_by_default(db_session):
    t1 = Task(name="Open", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Blocked", status=ModelTaskStatus.BLOCKED, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Blocked" not in names


def test_get_workable_task_contexts_includes_blocked_when_requested(db_session):
    t1 = Task(name="Open", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Blocked", status=ModelTaskStatus.BLOCKED, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    results = TaskRepository().get_workable_task_contexts(db_session, include_blocked=True)
    names = [r.name for r in results]
    assert "Open" in names
    assert "Blocked" in names


def _make_ctx(
    task_id=1,
    name="Test task",
    priority=TaskPriority.HIGH,
    status=TaskStatus.TODO,
    stale_days=0,
    note_count=0,
    decision_count=0,
    last_note_preview=None,
) -> TaskContext:
    return TaskContext(
        id=task_id,
        name=name,
        status=status,
        priority=priority,
        category=TaskCategory.ISSUE,
        due_date=None,
        source_id=None,
        source_url=None,
        last_note_type=None,
        last_note_preview=last_note_preview,
        last_worked_at=None,
        stale_days=stale_days,
        note_count=note_count,
        decision_count=decision_count,
    )


def test_classify_momentum_new():
    ctx = _make_ctx(note_count=0)
    assert _classify_momentum(ctx) == "new"


def test_classify_momentum_active():
    ctx = _make_ctx(note_count=3, stale_days=1)
    assert _classify_momentum(ctx) == "active"


def test_classify_momentum_cooling():
    ctx = _make_ctx(note_count=2, stale_days=5)
    assert _classify_momentum(ctx) == "cooling"


def test_classify_momentum_cold():
    ctx = _make_ctx(note_count=4, stale_days=10)
    assert _classify_momentum(ctx) == "cold"


def test_score_task_focus_prefers_high_priority():
    high = _make_ctx(task_id=1, priority=TaskPriority.HIGH, stale_days=0, note_count=1)
    low = _make_ctx(task_id=2, priority=TaskPriority.LOW, stale_days=0, note_count=1)
    assert _score_task(high, mode="focus") > _score_task(low, mode="focus")


def test_score_task_quick_wins_penalises_complex():
    simple = _make_ctx(task_id=1, priority=TaskPriority.MEDIUM, note_count=0)
    complex_ = _make_ctx(task_id=2, priority=TaskPriority.MEDIUM, note_count=20)
    assert _score_task(simple, mode="quick-wins") > _score_task(complex_, mode="quick-wins")


def test_score_task_30m_boosts_in_progress():
    in_prog = _make_ctx(task_id=1, status=TaskStatus.IN_PROGRESS, note_count=3, stale_days=1)
    todo = _make_ctx(task_id=2, status=TaskStatus.TODO, note_count=0, stale_days=0)
    assert _score_task(in_prog, mode="focus", time_budget="30m") > _score_task(todo, mode="focus", time_budget="30m")


def test_fallback_reason_priority_dominant():
    ctx = _make_ctx(priority=TaskPriority.HIGH, stale_days=2)
    reason = _fallback_reason(ctx, dominant_signal="priority")
    assert "priority" in reason.lower() or "high" in reason.lower()


def test_fallback_reason_recency_dominant():
    ctx = _make_ctx(stale_days=3)
    reason = _fallback_reason(ctx, dominant_signal="recency")
    assert "3" in reason or "ago" in reason.lower() or "resume" in reason.lower()


@pytest.mark.asyncio
async def test_what_should_i_work_on_returns_recommendation(db_session):
    t1 = Task(name="Fix auth", status=ModelTaskStatus.IN_PROGRESS, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Write docs", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.LOW, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    ctx = FakeContext()
    ctx.sample_result = type("R", (), {"content": "High priority in-progress task with active context."})()

    result = await what_should_i_work_on(
        session_id=1,
        ctx=ctx,
        t_repo=TaskRepository(),
        db=db_session,
    )

    assert result.recommended_task is not None
    assert result.recommended_task.name == "Fix auth"
    assert len(result.alternatives) >= 1


@pytest.mark.asyncio
async def test_what_should_i_work_on_no_tasks_returns_none(db_session):
    ctx = FakeContext()
    result = await what_should_i_work_on(
        session_id=1,
        ctx=ctx,
        t_repo=TaskRepository(),
        db=db_session,
    )
    assert result.recommended_task is None
    assert result.message is not None


@pytest.mark.asyncio
async def test_what_should_i_work_on_unblock_mode_filters_to_blocked(db_session):
    t1 = Task(name="Open task", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    t2 = Task(name="Blocked task", status=ModelTaskStatus.BLOCKED, priority=ModelTaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add_all([t1, t2])
    db_session.flush()

    ctx = FakeContext()
    ctx.sample_result = type("R", (), {"content": "Blocked and needs attention."})()

    result = await what_should_i_work_on(
        session_id=1,
        mode="unblock",
        ctx=ctx,
        t_repo=TaskRepository(),
        db=db_session,
    )

    assert result.recommended_task is not None
    assert result.recommended_task.name == "Blocked task"


@pytest.mark.asyncio
async def test_what_should_i_work_on_sampling_failure_uses_fallback(db_session):
    t1 = Task(name="Fix bug", status=ModelTaskStatus.TODO, priority=ModelTaskPriority.HIGH, category=TaskCategory.ISSUE)
    db_session.add(t1)
    db_session.flush()

    ctx = FakeContext()
    ctx.sample_error = RuntimeError("LLM unavailable")

    result = await what_should_i_work_on(
        session_id=1,
        ctx=ctx,
        t_repo=TaskRepository(),
        db=db_session,
    )

    assert result.recommended_task is not None
    assert len(result.recommended_task.reason) > 0


def test_get_open_task_contexts_respects_limit(db_session):
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus
    from wizard.repositories import TaskRepository

    for i in range(5):
        t = Task(
            name=f"Task {i}",
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.ISSUE,
        )
        db_session.add(t)
    db_session.flush()

    repo = TaskRepository()
    results = repo.get_open_task_contexts(db_session, limit=3)
    assert len(results) == 3


def test_get_open_task_contexts_no_limit_returns_all(db_session):
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus
    from wizard.repositories import TaskRepository

    for i in range(5):
        t = Task(
            name=f"Task {i}",
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.ISSUE,
        )
        db_session.add(t)
    db_session.flush()

    repo = TaskRepository()
    results = repo.get_open_task_contexts(db_session)
    assert len(results) == 5


def test_count_open_tasks_returns_full_count(db_session):
    from wizard.models import Task, TaskCategory, TaskPriority, TaskStatus
    from wizard.repositories import TaskRepository

    for i in range(4):
        t = Task(
            name=f"Task {i}",
            status=TaskStatus.TODO,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.ISSUE,
        )
        db_session.add(t)
    db_session.flush()

    repo = TaskRepository()
    assert repo.count_open_tasks(db_session) == 4
