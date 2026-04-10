from typing import Optional
from sqlmodel import Session, select, or_


class NoteRepository:
    def save(self, db: Session, note) -> None:
        db.add(note)
        db.commit()
        db.refresh(note)
        return note

    def get_for_task(
        self,
        db: Session,
        task_id: Optional[int],
        source_id: Optional[str],
    ) -> list:
        from .models import Note
        
        conditions = []
        if task_id is not None:
            conditions.append(Note.task_id == task_id)
        if source_id is not None:
            conditions.append(Note.source_id == source_id)
        if not conditions:
            return []
        stmt = (
            select(Note)
            .where(or_(*conditions))
            .order_by(Note.created_at.asc())
        )
        return list(db.exec(stmt).all())

    def get_latest_for_task(
        self,
        db: Session,
        task_id: Optional[int],
        source_id: Optional[str],
    ) -> Optional[any]:
        notes = self.get_for_task(db, task_id=task_id, source_id=source_id)
        return notes[-1] if notes else None
