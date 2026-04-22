"""TOON (Token-Oriented Object Notation) encoder for wizard response payloads.

Encodes uniform arrays of structured objects into the compact TOON tabular
format, reducing token consumption vs JSON for large structured payloads.

Only encoding is implemented — wizard never needs to decode TOON server-side.
"""

import csv
import io

from .schemas import TaskContext
from .transcript import TranscriptEntry

_TASK_FIELDS = (
    "id",
    "name",
    "status",
    "priority",
    "category",
    "due_date",
    "stale_days",
    "note_count",
    "decision_count",
    "last_note_type",
    "last_note_preview",
    "source_url",
)
_PREVIEW_MAX = 80


def encode_task_contexts(label: str, tasks: list[TaskContext]) -> str:
    """Encode a list of TaskContext objects as a TOON string.

    Returns ``label[0]`` for empty lists.
    Format: header line declaring count + field schema, then one indented
    CSV row per task.
    """
    if not tasks:
        return f"{label}[0]"

    header = f"{label}[{len(tasks)}]{{{','.join(_TASK_FIELDS)}}}:"
    lines = [header]

    buf = io.StringIO()
    writer = csv.writer(buf)
    for t in tasks:
        preview = (t.last_note_preview or "")[:_PREVIEW_MAX].replace("\n", " ")
        row = [
            t.id,
            t.name,
            t.status.value,
            t.priority.value,
            t.category.value,
            t.due_date.strftime("%Y-%m-%d") if t.due_date else "",
            t.stale_days,
            t.note_count,
            t.decision_count,
            t.last_note_type.value if t.last_note_type else "",
            preview,
            t.source_url or "",
        ]
        buf.seek(0)
        buf.truncate(0)
        writer.writerow(row)
        lines.append("  " + buf.getvalue().rstrip("\r\n"))

    return "\n".join(lines)


def encode_transcript_entries(entries: list[TranscriptEntry]) -> str:
    """Encode transcript entries as a TOON tabular string.

    Format: transcript[N]{role,tool,content}:
              one CSV row per entry (CSV handles quoting of commas/newlines).
    Returns ``transcript[0]`` for empty lists.
    """
    if not entries:
        return "transcript[0]"

    header = f"transcript[{len(entries)}]{{role,tool,content}}:"
    lines = [header]
    buf = io.StringIO()
    writer = csv.writer(buf)
    for e in entries:
        buf.seek(0)
        buf.truncate(0)
        writer.writerow([e.role, e.tool_name or "", e.content])
        lines.append("  " + buf.getvalue().rstrip("\r\n"))
    return "\n".join(lines)
