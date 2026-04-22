"""Scenario: synthesis prompt uses plain-text transcript format, not TOON CSV."""

import json
from unittest.mock import MagicMock, patch

import httpx
import pytest

from wizard.llm_adapters import OllamaAdapter
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


def test_ollama_adapter_posts_to_api_chat_with_json_format():
    """OllamaAdapter calls /api/chat with format='json' and stream=False."""
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "message": {
            "content": json.dumps([
                {"note_type": "investigation", "content": "found a bug", "task_id": None, "mental_model": None}
            ])
        }
    }
    mock_response.raise_for_status = MagicMock()

    with patch("wizard.llm_adapters.httpx.post", return_value=mock_response) as mock_post:
        adapter = OllamaAdapter(
            base_url="http://localhost:11434",
            model="ollama/gemma4:latest-64k",
            options={"num_ctx": 16384},
        )
        notes = adapter.complete([{"role": "user", "content": "summarise this"}])

    # Correct endpoint
    call_url = mock_post.call_args.args[0]
    assert call_url == "http://localhost:11434/api/chat"

    # Required payload fields
    payload = mock_post.call_args.kwargs["json"]
    assert payload["format"] == "json"
    assert payload["stream"] is False
    assert payload["model"] == "ollama/gemma4:latest-64k"
    assert payload["options"] == {"num_ctx": 16384}
    assert payload["messages"] == [{"role": "user", "content": "summarise this"}]

    # Parsed output
    assert len(notes) == 1
    assert notes[0].note_type == "investigation"
    assert notes[0].content == "found a bug"
    assert notes[0].task_id is None


def test_ollama_adapter_raises_on_http_error():
    """OllamaAdapter propagates HTTP errors so _call_adapter can catch them."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "500", request=MagicMock(), response=MagicMock()
    )

    with patch("wizard.llm_adapters.httpx.post", return_value=mock_response):
        adapter = OllamaAdapter("http://localhost:11434", "ollama/gemma4:latest-64k", {})
        with pytest.raises(httpx.HTTPStatusError):
            adapter.complete([{"role": "user", "content": "test"}])
