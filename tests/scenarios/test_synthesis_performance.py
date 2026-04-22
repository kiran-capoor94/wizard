"""Scenario: synthesis prompt uses plain-text transcript format, not TOON CSV."""

from wizard.synthesis import _format_transcript
from wizard.transcript import TranscriptEntry


def _entry(role: str, content: str, tool_name: str | None = None) -> TranscriptEntry:
    return TranscriptEntry(role=role, content=content, tool_name=tool_name, tool_use_id=None)


def test_format_transcript_plain_text_lines():
    """Each entry renders as [role] content or [role:tool] content on its own line."""
    entries = [
        _entry("user", "fix the bug"),
        _entry("assistant", "sure"),
        _entry("tool_call", "src/foo.py", tool_name="Edit"),
        _entry("tool_result", "ok", tool_name="Edit"),
    ]
    result = _format_transcript(entries)
    lines = result.splitlines()
    assert lines[0] == "[user] fix the bug"
    assert lines[1] == "[assistant] sure"
    assert lines[2] == "[tool_call:Edit] src/foo.py"
    assert lines[3] == "[tool_result:Edit] ok"


def test_format_transcript_empty():
    """Empty entry list returns empty string."""
    assert _format_transcript([]) == ""


def test_format_transcript_no_tool_name():
    """Entries without tool_name omit the colon suffix."""
    entries = [_entry("user", "hello")]
    result = _format_transcript(entries)
    assert result == "[user] hello"
