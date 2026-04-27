"""Prompt formatting helpers for transcript synthesis.

Stateless functions that convert TranscriptEntry lists into LLM prompt strings.
Extracted from synthesis.py to keep both files under the 500-line cap.
"""

from __future__ import annotations

import logging

from wizard.transcript import TranscriptEntry

logger = logging.getLogger(__name__)

# Drop tool_result for read/nav tools — the tool_call input is sufficient signal.
# We only keep results for tools that mutate or provide high-level agency.
KEEP_RESULT_TOOLS = frozenset({"Edit", "Write", "Agent", "Bash"})

# Per-role character budgets applied after filtering.
ROLE_CHAR_LIMITS: dict[str, int] = {
    "user": 400,
    "assistant": 400,
    "tool_call": 150,
    "tool_result": 200,
}


def format_transcript(entries: list[TranscriptEntry]) -> str:
    """Encode transcript entries as plain text for the LLM prompt.

    Each entry becomes a single line: [role] content or [role:tool] content.
    Simpler than TOON CSV — avoids quoting overhead for local models.
    """
    if not entries:
        return ""
    lines = []
    for e in entries:
        role_tag = f"{e.role}:{e.tool_name}" if e.tool_name else e.role
        lines.append(f"[{role_tag}] {e.content}")
    return "\n".join(lines)


def filter_for_synthesis(entries: list[TranscriptEntry]) -> list[TranscriptEntry]:
    """Drop low-signal entries and truncate content per role."""
    kept: list[TranscriptEntry] = []
    call_by_id: dict[str, str | None] = {}
    for entry in entries:
        if entry.role == "tool_call":
            if entry.tool_use_id:
                call_by_id[entry.tool_use_id] = entry.tool_name
            kept.append(
                entry.model_copy(
                    update={"content": entry.content[: ROLE_CHAR_LIMITS["tool_call"]]}
                )
            )
        elif entry.role == "tool_result":
            call_name = (
                call_by_id.pop(entry.tool_use_id, None) if entry.tool_use_id else None
            )
            if call_name not in KEEP_RESULT_TOOLS:
                continue
            kept.append(
                entry.model_copy(
                    update={"content": entry.content[: ROLE_CHAR_LIMITS["tool_result"]]}
                )
            )
        else:
            kept.append(
                entry.model_copy(
                    update={
                        "content": entry.content[: ROLE_CHAR_LIMITS.get(entry.role, 2000)]
                    }
                )
            )
    return kept


def format_prompt(filtered: list[TranscriptEntry], task_table: str = "") -> str:
    """Format pre-filtered transcript entries into the LLM prompt string.

    Safety trim: if still over 15k chars (≈4k tokens), drop oldest entries
    until under the limit.
    """
    # Trim from the front (oldest entries) while over budget.
    # Use index-based slicing to avoid O(n²) list.pop(0) shifting.
    entries = list(filtered)
    total_chars = sum(len(e.content) for e in entries)
    if total_chars > 15_000:
        logger.warning("format_prompt: %d chars; trimming oldest entries", total_chars)
        start = 0
        while start < len(entries) and total_chars > 15_000:
            total_chars -= len(entries[start].content)
            start += 1
        entries = entries[start:]

    lines = [format_transcript(entries)]

    if task_table:
        lines.append(f"\nAvailable tasks (id<TAB>name):\n{task_table}\n\n")
    else:
        lines.append("\ntask_id must always be null — no task list available.")

    lines.append(
        "\nCRITICAL: Respond ONLY with a valid JSON array of objects. "
        "DO NOT include any text outside the JSON array. "
        "Format: "
        '[{"note_type": "investigation"|"decision"|"docs"|"learnings", '
        '"content": "string", "task_id": integer|null, "mental_model": "string"}]'
    )
    return "\n".join(lines)
