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


def test_meeting_context_has_already_summarised_field():
    from wizard.schemas import MeetingContext, MeetingCategory
    import datetime

    ctx = MeetingContext(
        id=1,
        title="Planning",
        category=MeetingCategory.PLANNING,
        created_at=datetime.datetime(2026, 4, 10),
        already_summarised=True,
        source_url="https://example.com",
        source_type="KRISP",
    )
    assert ctx.already_summarised is True
    assert ctx.source_url == "https://example.com"
    assert ctx.source_type == "KRISP"


def test_timeline_entry_round_trip():
    from wizard.models import NoteType
    from wizard.schemas import TimelineEntry
    import datetime

    entry = TimelineEntry(
        note_id=1,
        created_at=datetime.datetime(2026, 4, 1),
        note_type=NoteType.INVESTIGATION,
        preview="Short preview",
        mental_model=None,
    )
    assert entry.note_id == 1
    assert entry.preview == "Short preview"
    assert entry.mental_model is None


def test_rewind_response_empty_timeline():
    from wizard.models import Task, TaskPriority, TaskCategory, TaskStatus
    from wizard.schemas import RewindResponse, RewindSummary, TaskContext
    import datetime

    task = Task(id=1, name="T", status=TaskStatus.TODO,
                priority=TaskPriority.HIGH, category=TaskCategory.ISSUE)
    ctx = TaskContext.from_model(task, None)
    resp = RewindResponse(
        task=ctx,
        timeline=[],
        summary=RewindSummary(
            total_notes=0,
            duration_days=0,
            last_activity=datetime.datetime(2026, 4, 1),
        ),
    )
    assert resp.timeline == []
    assert resp.summary.total_notes == 0


def test_signal_severity_literal():
    from wizard.schemas import Signal

    s = Signal(type="stale", severity="high", message="No activity for 5 days")
    assert s.severity == "high"
    assert s.type == "stale"


def test_missing_response_empty_signals():
    from wizard.schemas import MissingResponse

    resp = MissingResponse(signals=[])
    assert resp.signals == []


def test_resumed_task_notes_round_trip():
    from wizard.models import Task, TaskPriority, TaskCategory, TaskStatus
    from wizard.schemas import ResumedTaskNotes, TaskContext

    task = Task(id=5, name="T5", status=TaskStatus.TODO,
                priority=TaskPriority.LOW, category=TaskCategory.ISSUE)
    ctx = TaskContext.from_model(task, None)
    rtn = ResumedTaskNotes(task=ctx, notes=[], latest_mental_model=None)
    assert rtn.notes == []
    assert rtn.latest_mental_model is None


def test_resume_session_response_round_trip():
    from wizard.models import Task, TaskPriority, TaskCategory, TaskStatus
    from wizard.schemas import ResumeSessionResponse, TaskContext

    resp = ResumeSessionResponse(
        session_id=2,
        resumed_from_session_id=1,
        session_state=None,
        working_set_tasks=[],
        prior_notes=[],
        unsummarised_meetings=[],
        sync_results=[],
        daily_page=None,
    )
    assert resp.session_id == 2
    assert resp.session_state is None


# ---------------------------------------------------------------------------
# UTCDateTime serializer correctness
# ---------------------------------------------------------------------------


def test_utc_datetime_appends_z_to_naive():
    """Naive datetime (SQLite round-trip) serializes as UTC with Z suffix."""
    import json
    from pydantic import BaseModel
    from wizard.schemas import UTCDateTime

    class M(BaseModel):
        ts: UTCDateTime

    naive = datetime.datetime(2026, 4, 15, 12, 0, 0)
    result = json.loads(M(ts=naive).model_dump_json())
    assert result["ts"] == "2026-04-15T12:00:00Z"


def test_utc_datetime_preserves_already_utc_z():
    """UTC-aware datetime with Z still serializes correctly."""
    import json
    from pydantic import BaseModel
    from wizard.schemas import UTCDateTime

    class M(BaseModel):
        ts: UTCDateTime

    utc_aware = datetime.datetime(2026, 4, 15, 12, 0, 0, tzinfo=datetime.timezone.utc)
    result = json.loads(M(ts=utc_aware).model_dump_json())
    assert result["ts"] == "2026-04-15T12:00:00Z"


def test_utc_datetime_converts_offset_aware_to_utc():
    """Offset-aware datetime (non-UTC) must be *converted* to UTC, not just stripped."""
    import json
    from pydantic import BaseModel
    from wizard.schemas import UTCDateTime

    class M(BaseModel):
        ts: UTCDateTime

    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    ist_dt = datetime.datetime(2026, 4, 15, 17, 30, 0, tzinfo=ist)  # = 12:00 UTC
    result = json.loads(M(ts=ist_dt).model_dump_json())
    # Must be 12:00:00Z, not 17:30:00Z (which is what the old code produced)
    assert result["ts"] == "2026-04-15T12:00:00Z"
