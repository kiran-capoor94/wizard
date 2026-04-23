"""Synthesiser — synthesise agent transcripts into structured Note objects."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import litellm
import sentry_sdk
from pydantic import ValidationError
from sqlmodel import Session, col, select

from wizard.config import settings
from wizard.llm_adapters import complete as llm_complete
from wizard.llm_adapters import probe_backend_health
from wizard.models import Note, NoteType, Task, WizardSession
from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
from wizard.schemas import SynthesisNote, SynthesisResult
from wizard.security import SecurityService
from wizard.transcript import TranscriptEntry, TranscriptReader

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = (
    "You are synthesising a coding session transcript into structured notes "
    "for a task management system. Be concise. Focus on what was accomplished, "
    "what was found, and what decisions were made. "
    "Respond directly with a JSON array — no thinking blocks, no preamble."
)

# Drop tool_result for read/nav tools — the tool_call input is sufficient signal.
# We only keep results for tools that mutate or provide high-level agency.
KEEP_RESULT_TOOLS = frozenset({"Edit", "Write", "Agent", "Bash"})

# Per-role character budgets applied after filtering.
ROLE_CHAR_LIMITS: dict[str, int] = {
    "user": 400,
    "assistant": 400,
    "tool_call": 150,
    "tool_result": 200,
}

NOTE_TYPE_MAP: dict[str, NoteType] = {
    "investigation": NoteType.INVESTIGATION,
    "decision": NoteType.DECISION,
    "docs": NoteType.DOCS,
    "learnings": NoteType.LEARNINGS,
}

# Maximum chars per synthesis chunk. Default to 15k for extremely fast local prefill.
CHUNK_CHAR_LIMIT: int = min(
    settings.synthesis.context_chars, 15000
)  # 15k for fast local prefill


def _format_transcript(entries: list[TranscriptEntry]) -> str:
    """Encode transcript entries as plain text for the LLM prompt.

    Each entry becomes a single line: [role] content or [role:tool] content.
    Simpler than TOON CSV — avoids quoting overhead for local models.
    """
    if not entries:
        return ""
    lines = []
    for e in entries:
        role_tag = f"{e.role}:{e.tool_name}" if e.tool_name else e.role
        lines.append(f"[{role_tag}] {e.content}")
    return "\n".join(lines)


class Synthesiser:
    """Synthesise agent transcripts into structured Note objects."""

    def __init__(
        self,
        reader: TranscriptReader,
        note_repo: NoteRepository,
        security: SecurityService,
        task_state_repo: TaskStateRepository | None = None,
        t_repo: TaskRepository | None = None,
        backend: dict | None = None,
    ):
        self._reader = reader
        self._note_repo = note_repo
        self._security = security
        self._task_state_repo = task_state_repo or TaskStateRepository()
        self._t_repo = t_repo or TaskRepository()
        self._backend = (
            backend if backend is not None else self._select_backend(settings.synthesis)
        )

    @staticmethod
    def _select_backend(synthesis_settings) -> dict:
        """Health-check configured backends; return the first reachable one."""
        for b in synthesis_settings.backends:
            config = {
                "model": b.model or synthesis_settings.model,
                "base_url": b.base_url or None,
                "api_key": b.api_key or None,
            }
            if probe_backend_health(config["base_url"]):
                logger.info("Synthesiser: selected backend: %s", config["model"])
                return config
        return {
            "model": synthesis_settings.model,
            "base_url": synthesis_settings.base_url or None,
            "api_key": synthesis_settings.api_key or None,
        }

    def _write_failure_marker(
        self, db: Session, wizard_session: WizardSession, chunk_description: str
    ) -> None:
        """Write a recoverable investigation note when synthesis fails after retry."""
        marker = Note(
            note_type=NoteType.INVESTIGATION,
            content=(
                f"Synthesis failed for session {wizard_session.id}. "
                f"{chunk_description} "
                "Content available in wizardsession.transcript_raw. "
                "Retry with: wizard capture --resynthesise --session-id "
                f"{wizard_session.id}"
            ),
            session_id=wizard_session.id,
            artifact_id=wizard_session.artifact_id,
            artifact_type="session",
            synthesis_confidence=0.0,
            status="unclassified",
        )
        self._note_repo.save(db, marker)

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
                notes_created=0, task_ids_touched=[], synthesised_via="fallback"
            )

        with sentry_sdk.start_span(
            op="synthesis.path", description=str(transcript_path)
        ) as span:
            span.set_tag("session_id", wizard_session.id)
            span.set_tag("agent", wizard_session.agent)

            task_table, valid_task_ids = self.prepare_task_table(db)
            had_failure = False
            try:
                notes_data = self.generate_notes(
                    transcript_path, wizard_session.agent, task_table
                )
            except Exception as exc:
                logger.warning(
                    "Synthesiser: generate_notes failed after retry for session %d: %s",
                    wizard_session.id,
                    exc,
                )
                self._write_failure_marker(
                    db,
                    wizard_session,
                    f"Transcript: {transcript_path.name}.",
                )
                had_failure = True
                notes_data = []

            if not notes_data and not had_failure:
                if terminal:
                    wizard_session.synthesis_status = "complete"
                    wizard_session.is_synthesised = True
                    db.add(wizard_session)
                    db.flush()
                return SynthesisResult(
                    notes_created=0, task_ids_touched=[], synthesised_via="fallback"
                )
            return self.persist(
                db, notes_data, wizard_session, valid_task_ids, terminal, had_failure
            )

    def prepare_task_table(self, db: Session) -> tuple[str, set[int]]:
        """Fetch open tasks and format them for the LLM prompt. Used by prepare stage."""
        with sentry_sdk.start_span(op="synthesis.prepare"):
            open_tasks = self._t_repo.get_open_tasks_compact(db)
            valid_task_ids = {tid for tid, _ in open_tasks}
            task_table = "\n".join(f"{tid}\t{name}" for tid, name in open_tasks)
            return task_table, valid_task_ids

    def generate_notes(
        self,
        transcript_path: Path,
        agent: str,
        task_table: str,
    ) -> list[SynthesisNote]:
        """Perform the LLM call outside any database transaction. Used by generate stage."""
        with sentry_sdk.start_span(op="synthesis.read"):
            entries = self._read_entries(transcript_path, agent)
            if not entries:
                return []

        with sentry_sdk.start_span(op="synthesis.filter"):
            filtered = self._filter_for_synthesis(entries)
            messages = [
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": self._format_prompt(filtered, task_table)},
            ]

        return self._call_adapter(messages, filtered, task_table)

    def persist(
        self,
        db: Session,
        notes_data: list[SynthesisNote],
        wizard_session: WizardSession,
        valid_task_ids: set[int],
        terminal: bool,
        had_failure: bool = False,
    ) -> SynthesisResult:
        """Save notes, update session state, refresh task summaries, return result."""
        with sentry_sdk.start_span(op="synthesis.persist"):
            saved = self._save_notes(db, notes_data, wizard_session, valid_task_ids)
            if terminal:
                if had_failure:
                    wizard_session.synthesis_status = "partial_failure"
                else:
                    wizard_session.is_synthesised = True
                    wizard_session.synthesis_status = "complete"
            if wizard_session.summary is None:
                wizard_session.summary = f"Synthesised {saved} note(s) from transcript."
            db.add(wizard_session)
            db.flush()
            task_ids_touched = self._refresh_rolling_summaries(db, wizard_session)
            return SynthesisResult(
                notes_created=saved,
                task_ids_touched=task_ids_touched,
                synthesised_via=self._backend["model"],
            )

    def synthesise(self, db: Session, wizard_session: WizardSession) -> SynthesisResult:
        """Synthesise session.transcript_path. Delegates to synthesise_path."""
        if not wizard_session.transcript_path:
            return SynthesisResult(
                notes_created=0, task_ids_touched=[], synthesised_via="fallback"
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
        """Synthesise a slice of JSONL lines as a partial transcript."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write("\n".join(lines) + "\n")
            tmp_path = Path(tmp.name)
        try:
            return self.synthesise_path(db, wizard_session, tmp_path, terminal=False)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _read_entries(self, transcript_path: Path, agent: str) -> list[TranscriptEntry]:
        """Read and parse transcript. Returns empty list on any read failure."""
        try:
            return self._reader.read(str(transcript_path), agent)
        except (
            FileNotFoundError,
            NotImplementedError,
            ValueError,
            ValidationError,
        ) as e:
            logger.warning("Synthesiser: cannot read transcript: %s", e)
            return []

    def _call_adapter(
        self,
        messages: list[dict],
        filtered: list[TranscriptEntry],
        task_table: str,
    ) -> list[SynthesisNote]:
        """Call the adapter, falling back to chunked synthesis on context overflow.

        Raises on non-context-overflow failures so callers can write failure markers.
        Retries once before raising (spec §9.3).
        """
        last_exc: Exception | None = None
        for attempt in range(2):  # one retry per spec §9.3
            try:
                return llm_complete(
                    self._backend["model"],
                    messages,
                    self._backend.get("base_url"),
                    self._backend.get("api_key"),
                )
            except Exception as e:
                if isinstance(
                    e, getattr(litellm, "ContextWindowExceededError", type(None))
                ):
                    return self._synthesise_in_chunks(filtered, task_table)
                last_exc = e
                if attempt == 0:
                    logger.warning(
                        "Synthesiser: LLM call failed (attempt %d), retrying: %s",
                        attempt,
                        e,
                    )
        logger.error(
            "Synthesiser: LLM call failed after retry, raising for failure marker: %s",
            last_exc,
        )
        raise last_exc  # type: ignore[misc]

    def _synthesise_in_chunks(
        self, filtered: list[TranscriptEntry], task_table: str
    ) -> list[SynthesisNote]:
        """Split pre-filtered entries into char-budget chunks and synthesise each."""
        chunks: list[list[TranscriptEntry]] = []
        cur: list[TranscriptEntry] = []
        cur_len = 0
        for ent in filtered:
            entry_len = len(ent.content)
            if cur and (cur_len + entry_len) > CHUNK_CHAR_LIMIT:
                chunks.append(cur)
                cur = [ent]
                cur_len = entry_len
            else:
                cur.append(ent)
                cur_len += entry_len
        if cur:
            chunks.append(cur)
        notes_data: list[SynthesisNote] = []
        for chunk in chunks:
            try:
                nd = llm_complete(
                    self._backend["model"],
                    [
                        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": self._format_prompt(chunk, task_table),
                        },
                    ],
                    self._backend.get("base_url"),
                    self._backend.get("api_key"),
                )
                notes_data.extend(nd)
            except Exception as ex:
                logger.warning("Synthesiser: chunk LLM call failed: %s", ex)
        return notes_data

    def _filter_for_synthesis(
        self, entries: list[TranscriptEntry]
    ) -> list[TranscriptEntry]:
        """Drop low-signal entries and truncate content per role."""
        kept: list[TranscriptEntry] = []
        call_by_id: dict[str, str | None] = {}
        for entry in entries:
            if entry.role == "tool_call":
                if entry.tool_use_id:
                    call_by_id[entry.tool_use_id] = entry.tool_name
                kept.append(
                    entry.model_copy(
                        update={
                            "content": entry.content[: ROLE_CHAR_LIMITS["tool_call"]]
                        }
                    )
                )
            elif entry.role == "tool_result":
                call_name = (
                    call_by_id.pop(entry.tool_use_id, None)
                    if entry.tool_use_id
                    else None
                )
                if call_name not in KEEP_RESULT_TOOLS:
                    continue
                kept.append(
                    entry.model_copy(
                        update={
                            "content": entry.content[: ROLE_CHAR_LIMITS["tool_result"]]
                        }
                    )
                )
            else:
                kept.append(
                    entry.model_copy(
                        update={
                            "content": entry.content[
                                : ROLE_CHAR_LIMITS.get(entry.role, 2000)
                            ]
                        }
                    )
                )
        return kept

    def _format_prompt(
        self, filtered: list[TranscriptEntry], task_table: str = ""
    ) -> str:
        """Format pre-filtered transcript entries into the LLM prompt string.

        Safety trim: if still over 15k chars (≈4k tokens), drop oldest entries.
        """
        entries = list(filtered)  # copy — safety trim must not mutate the caller's list
        total_chars = sum(len(e.content) for e in entries)
        if total_chars > 15_000:
            logger.warning(
                "_format_prompt: %d chars; trimming oldest entries", total_chars
            )
            while entries and total_chars > 15_000:
                total_chars -= len(entries.pop(0).content)

        lines = [_format_transcript(entries)]

        if task_table:
            lines.append(f"\nAvailable tasks (id<TAB>name):\n{task_table}\n\n")
        else:
            lines.append("\ntask_id must always be null — no task list available.")

        lines.append(
            "\nCRITICAL: Respond ONLY with a valid JSON array of objects. "
            "DO NOT include any text outside the JSON array. "
            "Format: "
            '[{"note_type": "investigation"|"decision"|"docs"|"learnings", '
            '"content": "string", "task_id": integer|null, "mental_model": "string"}]'
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
            # Artifact identity (v3): single anchor per attribution decision tree.
            # 1. task_id set -> use task.artifact_id
            # 2. session only -> use session.artifact_id
            artifact_id: str | None = None
            artifact_type: str | None = None
            if matched_task_id is not None:
                task_row = db.get(Task, matched_task_id)
                if task_row and task_row.artifact_id:
                    artifact_id = task_row.artifact_id
                    artifact_type = "task"
            if artifact_id is None and wizard_session.artifact_id:
                artifact_id = wizard_session.artifact_id
                artifact_type = "session"
            note = Note(
                note_type=NOTE_TYPE_MAP.get(nd.note_type, NoteType.INVESTIGATION),
                content=clean_content,
                mental_model=clean_model,
                task_id=matched_task_id,
                session_id=wizard_session.id,
                artifact_id=artifact_id,
                artifact_type=artifact_type,
            )
            self._note_repo.save(db, note)
            count += 1
        return count

    def _refresh_rolling_summaries(
        self, db: Session, wizard_session: WizardSession
    ) -> list[int]:
        """Rebuild TaskState for every task that received notes in this session."""
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
        for task_id in task_ids:
            self._task_state_repo.on_note_saved(db, task_id)
        return task_ids
