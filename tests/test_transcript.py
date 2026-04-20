import json
from pathlib import Path

import pytest

from wizard.transcript import TranscriptReader

SAMPLE_CLAUDE_TRANSCRIPT = [
    {
        "type": "user",
        "message": {
            "role": "user",
            "content": "Read the middleware file and explain it",
        },
        "timestamp": "2026-04-18T10:00:00.000Z",
        "sessionId": "test-session-1",
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me read that file."},
                {
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "Read",
                    "input": {"file_path": "src/wizard/middleware.py"},
                },
            ],
        },
        "timestamp": "2026-04-18T10:00:01.000Z",
    },
    {
        "type": "user",
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_001",
                    "content": "class ToolLoggingMiddleware(Middleware):\n    ...",
                    "is_error": False,
                },
            ],
        },
        "timestamp": "2026-04-18T10:00:02.000Z",
    },
    {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": "The middleware has two classes.",
                },
            ],
        },
        "timestamp": "2026-04-18T10:00:03.000Z",
    },
    {"type": "progress", "data": {"type": "hook_progress"}, "timestamp": "2026-04-18T10:00:04.000Z"},
    {"type": "file-history-snapshot", "messageId": "msg-1", "snapshot": {}},
]


@pytest.fixture()
def claude_transcript_file(tmp_path: Path) -> Path:
    p = tmp_path / "transcript.jsonl"
    with p.open("w") as f:
        for entry in SAMPLE_CLAUDE_TRANSCRIPT:
            f.write(json.dumps(entry) + "\n")
    return p


class TestTranscriptReader:
    def test_read_claude_code_returns_entries(self, claude_transcript_file: Path):
        reader = TranscriptReader()
        entries = reader.read(str(claude_transcript_file), agent="claude-code")
        assert len(entries) == 4
        assert entries[0].role == "user"
        assert entries[1].role == "tool_call"
        assert entries[1].tool_name == "Read"
        assert entries[2].role == "tool_result"
        assert entries[3].role == "assistant"

    def test_read_claude_code_extracts_tool_name(self, claude_transcript_file: Path):
        reader = TranscriptReader()
        entries = reader.read(str(claude_transcript_file), agent="claude-code")
        tool_calls = [e for e in entries if e.role == "tool_call"]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "Read"
        assert "middleware.py" in tool_calls[0].content

    def test_read_claude_code_skips_noise(self, claude_transcript_file: Path):
        reader = TranscriptReader()
        entries = reader.read(str(claude_transcript_file), agent="claude-code")
        types = {e.role for e in entries}
        assert "progress" not in types

    def test_read_unsupported_agent_raises(self, claude_transcript_file: Path):
        reader = TranscriptReader()
        with pytest.raises(ValueError, match="Unsupported agent"):
            reader.read(str(claude_transcript_file), agent="unknown-agent")

    def test_read_missing_file_raises(self):
        reader = TranscriptReader()
        with pytest.raises(FileNotFoundError):
            reader.read("/nonexistent/path.jsonl", agent="claude-code")

    def test_read_codex_parses_message_and_tool_calls(self, tmp_path: Path):
        lines = [
            {"type": "response_item", "timestamp": "2026-04-18T10:00:00Z", "payload": {
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Fix the bug"}],
            }},
            {"type": "response_item", "timestamp": "2026-04-18T10:00:01Z", "payload": {
                "type": "function_call", "name": "bash", "arguments": '{"cmd": "ls"}',
            }},
            {"type": "response_item", "timestamp": "2026-04-18T10:00:02Z", "payload": {
                "type": "function_call_output", "output": "src/  tests/",
            }},
        ]
        p = tmp_path / "codex.jsonl"
        p.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        reader = TranscriptReader()
        entries = reader.read(str(p), agent="codex")
        assert len(entries) == 3
        assert entries[0].role == "user"
        assert entries[0].content == "Fix the bug"
        assert entries[1].role == "tool_call"
        assert entries[1].tool_name == "bash"
        assert entries[2].role == "tool_result"
        assert "src/" in entries[2].content

    def test_read_codex_skips_non_response_item(self, tmp_path: Path):
        lines = [
            {"type": "session_start", "payload": {"type": "message", "role": "user",
                "content": [{"type": "text", "text": "ignored"}]}},
            {"type": "response_item", "timestamp": "2026-04-18T10:00:00Z", "payload": {
                "type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "Hello"}],
            }},
        ]
        p = tmp_path / "codex2.jsonl"
        p.write_text("\n".join(json.dumps(line) for line in lines) + "\n")
        reader = TranscriptReader()
        entries = reader.read(str(p), agent="codex")
        assert len(entries) == 1
        assert entries[0].content == "Hello"
