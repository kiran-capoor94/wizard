"""Synthesiser — synthesise agent transcripts into structured Note objects."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import litellm
import sentry_sdk
from pydantic import ValidationError
from sqlmodel import Session, col, select

from wizard.llm_adapters import complete as llm_complete
from wizard.llm_adapters import probe_backend_health
from wizard.models import Note, NoteType, Task, WizardSession
from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
from wizard.schemas import SynthesisNote, SynthesisResult
from wizard.security import SecurityService
from wizard.synthesis_prompt import filter_for_synthesis, format_prompt
from wizard.transcript import TranscriptEntry, TranscriptReader

if TYPE_CHECKING:
    from wizard.config import Settings

logger = logging.getLogger(__name__)

SYNTHESIS_SYSTEM_PROMPT = (
    "You are synthesising a coding session transcript into structured notes "
    "for a task management system. Be concise. Focus on what was accomplished, "
    "what was found, and what decisions were made. "
    "Respond directly with a JSON array — no thinking blocks, no preamble."
)

NOTE_TYPE_MAP: dict[str, NoteType] = {
    "investigation": NoteType.INVESTIGATION,
    "decision": NoteType.DECISION,
    "docs": NoteType.DOCS,
    "learnings": NoteType.LEARNINGS,
    "failure": NoteType.FAILURE,
}


class Synthesiser:
    """Synthesise agent transcripts into structured Note objects."""

    def __init__(
        self,
        reader: TranscriptReader,
        note_repo: NoteRepository,
        security: SecurityService,
        settings: Settings,
        task_state_repo: TaskStateRepository | None = None,
        t_repo: TaskRepository | None = None,
        backend: dict | None = None,
    ):
        self._reader = reader
        self._note_repo = note_repo
        self._security = security
        self._settings = settings
        self._task_state_repo = task_state_repo or TaskStateRepository()
        self._t_repo = t_repo or TaskRepository()
        self._backend = (
            backend if backend is not None else self._select_backend(settings.synthesis)
        )
        # Maximum chars per synthesis chunk. Default to 15k for extremely fast local prefill.
        self._chunk_char_limit: int = min(settings.synthesis.context_chars, 15000)

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

    def write_failure_marker(
        self, db: Session, wizard_session: WizardSession, chunk_description: str
    ) -> None:
        """Write a recoverable investigation note when synthesis fails after retry."""
        marker = Note(
            note_type=NoteType.INVESTIGATION,
            content=(
                f"Synthesis failed for session {wizard_session.id}. "
                f"{chunk_description} "
                "Content available in wizardsession.transcript_raw. "
                "Retry with: wizard capture --close --session-id "
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
                sentry_sdk.capture_exception(exc)
                logger.warning(
                    "Synthesiser: generate_notes failed after retry for session %d: %s",
                    wizard_session.id,
                    exc,
                )
                self.write_failure_marker(
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
            filtered = filter_for_synthesis(entries)
            messages = [
                {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": format_prompt(filtered, task_table)},
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
        sentry_sdk.capture_exception(last_exc)
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
            if cur and (cur_len + entry_len) > self._chunk_char_limit:
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
            # No retry here — each chunk is already a subdivision of a failed single call.
            # Raise on failure so synthesise_path can write a failure marker.
            nd = llm_complete(
                self._backend["model"],
                [
                    {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": format_prompt(chunk, task_table),
                    },
                ],
                self._backend.get("base_url"),
                self._backend.get("api_key"),
            )
            notes_data.extend(nd)
        return notes_data

    def _save_notes(
        self,
        db: Session,
        notes_data: list[SynthesisNote],
        wizard_session: WizardSession,
        valid_task_ids: set[int] | None = None,
    ) -> int:
        # Pre-load artifact_ids for all referenced tasks in one query (no N+1).
        referenced_task_ids = {
            nd.task_id
            for nd in notes_data
            if nd.task_id is not None
            and (valid_task_ids is None or nd.task_id in valid_task_ids)
        }
        task_artifact_ids: dict[int, str] = {}
        if referenced_task_ids:
            rows = db.exec(
                select(Task.id, Task.artifact_id).where(
                    col(Task.id).in_(referenced_task_ids)
                )
            ).all()
            task_artifact_ids = {tid: aid for tid, aid in rows if aid is not None}

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
            # 1. task_id set -> use task.artifact_id (pre-loaded above)
            # 2. session only -> use session.artifact_id
            if matched_task_id is not None and matched_task_id in task_artifact_ids:
                artifact_id: str | None = task_artifact_ids[matched_task_id]
                artifact_type: str | None = "task"
            elif wizard_session.artifact_id:
                artifact_id = wizard_session.artifact_id
                artifact_type = "session"
            else:
                artifact_id = None
                artifact_type = None
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
        """Rebuild TaskState for every task that received notes in this session.

        Fetches the affected task IDs in one query, then calls recompute_for_task per
        task (3 queries each: Task lookup + count query + mental_model notes). 3N queries total.
        """
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
            self._task_state_repo.recompute_for_task(db, task_id)
        return task_ids
