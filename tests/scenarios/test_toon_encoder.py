# tests/scenarios/test_toon_encoder.py
"""Scenario: TOON encoding of TaskContext arrays."""

from wizard.models import TaskCategory, TaskPriority, TaskStatus
from wizard.schemas import TaskContext
from wizard.toon import encode_task_contexts


def _make_task(**kwargs) -> TaskContext:
    defaults = dict(
        id=1,
        name="Test task",
        status=TaskStatus.TODO,
        priority=TaskPriority.MEDIUM,
        category=TaskCategory.ISSUE,
        due_date=None,
        source_id=None,
        source_url=None,
        last_note_type=None,
        last_note_preview=None,
        last_worked_at=None,
        stale_days=0,
        note_count=0,
        decision_count=0,
    )
    defaults.update(kwargs)
    return TaskContext(**defaults)


def test_empty_list_returns_empty_marker():
    assert encode_task_contexts("open_tasks", []) == "open_tasks[0]"


def test_header_declares_count_and_fields():
    task = _make_task(id=42, name="Fix auth bug", status=TaskStatus.TODO,
                      priority=TaskPriority.HIGH, category=TaskCategory.BUG,
                      stale_days=2, note_count=3, decision_count=1)
    result = encode_task_contexts("open_tasks", [task])
    lines = result.split("\n")
    assert lines[0] == (
        "open_tasks[1]{id,name,status,priority,category,due_date,"
        "stale_days,note_count,decision_count,last_note_type,last_note_preview,source_url}:"
    )


def test_row_values_in_correct_field_order():
    task = _make_task(id=42, name="Fix auth bug", status=TaskStatus.TODO,
                      priority=TaskPriority.HIGH, category=TaskCategory.BUG,
                      stale_days=2, note_count=3, decision_count=1)
    result = encode_task_contexts("open_tasks", [task])
    lines = result.split("\n")
    assert lines[1] == "  42,Fix auth bug,todo,high,bug,,2,3,1,,,"


def test_name_with_comma_is_csv_quoted():
    task = _make_task(id=1, name="Fix, the auth bug")
    result = encode_task_contexts("t", [task])
    assert '"Fix, the auth bug"' in result


def test_preview_truncated_to_80_chars():
    long_preview = "x" * 200
    task = _make_task(id=1, last_note_preview=long_preview)
    result = encode_task_contexts("t", [task])
    assert "x" * 80 in result
    assert "x" * 81 not in result


def test_preview_newlines_stripped():
    task = _make_task(id=1, last_note_preview="line1\nline2")
    result = encode_task_contexts("t", [task])
    assert "\n  " in result   # only the TOON row separator newline
    assert "line1 line2" in result


def test_two_tasks_produce_two_rows():
    tasks = [_make_task(id=1, name="A"), _make_task(id=2, name="B")]
    result = encode_task_contexts("open_tasks", tasks)
    lines = result.split("\n")
    assert lines[0].startswith("open_tasks[2]")
    assert len(lines) == 3   # header + 2 rows


def test_label_used_in_header():
    result = encode_task_contexts("blocked_tasks", [_make_task()])
    assert result.startswith("blocked_tasks[1]")
