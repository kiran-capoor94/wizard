import datetime
import logging

from sqlmodel import Session, col, func, select

from ..models import Note, NoteType

logger = logging.getLogger(__name__)


class NoteRepository:
    def save(self, db: Session, note: Note) -> Note:
        db.add(note)
        db.flush()
        db.refresh(note)
        return note

    def get_by_content_hash(
        self, db: Session, task_id: int, content_hash: str
    ) -> Note | None:
        """Return the first active note on task_id matching content_hash, or None."""
        stmt = (
            select(Note)
            .where(Note.task_id == task_id)
            .where(Note.synthesis_content_hash == content_hash)
            .where(Note.status == "active")
            .limit(1)
        )
        return db.exec(stmt).first()

    def get_for_task(
        self,
        db: Session,
        task_id: int | None,
        ascending: bool = False,
        limit: int | None = None,
    ) -> list[Note]:
        if task_id is None:
            return []
        order = col(Note.created_at).asc() if ascending else col(Note.created_at).desc()
        stmt = select(Note).where(Note.task_id == task_id).order_by(order)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.exec(stmt).all())

    def get_notes_grouped_by_task(
        self, db: Session, session_id: int
    ) -> dict[int, list[Note]]:
        """Return notes for a session grouped by task_id, ordered by created_at asc."""
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(col(Note.created_at).asc())
        )
        all_notes = list(db.exec(stmt).all())
        by_task: dict[int, list[Note]] = {}
        for n in all_notes:
            if n.task_id is not None:
                by_task.setdefault(n.task_id, []).append(n)
        return by_task

    def count_investigations(self, db: Session, task_id: int) -> int:
        """Count investigation notes for a task."""
        stmt = (
            select(func.count())
            .select_from(Note)
            .where(Note.task_id == task_id)
            .where(Note.note_type == NoteType.INVESTIGATION)
        )
        return db.exec(stmt).one()

    def has_mental_model(self, db: Session, task_id: int) -> bool:
        """Check if any note for this task has a mental_model."""
        stmt = (
            select(Note)
            .where(Note.task_id == task_id)
            .where(Note.mental_model.is_not(None))  # type: ignore[union-attr]
            .limit(1)
        )
        return db.exec(stmt).first() is not None

    def list_for_session(self, db: Session, session_id: int) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(col(Note.created_at).asc())
        )
        return list(db.exec(stmt).all())

    def count_for_session(self, db: Session, session_id: int) -> int:
        return db.exec(
            select(func.count()).select_from(Note).where(Note.session_id == session_id)
        ).one()

    def get_notes_by_artifact_id(
        self,
        db: Session,
        artifact_id: str,
        ascending: bool = False,
        limit: int | None = None,
    ) -> list[Note]:
        order = col(Note.created_at).asc() if ascending else col(Note.created_at).desc()
        stmt = select(Note).where(Note.artifact_id == artifact_id).order_by(order)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(db.exec(stmt).all())

    def get_artifact_id_hashes(self, db: Session, artifact_id: str) -> set[str]:
        """Return synthesis_content_hash values for notes on this artifact.

        Used by synthesis to pre-filter exact duplicate candidates before LLM calls.
        Returns only non-null hashes.
        """
        stmt = (
            select(Note.synthesis_content_hash)
            .where(Note.artifact_id == artifact_id)
            .where(Note.synthesis_content_hash.is_not(None))  # type: ignore[union-attr]
        )
        return set(db.exec(stmt).all())

    def get_recent(self, db: Session, days: int) -> list[Note]:
        """Return active notes created in the last `days` days, newest first."""
        cutoff = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=days), datetime.time.min
        )
        stmt = (
            select(Note)
            .where(Note.created_at >= cutoff)
            .where(Note.status == "active")
            .order_by(col(Note.created_at).desc())
        )
        return list(db.exec(stmt).all())

    def count_for_sessions(self, db: Session, session_ids: list[int]) -> dict[int, int]:
        """Batch-count notes per session. Returns {session_id: count}."""
        if not session_ids:
            return {}
        stmt = (
            select(Note.session_id, func.count().label("cnt"))
            .where(col(Note.session_id).in_(session_ids))
            .group_by(col(Note.session_id))
        )
        return {row[0]: row[1] for row in db.execute(stmt).all()}


def build_rolling_summary(notes: list[Note]) -> str | None:
    """Build a rolling summary from mental_models across all task notes.

    Produces a chronological digest (newest first) of captured mental models.
    Returns None if no notes have mental_models recorded.
    """
    entries = []
    for n in sorted(notes, key=lambda x: x.created_at, reverse=True):
        if n.status not in ("active", None):
            continue
        if n.mental_model:
            dt = n.created_at.strftime("%Y-%m-%d")
            entries.append(f"[{dt} {n.note_type.value}] {n.mental_model}")
    return "\n".join(entries) if entries else None


