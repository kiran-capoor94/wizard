import datetime
import logging

logger = logging.getLogger(__name__)


def query_sessions(db, start: datetime.date, end: datetime.date) -> dict:
    from sqlmodel import select
    from wizard.models import ToolCall

    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time.max)

    calls = db.exec(
        select(ToolCall).where(
            ToolCall.called_at >= start_dt,
            ToolCall.called_at <= end_dt,
        )
    ).all()

    total_tool_calls = len(calls)

    starts = {c.session_id: c.called_at for c in calls if c.tool_name == "session_start" and c.session_id}
    ends = {c.session_id: c.called_at for c in calls if c.tool_name == "session_end" and c.session_id}

    session_count = len(starts)
    durations = []
    for sid, start_time in starts.items():
        if sid in ends:
            delta = (ends[sid] - start_time).total_seconds() / 60
            durations.append(delta)

    avg_duration = sum(durations) / len(durations) if durations else 0.0

    return {
        "session_count": session_count,
        "avg_duration_minutes": round(avg_duration, 1),
        "total_tool_calls": total_tool_calls,
    }


def query_notes(db, start: datetime.date, end: datetime.date) -> dict:
    from sqlmodel import select
    from wizard.models import Note

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
        type_name = note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type)
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
    from sqlmodel import select
    from wizard.models import Note, TaskState

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
    from sqlmodel import select
    from wizard.models import Note, ToolCall

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

    compounding_count = 0
    for tc in task_starts:
        if tc.session_id is None:
            continue
        prior_note = db.exec(
            select(Note).where(Note.created_at < tc.called_at)
        ).first()
        if prior_note:
            compounding_count += 1

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
