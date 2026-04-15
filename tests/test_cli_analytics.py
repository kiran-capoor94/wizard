import datetime


def test_query_sessions_empty_period(db_session):
    from wizard.cli.analytics import query_sessions
    start = datetime.date(2026, 1, 1)
    end = datetime.date(2026, 1, 7)
    result = query_sessions(db_session, start, end)
    assert result["session_count"] == 0
    assert result["avg_duration_minutes"] == 0.0
    assert result["total_tool_calls"] == 0


def test_query_sessions_counts_tool_calls(db_session):
    import datetime as dt
    from wizard.cli.analytics import query_sessions

    from wizard.models import ToolCall
    now = dt.datetime(2026, 1, 3, 10, 0, 0)
    db_session.add(ToolCall(tool_name="session_start", called_at=now, session_id=1))
    db_session.add(ToolCall(tool_name="session_end", called_at=now + dt.timedelta(minutes=30), session_id=1))
    db_session.add(ToolCall(tool_name="save_note", called_at=now + dt.timedelta(minutes=10), session_id=1))
    db_session.commit()

    start = datetime.date(2026, 1, 1)
    end = datetime.date(2026, 1, 7)
    result = query_sessions(db_session, start, end)
    assert result["session_count"] == 1
    assert result["total_tool_calls"] == 3


def test_query_notes_empty(db_session):
    from wizard.cli.analytics import query_notes
    import datetime
    result = query_notes(db_session, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))
    assert result["total"] == 0
    assert result["by_type"] == {}
    assert result["mental_model_coverage"] == 0.0


def test_query_notes_counts_by_type(db_session):
    import datetime as dt
    from wizard.cli.analytics import query_notes

    from wizard.models import Note, NoteType, Task, TaskStatus, TaskPriority, TaskCategory
    task = Task(
        name="T1",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
    )
    db_session.add(task)
    db_session.flush()
    db_session.add(Note(
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="findings",
        created_at=dt.datetime(2026, 1, 3),
        mental_model="model A",
    ))
    db_session.add(Note(
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="decided",
        created_at=dt.datetime(2026, 1, 4),
        mental_model=None,
    ))
    db_session.commit()

    result = query_notes(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result["total"] == 2
    assert result["by_type"]["investigation"] == 1
    assert result["by_type"]["decision"] == 1
    assert result["mental_models_captured"] == 1
    assert result["mental_model_coverage"] == 0.5


def test_query_tasks_empty(db_session):
    import datetime
    from wizard.cli.analytics import query_tasks
    result = query_tasks(db_session, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))
    assert result["worked"] == 0
    assert result["avg_notes_per_task"] == 0.0
    assert result["stale_count"] == 0


def test_query_compounding_no_calls(db_session):
    import datetime
    from wizard.cli.analytics import query_compounding
    result = query_compounding(db_session, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))
    assert result == 0.0


def test_query_compounding_empty_db_returns_zero(db_session):
    from wizard.cli.analytics import query_compounding
    import datetime
    result = query_compounding(db_session, datetime.date(2026, 1, 1), datetime.date(2026, 1, 7))
    assert result == 0.0


