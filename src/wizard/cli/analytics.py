import datetime
import logging

from sqlmodel import select

from wizard.models import Note, TaskState, ToolCall, WizardSession

logger = logging.getLogger(__name__)


def query_sessions(db, start: datetime.date, end: datetime.date) -> dict:
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    calls = db.exec(
        select(ToolCall).where(
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    total_tool_calls = len(calls)

    starts = {
        c.session_id: c.called_at
        for c in calls if c.tool_name == "session_start" and c.session_id
    }
    ends = {
        c.session_id: c.called_at
        for c in calls if c.tool_name == "session_end" and c.session_id
    }

    session_count = len(starts)

    # Durations: user-closed sessions use session_end ToolCall timestamp
    durations = []
    for sid, start_time in starts.items():
        if sid in ends:
            delta = (ends[sid] - start_time).total_seconds() / 60
            durations.append(delta)

    # Query WizardSession for abandoned metrics and their durations
    sessions_in_range = db.exec(
        select(WizardSession).where(
            WizardSession.created_at >= start_dt,
            WizardSession.created_at <= end_dt,
        )
    ).all()

    abandoned = [s for s in sessions_in_range if s.closed_by == "auto"]
    abandoned_count = len(abandoned)

    for s in abandoned:
        if s.last_active_at is not None and s.id in starts:
            delta = (s.last_active_at - starts[s.id]).total_seconds() / 60
            durations.append(delta)

    avg_duration = sum(durations) / len(durations) if durations else 0.0

    return {
        "session_count": session_count,
        "avg_duration_minutes": round(avg_duration, 1),
        "total_tool_calls": total_tool_calls,
        "abandoned_count": abandoned_count,
        "abandoned_rate": round(abandoned_count / session_count, 2) if session_count else 0.0,
    }


def query_notes(db, start: datetime.date, end: datetime.date) -> dict:
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    notes = db.exec(
        select(Note).where(
            Note.created_at >= start_dt,
            Note.created_at <= end_dt,
        )
    ).all()

    total = len(notes)
    by_type: dict[str, int] = {}
    mental_models = 0
    for note in notes:
        type_name = (
            note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type)
        )
        by_type[type_name] = by_type.get(type_name, 0) + 1
        if note.mental_model:
            mental_models += 1

    coverage = mental_models / total if total > 0 else 0.0

    return {
        "total": total,
        "by_type": by_type,
        "mental_models_captured": mental_models,
        "mental_model_coverage": round(coverage, 2),
    }


def query_tasks(db, start: datetime.date, end: datetime.date) -> dict:
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    notes = db.exec(
        select(Note).where(
            Note.created_at >= start_dt,
            Note.created_at <= end_dt,
        )
    ).all()

    task_note_counts: dict[int, int] = {}
    for note in notes:
        if note.task_id is not None:
            task_note_counts[note.task_id] = task_note_counts.get(note.task_id, 0) + 1

    worked = len(task_note_counts)
    total_notes = sum(task_note_counts.values())
    avg_notes = total_notes / worked if worked > 0 else 0.0

    stale = db.exec(
        select(TaskState).where(TaskState.stale_days > 3)
    ).all()
    stale_count = len(stale)

    return {
        "worked": worked,
        "avg_notes_per_task": round(avg_notes, 1),
        "stale_count": stale_count,
    }


def query_compounding(db, start: datetime.date, end: datetime.date) -> float:
    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    task_starts = db.exec(
        select(ToolCall).where(
            ToolCall.tool_name == "task_start",
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    if not task_starts:
        return 0.0

    # Find the earliest session_start in the window to use as the prior-context boundary.
    # Any note before this timestamp came from a previous session.
    session_starts = db.exec(
        select(ToolCall).where(
            ToolCall.tool_name == "session_start",
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    if not session_starts:
        return 0.0

    earliest_session_start = min(tc.called_at for tc in session_starts)

    prior_context_exists = (
        db.exec(select(Note).where(Note.created_at < earliest_session_start)).first()
        is not None
    )

    if not prior_context_exists:
        return 0.0

    compounding_count = sum(1 for tc in task_starts if tc.session_id is not None)
    return round(compounding_count / len(task_starts), 2)


def format_table(data: dict, start: datetime.date, end: datetime.date) -> str:
    sessions = data.get("sessions", {})
    notes = data.get("notes", {})
    tasks = data.get("tasks", {})
    compounding = data.get("compounding", 0.0)

    lines = [
        f"Wizard Analytics  {start} \u2192 {end}",
        "=" * 50,
        "",
        "Sessions",
        f"  Sessions:             {sessions.get('session_count', 0)}",
        f"  Avg duration (min):   {sessions.get('avg_duration_minutes', 0.0)}",
        f"  Total tool calls:     {sessions.get('total_tool_calls', 0)}",
    ]
    abandoned_count = sessions.get('abandoned_count', 0)
    if abandoned_count > 0:
        rate = sessions.get('abandoned_rate', 0.0)
        lines.append(f"  Abandoned:            {abandoned_count} ({rate:.0%})")
    lines += [
        "",
        "Notes",
        f"  Total notes:          {notes.get('total', 0)}",
        f"  Mental model coverage:{notes.get('mental_model_coverage', 0.0):.0%}",
    ]
    by_type = notes.get("by_type", {})
    for note_type, count in sorted(by_type.items()):
        lines.append(f"    {note_type}: {count}")

    lines += [
        "",
        "Tasks",
        f"  Tasks worked:         {tasks.get('worked', 0)}",
        f"  Avg notes/task:       {tasks.get('avg_notes_per_task', 0.0)}",
        f"  Stale tasks (>3d):    {tasks.get('stale_count', 0)}",
        "",
        "Compounding",
        f"  Ratio:                {compounding:.0%}",
        "",
    ]
    return "\n".join(lines)
