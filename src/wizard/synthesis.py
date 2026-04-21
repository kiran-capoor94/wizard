"""Synthesiser — synthesise agent transcripts into structured Note objects."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Protocol

import litellm
from sqlmodel import Session, col, select

from wizard.config import settings
from wizard.models import Note, NoteType, WizardSession
from wizard.repositories import (
    NoteRepository,
    TaskRepository,
    TaskStateRepository,
    build_rolling_summary,
)
from wizard.schemas import SynthesisNote, SynthesisResult
from wizard.security import SecurityService
from wizard.transcript import TranscriptEntry, TranscriptReader

logger = logging.getLogger(__name__)

# JSON schema for structured synthesis output — inlined to avoid $ref/$defs.
_SYNTHESIS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "required": ["note_type", "content"],
        "properties": {
            "task_id": {"type": "integer"},
            "note_type": {"type": "string"},
            "content": {"type": "string"},
            "mental_model": {"type": "string"},
        },
    },
}

_SYNTHESIS_SYSTEM_PROMPT = (
    "You are synthesising a coding session transcript into structured notes "
    "for a task management system. Be concise. Focus on what was accomplished, "
    "what was found, and what decisions were made."
)

# Drop tool_result for read/nav tools — the tool_call input is sufficient signal.
_SKIP_RESULT_TOOLS = frozenset(
    {
        "Read",
        "Glob",
        "Grep",
        "LS",
        "WebFetch",
        "WebSearch",
        "NotebookRead",
    }
)

# Per-role character budgets applied after filtering.
_TRUNCATE: dict[str, int] = {
    "user": 1000,
    "assistant": 1000,
    "tool_call": 250,
    "tool_result": 150,
}


class SynthesisAdapter(Protocol):
    """Protocol for LLM backends used by Synthesiser."""

    @property
    def model_id(self) -> str: ...

    def complete(
        self,
        messages: list[dict],
        schema: dict,
    ) -> list[SynthesisNote]: ...


class LiteLLMAdapter:
    """LiteLLM-backed SynthesisAdapter. Supports any litellm-compatible provider."""

    def __init__(
        self,
        model: str,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url or None
        self._api_key = api_key or None

    @property
    def model_id(self) -> str:
        return self._model

    def complete(self, messages: list[dict], schema: dict) -> list[SynthesisNote]:
        kwargs: dict = {"model": self._model, "messages": messages}
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._api_key:
            kwargs["api_key"] = self._api_key
        try:
            response = litellm.completion(
                **kwargs,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "notes", "schema": schema},
                },
            )
            raw = response.choices[0].message.content
        except Exception:
            response = litellm.completion(**kwargs)
            raw = response.choices[0].message.content
        raw = self._extract_json(raw or "")
        return [SynthesisNote.model_validate(n) for n in json.loads(raw)]

    @staticmethod
    def _extract_json(text: str) -> str:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        return match.group(1).strip() if match else text.strip()


class Synthesiser:
    """Synthesise agent transcripts into structured Note objects."""

    def __init__(
        self,
        reader: TranscriptReader,
        note_repo: NoteRepository,
        security: SecurityService,
        task_state_repo: TaskStateRepository | None = None,
        t_repo: TaskRepository | None = None,
        adapter: SynthesisAdapter | None = None,
    ):
        self._reader = reader
        self._note_repo = note_repo
        self._security = security
        self._task_state_repo = task_state_repo or TaskStateRepository()
        self._t_repo = t_repo or TaskRepository()
        self._adapter = adapter or LiteLLMAdapter(
            model=settings.synthesis.model,
            base_url=settings.synthesis.base_url or None,
            api_key=settings.synthesis.api_key or None,
        )

    def synthesise_path(
        self,
        db: Session,
        wizard_session: WizardSession,
        transcript_path: Path,
        terminal: bool = True,
    ) -> SynthesisResult:
        """Synthesise a specific transcript file into notes. Core implementation."""
        if not wizard_session.agent:
            return SynthesisResult(
                notes_created=0,
                task_ids_touched=[],
                synthesised_via="fallback",
            )
        try:
            entries = self._reader.read(str(transcript_path), wizard_session.agent)
        except (FileNotFoundError, NotImplementedError, ValueError) as e:
            logger.warning("Synthesiser: cannot read transcript: %s", e)
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback"
            )
        if not entries:
            return SynthesisResult(
                notes_created=0,
                task_ids_touched=[],
                synthesised_via="fallback",
            )
        open_tasks = self._t_repo.get_open_tasks_compact(db)
        valid_task_ids = {tid for tid, _ in open_tasks}
        task_table = "\n".join(f"{tid}\t{name}" for tid, name in open_tasks)
        messages = [
            {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
            {"role": "user", "content": self._build_prompt(entries, task_table)},
        ]
        try:
            notes_data = self._adapter.complete(messages, _SYNTHESIS_SCHEMA)
        except Exception as e:
            logger.warning("Synthesiser: LLM call failed: %s", e)
            return SynthesisResult(
                notes_created=0,
                task_ids_touched=[],
                synthesised_via="fallback",
            )
        saved = self._save_notes(db, notes_data, wizard_session, valid_task_ids)
        if terminal:
            wizard_session.is_synthesised = True
        if wizard_session.summary is None:
            wizard_session.summary = f"Synthesised {saved} note(s) from transcript."
        db.add(wizard_session)
        db.flush()
        task_ids_touched = self._refresh_rolling_summaries(db, wizard_session)
        return SynthesisResult(
            notes_created=saved,
            task_ids_touched=task_ids_touched,
            synthesised_via=self._adapter.model_id,
        )

    def synthesise(self, db: Session, wizard_session: WizardSession) -> SynthesisResult:
        """Synthesise session.transcript_path. Delegates to synthesise_path."""
        if not wizard_session.transcript_path:
            return SynthesisResult(
                notes_created=0,
                task_ids_touched=[],
                synthesised_via="fallback",
            )
        return self.synthesise_path(
            db, wizard_session, Path(wizard_session.transcript_path)
        )

    def synthesise_lines(
        self,
        db: Session,
        wizard_session: WizardSession,
        lines: list[str],
    ) -> SynthesisResult:
        """Synthesise a slice of JSONL lines as a partial transcript.

        Writes lines to a NamedTemporaryFile, delegates to synthesise_path,
        then deletes the temp file.
        """
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write("\n".join(lines) + "\n")
            tmp_path = Path(tmp.name)
        try:
            return self.synthesise_path(db, wizard_session, tmp_path, terminal=False)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _filter_for_synthesis(
        self, entries: list[TranscriptEntry]
    ) -> list[TranscriptEntry]:
        """Drop low-signal entries and truncate content per role.
        tool_result for read/navigation tools (Read, Glob, Grep, etc.) adds
        noise — the tool_call input already captures what was read.
        tool_result for action tools (Bash, Edit, Write, Agent) signals outcomes
        and is kept. tool_use_id from the Claude API links each result to its
        call; orphaned results (no matching id) are kept conservatively.
        """
        kept: list[TranscriptEntry] = []
        call_by_id: dict[str, str | None] = {}
        for entry in entries:
            if entry.role == "tool_call":
                if entry.tool_use_id:
                    call_by_id[entry.tool_use_id] = entry.tool_name
                kept.append(
                    entry.model_copy(update={"content": entry.content[: _TRUNCATE["tool_call"]]})
                )
            elif entry.role == "tool_result":
                call_name = (
                    call_by_id.pop(entry.tool_use_id, None)
                    if entry.tool_use_id
                    else None
                )
                if call_name in _SKIP_RESULT_TOOLS:
                    continue
                kept.append(
                    entry.model_copy(update={"content": entry.content[: _TRUNCATE["tool_result"]]})
                )
            else:
                kept.append(
                    entry.model_copy(
                        update={"content": entry.content[: _TRUNCATE.get(entry.role, 2000)]}
                    )
                )
        return kept

    def _build_prompt(
        self, entries: list[TranscriptEntry], task_table: str = ""
    ) -> str:
        filtered = self._filter_for_synthesis(entries)
        total_chars = sum(len(e.content) for e in filtered)
        if total_chars > 200_000:
            logger.warning(
                "_build_prompt: %d chars after filtering; trimming oldest entries",
                total_chars,
            )
            while filtered and total_chars > 200_000:
                total_chars -= len(filtered.pop(0).content)
        lines = ["Session transcript (chronological):\n"]
        for e in filtered:
            prefix = e.role.upper()
            if e.tool_name:
                prefix = f"{prefix} [{e.tool_name}]"
            lines.append(f"  {prefix}: {e.content}")
        if task_table:
            lines.append(
                f"\nAvailable tasks (id<TAB>name):\n{task_table}\n\n"
                "Set task_id to the matching integer ID if the note clearly relates to a task. "
                "Set task_id to null if uncertain or if no task matches."
            )
        else:
            lines.append("\ntask_id must always be null — no task list available.")
        lines.append(
            "\n\nFor each distinct task or workstream, produce a JSON array of notes. "
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
        self,
        db: Session,
        notes_data: list[SynthesisNote],
        wizard_session: WizardSession,
        valid_task_ids: set[int] | None = None,
    ) -> int:
        count = 0
        for nd in notes_data:
            clean_content = self._security.scrub(nd.content).clean
            clean_model = (
                self._security.scrub(nd.mental_model).clean if nd.mental_model else None
            )
            matched_task_id = (
                nd.task_id
                if nd.task_id is not None
                and (valid_task_ids is None or nd.task_id in valid_task_ids)
                else None
            )
            note = Note(
                note_type=self._resolve_note_type(nd.note_type),
                content=clean_content,
                mental_model=clean_model,
                task_id=matched_task_id,
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

    def _refresh_rolling_summaries(
        self, db: Session, wizard_session: WizardSession
    ) -> list[int]:
        """Rebuild rolling_summary for tasks that received notes during this session."""
        if wizard_session.id is None:
            return []

        task_ids: list[int] = list(
            {
                n
                for n in db.exec(
                    select(Note.task_id)
                    .where(Note.session_id == wizard_session.id)
                    .where(col(Note.task_id).is_not(None))
                ).all()
                if n is not None
            }
        )

        if not task_ids:
            return []

        for task_id in task_ids:
            all_notes = list(
                db.exec(select(Note).where(col(Note.task_id) == task_id)).all()
            )
            summary = build_rolling_summary(all_notes)
            if summary is not None:
                self._task_state_repo.update_rolling_summary(db, task_id, summary)

        return task_ids
