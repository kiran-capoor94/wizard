import datetime
import logging

from rich.console import Console
from rich.table import Table
from rich.text import Text

from wizard.repositories.analytics import AnalyticsRepository

logger = logging.getLogger(__name__)

# Repository instance for thin controller orchestration
_repo = AnalyticsRepository()


def query_sessions(db, start: datetime.date, end: datetime.date) -> dict:
    return _repo.get_session_stats(db, start, end)


def query_notes(db, start: datetime.date, end: datetime.date) -> dict:
    return _repo.get_note_stats(db, start, end)


def query_tasks(db, start: datetime.date, end: datetime.date) -> dict:
    return _repo.get_task_stats(db, start, end)


def query_compounding(db, start: datetime.date, end: datetime.date) -> float:
    return _repo.get_compounding_score(db, start, end)


def _format_sessions_section(sessions: dict) -> list[str]:
    lines = [
        "Sessions",
        f"  Sessions:             {sessions.get('session_count', 0)}",
        f"  Avg duration (min):   {sessions.get('avg_duration_minutes', 0.0)}",
        f"  Total tool calls:     {sessions.get('total_tool_calls', 0)}",
    ]
    abandoned_count = sessions.get("abandoned_count", 0)
    if abandoned_count > 0:
        rate = sessions.get("abandoned_rate", 0.0)
        lines.append(f"  Abandoned:            {abandoned_count} ({rate:.0%})")
    if sessions.get("synthesis_failures", 0) > 0:
        lines.append(f"  Synthesis failures:   {sessions['synthesis_failures']}")
    if sessions.get("pending_synthesis", 0) > 0:
        lines.append(f"  Pending synthesis:    {sessions['pending_synthesis']}")
    return lines


def _format_notes_section(notes: dict) -> list[str]:
    lines = [
        "Notes",
        f"  Manual notes:         {notes.get('manual_notes', 0)}",
    ]
    manual_types = {k: v for k, v in notes.get("by_type", {}).items() if k != "session_summary"}
    for note_type, count in sorted(manual_types.items()):
        lines.append(f"    {note_type}: {count}")
    lines += [
        f"  Mental model coverage:{notes.get('mental_model_coverage', 0.0):.0%}",
        f"  Session summaries:    {notes.get('session_summaries', 0)}",
    ]
    if notes.get("unclassified", 0) > 0:
        lines.append(f"  Unclassified (failed):{notes['unclassified']}")
    if notes.get("superseded", 0) > 0:
        lines.append(f"  Superseded:           {notes['superseded']}")
    return lines


def _format_health_messages(sessions: dict, notes: dict, tasks: dict) -> list[str]:
    messages = []
    if notes.get("manual_notes", 0) > 0 and notes.get("mental_model_coverage", 1.0) < 0.25:
        messages.append("  Mental model coverage is low — add mental_model to save_note calls")
    if sessions.get("abandoned_rate", 0.0) > 0.5:
        messages.append("  Most sessions are abandoned — call session_end before closing")
    if sessions.get("synthesis_failures", 0) > 0:
        ids = sessions.get("synthesis_failure_ids", [])
        for sid in ids:
            messages.append(
                f"  Session {sid} had synthesis failure"
                f" — retry with: wizard capture --close --session-id {sid}"
            )
    # Default 2.0 is above the 1.5 threshold so missing data suppresses nudge.
    if tasks.get("worked", 0) > 0 and tasks.get("avg_notes_per_task", 2.0) < 1.5:
        messages.append("  Low note density — investigation and decision notes build compounding")
    return messages


def format_table(data: dict, start: datetime.date, end: datetime.date) -> str:
    sessions = data.get("sessions", {})
    notes = data.get("notes", {})
    tasks = data.get("tasks", {})
    compounding = data.get("compounding", 0.0)

    lines = [f"Wizard Analytics  {start} \u2192 {end}", "=" * 50, ""]
    lines += _format_sessions_section(sessions)
    lines += [""]
    lines += _format_notes_section(notes)
    lines += [
        "",
        "Tasks",
        f"  Tasks worked:         {tasks.get('worked', 0)}",
        f"  Avg notes/task:       {tasks.get('avg_notes_per_task', 0.0)}",
        f"  Stale tasks (>3d):    {tasks.get('stale_count', 0)}",
        "",
        "Compounding",
        f"  Sessions with context:{compounding:.0%}",
    ]
    health_messages = _format_health_messages(sessions, notes, tasks)
    if health_messages:
        lines += ["", "Health"]
        lines += health_messages
    lines.append("")
    return "\n".join(lines)


def _build_sessions_col(sessions: dict, session_summaries: int) -> Text:
    session_count = sessions.get("session_count", 0)
    abandoned = sessions.get("abandoned_count", 0)
    synthesis_failures = sessions.get("synthesis_failures", 0)
    col = Text()
    col.append(f"{session_count}", style="bold")
    col.append(" sessions\n")
    col.append(f"{session_summaries}", style="bold")
    col.append(" summarised")
    if abandoned:
        col.append(f"\n{abandoned}", style="bold yellow")
        col.append(" abandoned", style="yellow")
    if synthesis_failures:
        col.append(f"\n{synthesis_failures}", style="bold red")
        col.append(" synthesis failed", style="red")
    return col


def _build_notes_col(notes: dict) -> Text:
    by_type = {k: v for k, v in notes.get("by_type", {}).items() if k != "session_summary"}
    unclassified = notes.get("unclassified", 0)
    col = Text()
    for note_type, count in sorted(by_type.items(), key=lambda x: -x[1]):
        col.append(f"{count:3d}", style="bold")
        col.append(f"  {note_type}\n")
    if not by_type:
        col.append("(none)", style="dim")
    if unclassified:
        col.append(f"\n{unclassified}", style="bold red")
        col.append(" unclassified", style="red")
    return col


def _build_tasks_col(tasks: dict, compounding: float) -> Text:
    worked = tasks.get("worked", 0)
    stale = tasks.get("stale_count", 0)
    col = Text()
    col.append(f"{worked}", style="bold")
    col.append(" worked\n")
    if stale:
        col.append(f"{stale}", style="bold yellow")
        col.append(" stale (>3 days)\n", style="yellow")
    if compounding > 0:
        col.append(f"\n{compounding:.0%}", style="bold")
        col.append(" compounding")
    return col


def print_analytics(data: dict, start: datetime.date, end: datetime.date) -> None:
    """Render analytics to the terminal using a compact 3-column Rich layout."""
    sessions = data.get("sessions", {})
    notes = data.get("notes", {})
    tasks = data.get("tasks", {})
    compounding = data.get("compounding", 0.0)

    session_summaries = notes.get("session_summaries", 0)
    sess_col = _build_sessions_col(sessions, session_summaries)
    notes_col = _build_notes_col(notes)
    tasks_col = _build_tasks_col(tasks, compounding)

    grid = Table(box=None, show_header=True, header_style="bold", padding=(0, 3))
    grid.add_column("Sessions", min_width=18)
    grid.add_column("Notes", min_width=22)
    grid.add_column("Tasks", min_width=18)
    grid.add_row(sess_col, notes_col, tasks_col)

    console = Console()
    date_label = str(start) if start == end else f"{start} → {end}"
    console.rule(f"[bold]Wizard[/bold]  {date_label}")
    console.print()
    console.print(grid)

    health = _format_health_messages(sessions, notes, tasks)
    if health:
        console.print()
        for msg in health:
            console.print(f"  [yellow]⚠[/yellow]  {msg.strip()}")
