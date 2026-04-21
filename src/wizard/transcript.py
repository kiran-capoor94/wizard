"""Reads and normalises agent conversation transcripts."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_CLAUDE_CODE_SKIP_TYPES = frozenset(
    {
        "progress",
        "file-history-snapshot",
        "system",
        "last-prompt",
    }
)


def find_transcript(agent_session_id: str, agent: str = "claude-code") -> Path | None:
    """Locate the transcript JSONL file for an agent session.

    Agent-specific discovery:
    - claude-code: ~/.claude/projects/*/<uuid>.jsonl
    - codex: (date-sharded; hook provides path via --transcript)
    - copilot: ~/.copilot/session-state/<id>/events.jsonl
    - gemini: (requires transcript_path from hook)
    - opencode: (requires session ID to assemble from storage)
    """
    if agent == "claude-code":
        matches = list(Path.home().glob(f".claude/projects/*/{agent_session_id}.jsonl"))
        return matches[0] if matches else None
    elif agent == "codex":
        # Codex transcripts are date-sharded: ~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl
        # Discovery by session UUID requires scanning date dirs.
        # Hook provides path via --transcript.
        return None
    elif agent == "copilot":
        session_file = (
            Path.home() / ".copilot" / "session-state" / agent_session_id / "events.jsonl"
        )
        return session_file if session_file.exists() else None
    return None


