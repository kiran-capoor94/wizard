"""Reads and normalises agent conversation transcripts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_CLAUDE_CODE_SKIP_TYPES = frozenset({
    "progress", "file-history-snapshot", "system", "last-prompt",
})


@dataclass
class TranscriptEntry:
    """One normalised entry from an agent transcript."""

    role: str  # "user" | "assistant" | "tool_call" | "tool_result"
    content: str
    tool_name: str | None = None
    timestamp: str | None = None


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
        self, content: str | list, role: str, timestamp: str | None,
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
                entries.append(TranscriptEntry(
                    role=role,
                    content=block.get("text", ""),
                    timestamp=timestamp,
                ))
            elif block_type == "tool_use":
                entries.append(TranscriptEntry(
                    role="tool_call",
                    content=json.dumps(block.get("input", {})),
                    tool_name=block.get("name"),
                    timestamp=timestamp,
                ))
            elif block_type == "tool_result":
                tool_content = block.get("content", "")
                if isinstance(tool_content, list):
                    tool_content = json.dumps(tool_content)
                entries.append(TranscriptEntry(
                    role="tool_result",
                    content=str(tool_content),
                    tool_name=None,
                    timestamp=timestamp,
                ))
        return entries

    def _read_codex(self, path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("Codex transcript parser not yet implemented")

    def _read_gemini(self, path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("Gemini transcript parser not yet implemented")

    def _read_opencode(self, path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("OpenCode transcript parser not yet implemented")