def test_query_compounding_no_prior_notes_returns_zero(db_session):
    """task_start exists in window and notes exist, but all notes are from this window."""
    import datetime as dt
    from wizard.cli.analytics import query_compounding
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority, ToolCall

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    session_start_time = dt.datetime(2026, 1, 3, 9, 0, 0)
    # Note created AFTER session_start but BEFORE task_start — same session, not prior context
    # Old code: note.created_at (9:30) < task_start.called_at (10:00) → True → wrongly compounding
    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="first note", created_at=dt.datetime(2026, 1, 3, 9, 30, 0),
    ))
    db_session.add(ToolCall(tool_name="session_start", called_at=session_start_time, session_id=1))
    db_session.add(ToolCall(tool_name="task_start", called_at=dt.datetime(2026, 1, 3, 10, 0, 0), session_id=1))
    db_session.commit()

    result = query_compounding(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result == 0.0


def test_query_compounding_prior_session_notes_returns_nonzero(db_session):
    """Notes from before the window's first session indicate prior-session context."""
    import datetime as dt
    from wizard.cli.analytics import query_compounding
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority, ToolCall

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    # Note from a prior session (before the window's first session_start)
    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="prior session note", created_at=dt.datetime(2025, 12, 20, 10, 0, 0),
    ))
    session_start_time = dt.datetime(2026, 1, 3, 9, 0, 0)
    db_session.add(ToolCall(tool_name="session_start", called_at=session_start_time, session_id=1))
    db_session.add(ToolCall(tool_name="task_start", called_at=dt.datetime(2026, 1, 3, 9, 5, 0), session_id=1))
    db_session.commit()

    result = query_compounding(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result == 1.0


def test_query_tasks_ignores_session_summary_notes(db_session):
    """Notes with task_id=None must not inflate 'tasks worked'."""
    import datetime as dt
    from wizard.cli.analytics import query_tasks
    from wizard.models import Note, NoteType

    db_session.add(Note(
        task_id=None,
        note_type=NoteType.SESSION_SUMMARY,
        content="session wrap-up",
        created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.commit()

    result = query_tasks(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result["worked"] == 0
    assert result["avg_notes_per_task"] == 0.0


def test_query_tasks_counts_only_task_notes(db_session):
    """task notes and non-task notes coexist — only task notes are counted."""
    import datetime as dt
    from wizard.cli.analytics import query_tasks
    from wizard.models import Note, NoteType, Task, TaskStatus, TaskCategory, TaskPriority

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.MEDIUM, category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    db_session.add(Note(
        task_id=task.id, note_type=NoteType.INVESTIGATION,
        content="task note", created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.add(Note(
        task_id=None, note_type=NoteType.SESSION_SUMMARY,
        content="session note", created_at=dt.datetime(2026, 1, 3),
    ))
    db_session.commit()

    result = query_tasks(db_session, dt.date(2026, 1, 1), dt.date(2026, 1, 7))
    assert result["worked"] == 1
    assert result["avg_notes_per_task"] == 1.0


def test_format_table_renders_sections(db_session):
    import datetime
    from wizard.cli.analytics import format_table
    data = {
        "sessions": {"session_count": 3, "avg_duration_minutes": 42.5, "total_tool_calls": 27},
        "notes": {"total": 12, "by_type": {"investigation": 5, "decision": 7}, "mental_model_coverage": 0.75},
        "tasks": {"worked": 4, "avg_notes_per_task": 3.0, "stale_count": 1},
        "compounding": 0.67,
    }
    start = datetime.date(2026, 1, 6)
    end = datetime.date(2026, 1, 12)
    output = format_table(data, start, end)
    assert "sessions" in output.lower() or "Sessions" in output
    assert "3" in output
    assert "42" in output
    assert "notes" in output.lower() or "Notes" in output


def test_analytics_cli_week_option(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(tmp_path / "wizard.db"))
    db_path = tmp_path / "wizard.db"
    db_path.touch()  # file must exist so doctor-like check passes

    with patch("wizard.cli.main.analytics_module") as mock_analytics, \
         patch("wizard.cli.main.get_db_session") as mock_db:
        mock_db.return_value.__enter__ = lambda s: s
        mock_db.return_value.__exit__ = lambda s, *a: None
        mock_analytics.query_sessions.return_value = {"session_count": 0, "avg_duration_minutes": 0.0, "total_tool_calls": 0}
        mock_analytics.query_notes.return_value = {"total": 0, "by_type": {}, "mental_models_captured": 0, "mental_model_coverage": 0.0}
        mock_analytics.query_tasks.return_value = {"worked": 0, "avg_notes_per_task": 0.0, "stale_count": 0}
        mock_analytics.query_compounding.return_value = 0.0
        mock_analytics.format_table.return_value = "table output"
        from typer.testing import CliRunner
        from wizard.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["analytics", "--week"])
    assert result.exit_code == 0


def test_analytics_cli_from_to_range(tmp_path, monkeypatch):
    from unittest.mock import patch
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setenv("WIZARD_DB", str(tmp_path / "wizard.db"))
    db_path = tmp_path / "wizard.db"
    db_path.touch()

    with patch("wizard.cli.main.analytics_module") as mock_analytics, \
         patch("wizard.cli.main.get_db_session") as mock_db:
        mock_db.return_value.__enter__ = lambda s: s
        mock_db.return_value.__exit__ = lambda s, *a: None
        mock_analytics.query_sessions.return_value = {"session_count": 0, "avg_duration_minutes": 0.0, "total_tool_calls": 0}
        mock_analytics.query_notes.return_value = {"total": 0, "by_type": {}, "mental_models_captured": 0, "mental_model_coverage": 0.0}
        mock_analytics.query_tasks.return_value = {"worked": 0, "avg_notes_per_task": 0.0, "stale_count": 0}
        mock_analytics.query_compounding.return_value = 0.0
        mock_analytics.format_table.return_value = "table output"
        from typer.testing import CliRunner
        from wizard.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["analytics", "--from", "2026-01-01", "--to", "2026-01-07"])
    assert result.exit_code == 0