def read_new_lines(path: Path, skip: int) -> list[str]:
    """Read lines from a JSONL file, skipping the first `skip` lines.

    Drops the last line of new content to guard against partial JSON objects
    while the transcript is actively being written. The dropped line is picked
    up on the next poll once the following line has been written.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logger.debug("read_new_lines: failed to read %s: %s", path, e)
        return []
    new = lines[skip:]
    return new[:-1] if len(new) > 1 else []


class TranscriptEntry(BaseModel):
    """One normalised entry from an agent transcript."""

    role: str  # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    tool_name: str | None = None
    timestamp: str | None = None
    tool_use_id: str | None = None  # links tool_use block to its tool_result block


class TranscriptReader:
    """Read agent transcript files into a list of TranscriptEntry."""

    _PARSERS: dict[str, str] = {
        "claude-code": "_read_claude_code",
        "codex": "_read_codex",
        "gemini": "_read_gemini",
        "opencode": "_read_opencode",
        "copilot": "_read_copilot",
    }

    def read(self, path: str, agent: str) -> list[TranscriptEntry]:
        parser_name = self._PARSERS.get(agent)
        if parser_name is None:
            raise ValueError(f"Unsupported agent: {agent}")
        p = Path(path)
        # OpenCode stores data in a directory keyed by session ID, not a single file.
        # The path.stem is the session ID; existence is checked inside _read_opencode.
        if agent != "opencode" and not p.exists():
            raise FileNotFoundError(f"Transcript not found: {path}")
        parser = getattr(self, parser_name)
        return parser(p)

    def _read_claude_code(self, path: Path) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_type = raw.get("type", "")
                if entry_type in _CLAUDE_CODE_SKIP_TYPES:
                    continue
                timestamp = raw.get("timestamp")
                message = raw.get("message", {})
                content = message.get("content", "")
                if entry_type == "user":
                    entries.extend(
                        self._parse_claude_message(content, "user", timestamp)
                    )
                elif entry_type == "assistant":
                    entries.extend(
                        self._parse_claude_message(content, "assistant", timestamp)
                    )
        return entries

    def _parse_claude_message(
        self,
        content: str | list,
        role: str,
        timestamp: str | None,
    ) -> list[TranscriptEntry]:
        if isinstance(content, str):
            return [TranscriptEntry(role=role, content=content, timestamp=timestamp)]
        has_tool_use = any(
            isinstance(b, dict) and b.get("type") in ("tool_use", "tool_result")
            for b in content
        )
        entries: list[TranscriptEntry] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            if block_type == "text":
                if has_tool_use:
                    continue
                entries.append(
                    TranscriptEntry(
                        role=role,
                        content=block.get("text", ""),
                        timestamp=timestamp,
                    )
                )
            elif block_type == "tool_use":
                entries.append(
                    TranscriptEntry(
                        role="tool_call",
                        content=json.dumps(block.get("input", {})),
                        tool_name=block.get("name"),
                        timestamp=timestamp,
                        tool_use_id=block.get("id"),
                    )
                )
            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    tool_content = json.dumps(tool_content)
                entries.append(
                    TranscriptEntry(
                        role="tool_result",
                        content=str(tool_content),
                        tool_name=None,
                        timestamp=timestamp,
                        tool_use_id=block.get("tool_use_id"),
                    )
                )
        return entries

    def _read_codex(self, path: Path) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue

                timestamp = raw.get("timestamp")
                if raw.get("type") != "response_item":
                    continue

                payload = raw.get("payload", {})
                payload_type = payload.get("type")
                if payload_type == "message":
                    role = payload.get("role")
                    if role not in {"user", "assistant"}:
                        continue
                    entries.extend(
                        self._parse_codex_message(
                            payload.get("content", []),
                            role,
                            timestamp,
                        )
                    )
                elif payload_type == "function_call":
                    entries.append(
                        TranscriptEntry(
                            role="tool_call",
                            content=payload.get("arguments", ""),
                            tool_name=payload.get("name"),
                            timestamp=timestamp,
                        )
                    )
                elif payload_type == "function_call_output":
                    entries.append(
                        TranscriptEntry(
                            role="tool_result",
                            content=str(payload.get("output", "")),
                            timestamp=timestamp,
                        )
                    )
        return entries

    def _parse_codex_message(
        self,
        content: list,
        role: str,
        timestamp: str | None,
    ) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            text = block.get("text")
            if block_type in {"input_text", "output_text", "text"} and isinstance(
                text, str
            ):
                entries.append(
                    TranscriptEntry(
                        role=role,
                        content=text,
                        timestamp=timestamp,
                    )
                )
        return entries

    def _read_gemini(self, path: Path) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                entry_type = raw.get("type", "")
                if entry_type in {"info", "error", "warning"}:
                    continue
                timestamp = raw.get("timestamp")
                role = "user" if entry_type == "user" else "assistant"
                content_raw = raw.get("content") or raw.get("text") or ""
                content = self._normalise_gemini_content(content_raw)
                if content:
                    entries.append(
                        TranscriptEntry(
                            role=role,
                            content=content,
                            timestamp=timestamp,
                        )
                    )
                for tc in raw.get("toolCalls", []):
                    if not isinstance(tc, dict):
                        continue
                    entries.append(
                        TranscriptEntry(
                            role="tool_call",
                            content=json.dumps(tc.get("args", {})),
                            tool_name=tc.get("name"),
                            timestamp=timestamp,
                            tool_use_id=tc.get("id"),
                        )
                    )
        return entries

    def _normalise_gemini_content(self, content_raw: object) -> str:
        """Coerce Gemini content (string, parts list, or other) to a plain string."""
        if isinstance(content_raw, str):
            return content_raw
        if isinstance(content_raw, list):
            # Gemini parts list: [{"text": "..."}, ...]
            return " ".join(
                p.get("text", "") for p in content_raw if isinstance(p, dict)
            )
        if content_raw is None:
            return ""
        return str(content_raw)

    def _parse_opencode_part(
        self, part: dict, role: str, timestamp: str | None
    ) -> list[TranscriptEntry]:
        part_type = part.get("type", "")
        if part_type == "text":
            return [TranscriptEntry(role=role, content=part.get("text", ""), timestamp=timestamp)]
        if part_type == "tool-invocation":
            ti = part.get("toolInvocation", {})
            if ti.get("state") == "result":
                result = ti.get("result", "")
                return [TranscriptEntry(
                    role="tool_result",
                    content=json.dumps(result) if isinstance(result, (dict, list)) else str(result),
                    tool_name=ti.get("toolName"),
                    timestamp=timestamp,
                    tool_use_id=ti.get("toolCallId"),
                )]
            return [TranscriptEntry(
                role="tool_call",
                content=json.dumps(ti.get("args", {})),
                tool_name=ti.get("toolName"),
                timestamp=timestamp,
                tool_use_id=ti.get("toolCallId"),
            )]
        return []

    def _read_opencode(self, path: Path) -> list[TranscriptEntry]:
        base = Path.home() / ".local" / "share" / "opencode" / "storage"
        session_id = path.stem
        msg_dir = base / "message" / session_id
        if not msg_dir.exists():
            return []

        messages: list[tuple[float, dict]] = []
        for msg_file in msg_dir.glob("*.json"):
            try:
                msg = json.loads(msg_file.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            try:
                created = float(msg.get("metadata", {}).get("time", {}).get("created", 0))
            except (TypeError, ValueError):
                created = 0.0
            messages.append((created, msg))

        entries: list[TranscriptEntry] = []
        for _, msg in sorted(messages, key=lambda x: x[0]):
            role = msg.get("role", "assistant")
            ts = msg.get("metadata", {}).get("time", {}).get("created")
            timestamp = str(ts) if ts is not None else None
            for part in msg.get("parts", []):
                if isinstance(part, dict):
                    entries.extend(self._parse_opencode_part(part, role, timestamp))
        return entries

    def _parse_copilot_assistant_message(
        self, data: dict, timestamp: str | None
    ) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        content = data.get("content", "")
        if content:
            entries.append(
                TranscriptEntry(role="assistant", content=str(content), timestamp=timestamp)
            )
        for tr in data.get("toolRequests", []):
            if not isinstance(tr, dict):
                continue
            entries.append(TranscriptEntry(
                role="tool_call",
                content=json.dumps(tr.get("arguments", {})),
                tool_name=tr.get("name"),
                timestamp=timestamp,
                tool_use_id=tr.get("toolCallId"),
            ))
        return entries

    def _read_copilot(self, path: Path) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    continue
                timestamp = raw.get("timestamp")
                event_type = raw.get("type", "")
                data = raw.get("data") or {}
                if event_type == "user.message":
                    content = data.get("content", "")
                    if content:
                        entries.append(
                            TranscriptEntry(role="user", content=str(content), timestamp=timestamp)
                        )
                elif event_type == "assistant.message":
                    entries.extend(self._parse_copilot_assistant_message(data, timestamp))
                elif event_type == "tool.execution_complete":
                    result = data.get("result", {})
                    if isinstance(result, dict):
                        result_text = result.get("content", json.dumps(result))
                    else:
                        result_text = str(result)
                    entries.append(TranscriptEntry(
                        role="tool_result",
                        content=result_text,
                        timestamp=timestamp,
                        tool_use_id=data.get("toolCallId"),
                    ))
        return entries


