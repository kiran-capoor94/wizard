import datetime
import logging

from sqlmodel import select

from wizard.models import Note, NoteType, TaskState, ToolCall, WizardSession

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

    sessions = db.exec(
        select(WizardSession).where(
            WizardSession.created_at >= start_dt,
            WizardSession.created_at <= end_dt,
        )
    ).all()
    session_count = len(sessions)

    durations = []
    for s in sessions:
        if s.closed_by == "user":
            delta = (s.updated_at - s.created_at).total_seconds() / 60
            durations.append(delta)
        elif s.closed_by == "auto" and s.last_active_at is not None:
            delta = (s.last_active_at - s.created_at).total_seconds() / 60
            durations.append(delta)
        # open sessions: excluded from average

    avg_duration = sum(durations) / len(durations) if durations else 0.0
    abandoned = [s for s in sessions if s.closed_by == "auto"]
    abandoned_count = len(abandoned)

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
    session_summaries = 0
    for note in notes:
        type_name = (
            note.note_type.value if hasattr(note.note_type, "value") else str(note.note_type)
        )
        by_type[type_name] = by_type.get(type_name, 0) + 1
        if note.note_type == NoteType.SESSION_SUMMARY:
            session_summaries += 1
        elif note.mental_model:
            mental_models += 1

    manual_notes = total - session_summaries
    coverage = mental_models / manual_notes if manual_notes > 0 else 0.0

    return {
        "total": total,
        "by_type": by_type,
        "mental_models_captured": mental_models,
        "mental_model_coverage": round(coverage, 2),
        "session_summaries": session_summaries,
        "manual_notes": manual_notes,
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

    # Build earliest session_start time per session (same min logic as query_sessions).
    session_start_times: dict[int, datetime.datetime] = {}
    for tc in session_starts:
        if tc.session_id and (
            tc.session_id not in session_start_times
            or tc.called_at < session_start_times[tc.session_id]
        ):
            session_start_times[tc.session_id] = tc.called_at

    # For each session that had a task_start call, check whether any note existed
    # before that session began. ToolCall has no task_id, so we use the session
    # as the prior-context boundary.
    task_start_session_ids = {tc.session_id for tc in task_starts if tc.session_id}

    sessions_with_prior_notes: set[int] = set()
    for sid in task_start_session_ids:
        if sid not in session_start_times:
            continue
        has_prior = (
            db.exec(
                select(Note).where(Note.created_at < session_start_times[sid]).limit(1)
            ).first()
            is not None
        )
        if has_prior:
            sessions_with_prior_notes.add(sid)

    return round(len(sessions_with_prior_notes) / len(task_start_session_ids), 2)


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
    manual_notes_count = notes.get("manual_notes", 0)
    session_summaries_count = notes.get("session_summaries", 0)
    lines += [
        "",
        "Notes",
        f"  Manual notes:         {manual_notes_count}",
    ]
    by_type = notes.get("by_type", {})
    manual_types = {k: v for k, v in by_type.items() if k != "session_summary"}
    for note_type, count in sorted(manual_types.items()):
        lines.append(f"    {note_type}: {count}")
    lines += [
        f"  Mental model coverage:{notes.get('mental_model_coverage', 0.0):.0%}",
        f"  Session summaries:    {session_summaries_count}",
    ]

    lines += [
        "",
        "Tasks",
        f"  Tasks worked:         {tasks.get('worked', 0)}",
        f"  Avg notes/task:       {tasks.get('avg_notes_per_task', 0.0)}",
        f"  Stale tasks (>3d):    {tasks.get('stale_count', 0)}",
        "",
        "Compounding",
        f"  Sessions with context:{compounding:.0%}",
        "",
    ]
    return "\n".join(lines)
