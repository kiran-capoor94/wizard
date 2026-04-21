"""Reads and normalises agent conversation transcripts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CLAUDE_CODE_SKIP_TYPES = frozenset(
    {
        "progress",
        "file-history-snapshot",
        "system",
        "last-prompt",
    }
)


def find_transcript(agent_session_id: str) -> Path | None:
    """Locate the Claude Code transcript JSONL file for an agent session UUID.

    Globs ~/.claude/projects/*/<uuid>.jsonl — the path Claude Code uses for
    per-project transcripts. Returns the first match, or None if not found.
    """
    matches = list(Path.home().glob(f".claude/projects/*/{agent_session_id}.jsonl"))
    return matches[0] if matches else None


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


_SYNTHESIS_SYSTEM_PROMPT = (
    "You are synthesising a coding session transcript into structured notes "
    "for a task management system. Be concise. Focus on what was accomplished, "
    "what was found, and what decisions were made."
)


@dataclass
class TranscriptEntry:
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
    }

    def read(self, path: str, agent: str) -> list[TranscriptEntry]:
        parser_name = self._PARSERS.get(agent)
        if parser_name is None:
            raise ValueError(f"Unsupported agent: {agent}")
        p = Path(path)
        if not p.exists():
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

    def _read_gemini(self, _path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("Gemini transcript parser not yet implemented")

    def _read_opencode(self, _path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("OpenCode transcript parser not yet implemented")


