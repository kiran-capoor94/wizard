"""Scenario: analytics output includes a Health section when thresholds exceeded."""

import datetime

from wizard.cli.analytics import format_table

START = datetime.date(2026, 4, 13)
END = datetime.date(2026, 4, 20)


def _data(
    mental_model_coverage: float = 0.4,
    manual_notes: int = 10,
    abandoned_rate: float = 0.25,
    avg_notes_per_task: float = 2.0,
    worked: int = 5,
) -> dict:
    return {
        "sessions": {
            "session_count": 4,
            "avg_duration_minutes": 30.0,
            "total_tool_calls": 100,
            "abandoned_count": int(4 * abandoned_rate),
            "abandoned_rate": abandoned_rate,
        },
        "notes": {
            "total": manual_notes + 10,
            "manual_notes": manual_notes,
            "session_summaries": 10,
            "mental_model_coverage": mental_model_coverage,
            "mental_models_captured": int(manual_notes * mental_model_coverage),
            "by_type": {"investigation": manual_notes},
        },
        "tasks": {
            "worked": worked,
            "avg_notes_per_task": avg_notes_per_task,
            "stale_count": 0,
        },
        "compounding": 0.5,
    }


def test_health_fires_when_mental_model_coverage_low():
    output = format_table(_data(mental_model_coverage=0.1, manual_notes=5), START, END)
    assert "Health" in output
    assert "Mental model coverage is low" in output


def test_health_fires_when_high_abandonment():
    output = format_table(_data(abandoned_rate=0.75), START, END)
    assert "Health" in output
    assert "Most sessions are abandoned" in output


def test_health_fires_when_low_note_density():
    output = format_table(_data(avg_notes_per_task=1.0, worked=3), START, END)
    assert "Health" in output
    assert "Low note density" in output


def test_health_omitted_when_all_healthy():
    output = format_table(
        _data(mental_model_coverage=0.5, abandoned_rate=0.25, avg_notes_per_task=2.5),
        START, END,
    )
    assert "Health" not in output


def test_mental_model_nudge_suppressed_with_no_manual_notes():
    # Coverage is 0.0 but there are no manual notes — nothing actionable
    output = format_table(_data(mental_model_coverage=0.0, manual_notes=0), START, END)
    assert "Mental model coverage is low" not in output
