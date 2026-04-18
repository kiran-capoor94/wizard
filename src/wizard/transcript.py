"""Reads and normalises agent conversation transcripts."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from wizard.models import Note, NoteType
from wizard.repositories import NoteRepository
from wizard.schemas import SynthesisNote, SynthesisResult
from wizard.security import SecurityService

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


_SYNTHESIS_SYSTEM_PROMPT = (
    "You are synthesising a coding session transcript into structured notes "
    "for a task management system. Be concise. Focus on what was accomplished, "
    "what was found, and what decisions were made."
)


class CaptureSynthesiser:
    """Synthesise agent transcripts into structured Note objects."""

    def __init__(
        self,
        reader: TranscriptReader,
        note_repo: NoteRepository,
        security: SecurityService,
    ):
        self._reader = reader
        self._note_repo = note_repo
        self._security = security

    async def synthesise(self, db, ctx, wizard_session, tasks=None) -> SynthesisResult:
        if not wizard_session.transcript_path or not wizard_session.agent:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        try:
            entries = self._reader.read(
                wizard_session.transcript_path, wizard_session.agent,
            )
        except (FileNotFoundError, NotImplementedError) as e:
            logger.warning("CaptureSynthesiser: could not read transcript: %s", e)
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        if not entries:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback",
            )
        tasks = tasks or []
        notes_data, via = await self._try_sampling(ctx, entries, tasks)
        if notes_data is None:
            summary, via = self._synthetic_summary(entries)
            clean = self._security.scrub(summary).clean
            note = Note(
                note_type=NoteType.SESSION_SUMMARY,
                content=clean,
                session_id=wizard_session.id,
            )
            self._note_repo.save(db, note)
            return SynthesisResult(
                notes_created=1, task_ids_touched=[], synthesised_via=via,
            )
        saved_count = 0
        task_ids: list[int] = []
        for nd in notes_data:
            clean_content = self._security.scrub(nd.content).clean
            clean_model = (
                self._security.scrub(nd.mental_model).clean if nd.mental_model else None
            )
            note = Note(
                note_type=self._resolve_note_type(nd.note_type),
                content=clean_content,
                mental_model=clean_model,
                task_id=nd.task_id,
                session_id=wizard_session.id,
            )
            self._note_repo.save(db, note)
            saved_count += 1
            if nd.task_id is not None:
                task_ids.append(nd.task_id)
        return SynthesisResult(
            notes_created=saved_count,
            task_ids_touched=list(set(task_ids)),
            synthesised_via=via,
        )

    async def _try_sampling(self, ctx, entries, tasks):
        chunks = self._chunk_entries(entries)
        all_notes: list[SynthesisNote] = []
        for chunk in chunks:
            prompt = self._build_synthesis_prompt(chunk, tasks)
            try:
                result = await ctx.sample(
                    messages=prompt,
                    system_prompt=_SYNTHESIS_SYSTEM_PROMPT,
                    result_type=list[SynthesisNote],
                    max_tokens=2000,
                    temperature=0.3,
                )
                all_notes.extend(result.result)
            except Exception as e:
                logger.warning("CaptureSynthesiser sampling failed: %s", e)
                return None, ""
        if not all_notes:
            return None, ""
        return all_notes[:5], "sampling"

    def _build_synthesis_prompt(self, entries, tasks) -> str:
        lines = ["Session transcript (chronological):\n"]
        for e in entries:
            prefix = e.role.upper()
            if e.tool_name:
                prefix = f"{prefix} [{e.tool_name}]"
            content = e.content[:2000] if len(e.content) > 2000 else e.content
            lines.append(f"  {prefix}: {content}")
        if tasks:
            lines.append("\nKnown tasks in this session:")
            for t in tasks:
                lines.append(f"  - Task {t.id}: {t.name}")
        lines.append(
            "\nFor each distinct task or workstream, produce a JSON array of notes:\n"
            '[{"task_id": <int or null>, "note_type": '
            '"investigation"|"decision"|"docs"|"learnings", '
            '"content": "<what was done/found/changed>", '
            '"mental_model": "<2-3 sentence snapshot>"}]\n\n'
            "Rules:\n"
            "- Focus on WHAT and WHY, not mechanical tool calls.\n"
            "- Reads followed by Edits = 'investigated X, changed Y because Z'.\n"
            "- Test runs = 'tests passed/failed, specifically: ...'.\n"
            "- Decisions get note_type 'decision' with rationale.\n"
            "- Ignore noise (ls, pwd, git status with no follow-up).\n"
            "- Maximum 5 notes. Merge related work."
        )
        return "\n".join(lines)

    def _chunk_entries(self, entries, max_chars=50_000):
        chunks: list[list[TranscriptEntry]] = []
        current: list[TranscriptEntry] = []
        current_size = 0
        for entry in entries:
            entry_size = len(entry.content) + len(entry.role) + 20
            if current and current_size + entry_size > max_chars:
                chunks.append(current)
                current = []
                current_size = 0
            current.append(entry)
            current_size += entry_size
        if current:
            chunks.append(current)
        return chunks

    def _synthetic_summary(self, entries):
        tool_names = sorted({e.tool_name for e in entries if e.tool_name})
        tools_str = ", ".join(tool_names) if tool_names else "none"
        return (
            f"Auto-synthesised: {len(entries)} transcript entries. "
            f"Tools used: {tools_str}."
        ), "synthetic"

    def _resolve_note_type(self, raw: str) -> NoteType:
        mapping = {
            "investigation": NoteType.INVESTIGATION,
            "decision": NoteType.DECISION,
            "docs": NoteType.DOCS,
            "learnings": NoteType.LEARNINGS,
        }
        return mapping.get(raw, NoteType.INVESTIGATION)
