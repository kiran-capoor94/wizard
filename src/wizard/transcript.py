"""Reads and normalises agent conversation transcripts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import ollama
from pydantic import RootModel
from sqlmodel import Session

from wizard.config import settings
from wizard.models import Note, NoteType, WizardSession
from wizard.repositories import NoteRepository
from wizard.schemas import SynthesisNote, SynthesisResult
from wizard.security import SecurityService

logger = logging.getLogger(__name__)

_CLAUDE_CODE_SKIP_TYPES = frozenset({
    "progress", "file-history-snapshot", "system", "last-prompt",
})

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
                    entries.append(TranscriptEntry(
                        role="tool_call",
                        content=payload.get("arguments", ""),
                        tool_name=payload.get("name"),
                        timestamp=timestamp,
                    ))
                elif payload_type == "function_call_output":
                    entries.append(TranscriptEntry(
                        role="tool_result",
                        content=str(payload.get("output", "")),
                        timestamp=timestamp,
                    ))
        return entries

    def _parse_codex_message(
        self, content: list, role: str, timestamp: str | None,
    ) -> list[TranscriptEntry]:
        entries: list[TranscriptEntry] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = block.get("type", "")
            text = block.get("text")
            if block_type in {"input_text", "output_text", "text"} and isinstance(text, str):
                entries.append(TranscriptEntry(
                    role=role,
                    content=text,
                    timestamp=timestamp,
                ))
        return entries

    def _read_gemini(self, path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("Gemini transcript parser not yet implemented")

    def _read_opencode(self, path: Path) -> list[TranscriptEntry]:
        raise NotImplementedError("OpenCode transcript parser not yet implemented")


class _NoteList(RootModel[list[SynthesisNote]]):
    """Pydantic wrapper so model_json_schema() produces a top-level array schema."""
    root: list[SynthesisNote]


class OllamaSynthesiser:
    """Synthesise agent transcripts into structured Note objects via local Ollama."""

    def __init__(
        self,
        reader: TranscriptReader,
        note_repo: NoteRepository,
        security: SecurityService,
    ):
        self._reader = reader
        self._note_repo = note_repo
        self._security = security

    def synthesise_path(
        self,
        db: Session,
        wizard_session: WizardSession,
        transcript_path: Path,
    ) -> SynthesisResult:
        """Synthesise a specific transcript file into notes. Core implementation."""
        if not wizard_session.agent:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        try:
            entries = self._reader.read(str(transcript_path), wizard_session.agent)
        except (FileNotFoundError, NotImplementedError, ValueError) as e:
            logger.warning("OllamaSynthesiser: cannot read transcript: %s", e)
            return SynthesisResult(notes_created=0, task_ids_touched=[], synthesised_via="fallback")
        if not entries:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        try:
            notes_data = self._call_ollama(entries)
        except Exception as e:
            logger.warning("OllamaSynthesiser: Ollama call failed: %s", e)
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        saved = self._save_notes(db, notes_data, wizard_session)
        wizard_session.is_synthesised = True
        if wizard_session.summary is None:
            wizard_session.summary = f"Synthesised {saved} note(s) from transcript."
        db.add(wizard_session)
        db.flush()
        return SynthesisResult(
            notes_created=saved, task_ids_touched=[], synthesised_via="ollama",
        )

    def synthesise(self, db: Session, wizard_session: WizardSession) -> SynthesisResult:
        """Synthesise session.transcript_path. Delegates to synthesise_path."""
        if not wizard_session.transcript_path:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        return self.synthesise_path(db, wizard_session, Path(wizard_session.transcript_path))

    def _call_ollama(self, entries: list[TranscriptEntry]) -> list[SynthesisNote]:
        client = ollama.Client(host=settings.synthesis.base_url)
        response = client.chat(
            model=settings.synthesis.model,
            messages=[
                {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_prompt(entries)},
            ],
            format=_NoteList.model_json_schema(),
        )
        return _NoteList.model_validate_json(response.message.content).root

    def _build_prompt(self, entries: list[TranscriptEntry]) -> str:
        lines = ["Session transcript (chronological):\n"]
        for e in entries:
            prefix = e.role.upper()
            if e.tool_name:
                prefix = f"{prefix} [{e.tool_name}]"
            content = e.content[:2000] if len(e.content) > 2000 else e.content
            lines.append(f"  {prefix}: {content}")
        lines.append(
            "\nFor each distinct task or workstream, produce a JSON array of notes. "
            "task_id must always be null — wizard handles task matching separately.\n\n"
            "Rules:\n"
            "- Focus on WHAT and WHY, not mechanical tool calls.\n"
            "- Reads followed by Edits = 'investigated X, changed Y because Z'.\n"
            "- Test runs = 'tests passed/failed, specifically: ...'.\n"
            "- Decisions get note_type 'decision' with rationale.\n"
            "- Ignore noise (ls, pwd, git status with no follow-up).\n"
            "- Maximum 5 notes. Merge related work."
        )
        return "\n".join(lines)

    def _save_notes(
        self, db: Session, notes_data: list[SynthesisNote], wizard_session: WizardSession,
    ) -> int:
        count = 0
        for nd in notes_data:
            clean_content = self._security.scrub(nd.content).clean
            clean_model = (
                self._security.scrub(nd.mental_model).clean if nd.mental_model else None
            )
            note = Note(
                note_type=self._resolve_note_type(nd.note_type),
                content=clean_content,
                mental_model=clean_model,
                task_id=None,
                session_id=wizard_session.id,
            )
            self._note_repo.save(db, note)
            count += 1
        return count

    def _resolve_note_type(self, raw: str) -> NoteType:
        mapping = {
            "investigation": NoteType.INVESTIGATION,
            "decision": NoteType.DECISION,
            "docs": NoteType.DOCS,
            "learnings": NoteType.LEARNINGS,
        }
        return mapping.get(raw, NoteType.INVESTIGATION)
