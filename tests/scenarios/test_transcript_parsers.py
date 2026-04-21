"""Scenario: new multi-agent transcript parsers produce correct TranscriptEntry lists."""

import json
import unittest.mock as mock

import pytest

import wizard.transcript as t_module
from wizard.transcript import TranscriptReader


@pytest.fixture
def reader() -> TranscriptReader:
    return TranscriptReader()


def _fake_home(base):
    """Return a classmethod stub that makes Path.home() return `base`."""
    def _home():
        return base
    return _home


class TestGeminiParser:
    def test_plain_text_messages(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({"type": "user", "content": "Hello gemini", "timestamp": "t1"}) + "\n"
            + json.dumps({"type": "gemini", "content": "Hi there", "timestamp": "t2"}) + "\n"
        )
        entries = reader.read(str(transcript), "gemini")
        assert len(entries) == 2
        assert entries[0].role == "user"
        assert entries[0].content == "Hello gemini"
        assert entries[1].role == "assistant"
        assert entries[1].content == "Hi there"

    def test_structured_parts_list(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "gemini",
                "content": [{"text": "Part one"}, {"text": "part two"}],
                "timestamp": "t1",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "gemini")
        assert len(entries) == 1
        assert "Part one" in entries[0].content
        assert "part two" in entries[0].content

    def test_tool_calls_in_gemini_message(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "gemini",
                "content": "",
                "toolCalls": [
                    {"name": "read_file", "args": {"path": "foo.py"}, "id": "tc-1"},
                ],
                "timestamp": "t1",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "gemini")
        assert len(entries) == 1
        assert entries[0].role == "tool_call"
        assert entries[0].tool_name == "read_file"
        assert json.loads(entries[0].content) == {"path": "foo.py"}
        assert entries[0].tool_use_id == "tc-1"

    def test_tool_calls_alongside_text(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "gemini",
                "content": "Let me read that.",
                "toolCalls": [{"name": "read_file", "args": {"path": "x.py"}, "id": "tc-2"}],
                "timestamp": "t1",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "gemini")
        assert len(entries) == 2
        roles = [e.role for e in entries]
        assert "assistant" in roles
        assert "tool_call" in roles

    def test_skips_noise_types(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text(
            json.dumps({"type": "info", "content": "ignored"}) + "\n"
            + json.dumps({"type": "error", "content": "ignored"}) + "\n"
            + json.dumps({"type": "warning", "content": "ignored"}) + "\n"
            + json.dumps({"type": "user", "content": "real"}) + "\n"
        )
        entries = reader.read(str(transcript), "gemini")
        assert len(entries) == 1
        assert entries[0].content == "real"

    def test_empty_transcript(self, reader, tmp_path):
        transcript = tmp_path / "session.jsonl"
        transcript.write_text("")
        entries = reader.read(str(transcript), "gemini")
        assert entries == []


class TestOpenCodeParser:
    def _storage_dir(self, base, session_id):
        return base / ".local" / "share" / "opencode" / "storage" / "message" / session_id

    def test_reads_messages_in_creation_time_order(self, reader, tmp_path):
        session_id = "test-session-123"
        storage_dir = self._storage_dir(tmp_path, session_id)
        storage_dir.mkdir(parents=True)
        # Files named with UUIDs (not sequential); order determined by metadata.time.created
        (storage_dir / "uuid-c.json").write_text(json.dumps({
            "role": "assistant", "parts": [{"type": "text", "text": "last"}],
            "metadata": {"time": {"created": 3}},
        }))
        (storage_dir / "uuid-a.json").write_text(json.dumps({
            "role": "user", "parts": [{"type": "text", "text": "first"}],
            "metadata": {"time": {"created": 1}},
        }))
        (storage_dir / "uuid-b.json").write_text(json.dumps({
            "role": "assistant", "parts": [{"type": "text", "text": "mid"}],
            "metadata": {"time": {"created": 2}},
        }))

        with mock.patch.object(t_module.Path, "home", staticmethod(_fake_home(tmp_path))):
            synthetic_path = tmp_path / f"{session_id}.txt"
            entries = reader.read(str(synthetic_path), "opencode")

        assert [e.content for e in entries] == ["first", "mid", "last"]

    def test_parses_tool_invocation_parts(self, reader, tmp_path):
        session_id = "tool-session"
        storage_dir = self._storage_dir(tmp_path, session_id)
        storage_dir.mkdir(parents=True)
        (storage_dir / "msg.json").write_text(json.dumps({
            "role": "assistant",
            "parts": [
                {
                    "type": "tool-invocation",
                    "toolInvocation": {
                        "state": "call",
                        "toolCallId": "call-1",
                        "toolName": "Bash",
                        "args": {"command": "ls"},
                    },
                },
                {
                    "type": "tool-invocation",
                    "toolInvocation": {
                        "state": "result",
                        "toolCallId": "call-1",
                        "toolName": "Bash",
                        "args": {"command": "ls"},
                        "result": "file.py",
                    },
                },
            ],
            "metadata": {"time": {"created": 1}},
        }))

        with mock.patch.object(t_module.Path, "home", staticmethod(_fake_home(tmp_path))):
            synthetic_path = tmp_path / f"{session_id}.txt"
            entries = reader.read(str(synthetic_path), "opencode")

        assert len(entries) == 2
        assert entries[0].role == "tool_call"
        assert entries[0].tool_name == "Bash"
        assert json.loads(entries[0].content) == {"command": "ls"}
        assert entries[0].tool_use_id == "call-1"
        assert entries[1].role == "tool_result"
        assert entries[1].content == "file.py"
        assert entries[1].tool_use_id == "call-1"

    def test_missing_storage_dir_returns_empty(self, reader, tmp_path):
        with mock.patch.object(t_module.Path, "home", staticmethod(_fake_home(tmp_path))):
            synthetic_path = tmp_path / "nonexistent-session.txt"
            entries = reader.read(str(synthetic_path), "opencode")

        assert entries == []

    def test_rejects_malformed_json(self, reader, tmp_path):
        session_id = "bad-json-session"
        storage_dir = self._storage_dir(tmp_path, session_id)
        storage_dir.mkdir(parents=True)
        (storage_dir / "bad.json").write_text("not json{{{")
        (storage_dir / "good.json").write_text(json.dumps({
            "role": "assistant",
            "parts": [{"type": "text", "text": "valid"}],
            "metadata": {"time": {"created": 1}},
        }))

        with mock.patch.object(t_module.Path, "home", staticmethod(_fake_home(tmp_path))):
            synthetic_path = tmp_path / f"{session_id}.txt"
            entries = reader.read(str(synthetic_path), "opencode")

        assert len(entries) == 1
        assert entries[0].content == "valid"


class TestCopilotParser:
    def test_tool_call_with_dict_args(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "assistant.message",
                "data": {
                    "content": "",
                    "toolRequests": [
                        {
                            "toolCallId": "call-1",
                            "name": "read_file",
                            "arguments": {"path": "src/main.py"},
                        }
                    ],
                },
                "timestamp": "t1",
            }) + "\n"
            + json.dumps({
                "type": "tool.execution_complete",
                "data": {
                    "toolCallId": "call-1",
                    "result": {"content": "x = 1"},
                },
                "timestamp": "t2",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "copilot")
        tool_calls = [e for e in entries if e.role == "tool_call"]
        tool_results = [e for e in entries if e.role == "tool_result"]
        assert len(tool_calls) == 1
        assert tool_calls[0].tool_name == "read_file"
        assert json.loads(tool_calls[0].content) == {"path": "src/main.py"}
        assert tool_calls[0].tool_use_id == "call-1"
        assert len(tool_results) == 1
        assert tool_results[0].content == "x = 1"
        assert tool_results[0].tool_use_id == "call-1"

    def test_user_prompt(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "user.message",
                "data": {"content": "What does this do?"},
                "timestamp": "t1",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "copilot")
        assert len(entries) == 1
        assert entries[0].role == "user"
        assert entries[0].content == "What does this do?"

    def test_assistant_response(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text(
            json.dumps({
                "type": "assistant.message",
                "data": {"content": "It reads a file."},
                "timestamp": "t1",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "copilot")
        assert len(entries) == 1
        assert entries[0].role == "assistant"
        assert entries[0].content == "It reads a file."

    def test_ignores_non_content_events(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text(
            json.dumps({"type": "session.start", "data": {}, "timestamp": "t1"}) + "\n"
            + json.dumps({"type": "assistant.turn_start", "data": {}, "timestamp": "t2"}) + "\n"
            + json.dumps({
                "type": "user.message",
                "data": {"content": "real"},
                "timestamp": "t3",
            }) + "\n"
        )
        entries = reader.read(str(transcript), "copilot")
        assert len(entries) == 1
        assert entries[0].content == "real"

    def test_empty_transcript(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text("")
        entries = reader.read(str(transcript), "copilot")
        assert entries == []

    def test_malformed_lines_skipped(self, reader, tmp_path):
        transcript = tmp_path / "events.jsonl"
        transcript.write_text(
            "not json\n"
            + json.dumps({
                "type": "user.message",
                "data": {"content": "valid"},
            }) + "\n"
        )
        entries = reader.read(str(transcript), "copilot")
        assert len(entries) == 1
