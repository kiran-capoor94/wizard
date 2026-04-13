import datetime


def test_task_context_from_model_populates_task_state_fields():
    from wizard.models import Task, TaskPriority, TaskCategory, TaskState, TaskStatus
    from wizard.schemas import TaskContext

    task = Task(
        id=1,
        name="T1",
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
        category=TaskCategory.ISSUE,
        notion_id="notion-abc",
    )
    ts = TaskState(
        task_id=1,
        stale_days=5,
        note_count=3,
        decision_count=1,
        last_note_at=datetime.datetime(2026, 4, 10),
        last_touched_at=datetime.datetime(2026, 4, 10),
    )
    ctx = TaskContext.from_model(task, ts)
    assert ctx.id == 1
    assert ctx.name == "T1"
    assert ctx.notion_id == "notion-abc"
    assert ctx.stale_days == 5
    assert ctx.note_count == 3
    assert ctx.decision_count == 1
    assert ctx.last_worked_at == datetime.datetime(2026, 4, 10)


def test_task_context_from_model_with_latest_note_populates_preview_fields():
    from wizard.models import Note, NoteType, Task, TaskPriority, TaskCategory, TaskStatus
    from wizard.schemas import TaskContext

    task = Task(
        id=3,
        name="T3",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        notion_id=None,
    )
    note = Note(
        id=10,
        note_type=NoteType.DECISION,
        content="A" * 400,  # longer than 300 chars
        source_id=None,
    )
    ctx = TaskContext.from_model(task, None, latest_note=note)
    assert ctx.last_note_type == NoteType.DECISION
    assert ctx.last_note_preview is not None
    assert ctx.last_note_preview == "A" * 300  # truncated at 300
    assert len(ctx.last_note_preview) == 300


def test_task_context_from_model_null_task_state_uses_defaults():
    from wizard.models import Task, TaskPriority, TaskCategory, TaskStatus
    from wizard.schemas import TaskContext

    task = Task(
        id=2,
        name="T2",
        status=TaskStatus.TODO,
        priority=TaskPriority.LOW,
        category=TaskCategory.ISSUE,
        notion_id=None,
    )
    ctx = TaskContext.from_model(task, None)
    assert ctx.notion_id is None
    assert ctx.stale_days == 0
    assert ctx.note_count == 0
    assert ctx.decision_count == 0
    assert ctx.last_worked_at is None


def test_note_detail_from_model_includes_mental_model():
    from wizard.models import Note, NoteType
    from wizard.schemas import NoteDetail

    note = Note(
        id=10,
        note_type=NoteType.DECISION,
        content="We chose SQLite",
        mental_model="Trade-off accepted: consistency for simplicity",
        source_id=None,
    )
    detail = NoteDetail.from_model(note)
    assert detail.mental_model == "Trade-off accepted: consistency for simplicity"


def test_note_detail_from_model_mental_model_none_when_absent():
    from wizard.models import Note, NoteType
    from wizard.schemas import NoteDetail

    note = Note(
        id=11,
        note_type=NoteType.INVESTIGATION,
        content="Looking at options",
        mental_model=None,
        source_id=None,
    )
    detail = NoteDetail.from_model(note)
    assert detail.mental_model is None
