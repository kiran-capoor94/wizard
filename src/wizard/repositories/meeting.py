import logging

from sqlmodel import Session, col, select

from ..models import Meeting, MeetingTasks
from ..schemas import MeetingContext

logger = logging.getLogger(__name__)


class MeetingRepository:
    def get_by_source_id(self, db: Session, source_id: str) -> Meeting | None:
        return db.exec(select(Meeting).where(Meeting.source_id == source_id)).first()

    def get_by_id(self, db: Session, meeting_id: int) -> Meeting:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            logger.warning("Meeting %d not found", meeting_id)
            raise ValueError(f"Meeting {meeting_id} not found")
        return meeting

    def get_unsummarised_contexts(self, db: Session) -> list[MeetingContext]:
        stmt = select(Meeting).where(Meeting.summary == None)  # noqa: E711
        results: list[MeetingContext] = []
        for m in db.exec(stmt).all():
            if m.id is None:
                raise ValueError(f"Meeting row returned without an id: {m}")
            results.append(
                MeetingContext(
                    id=m.id,
                    title=m.title,
                    category=m.category,
                    created_at=m.created_at,
                    already_summarised=False,
                    source_url=m.source_url,
                    source_type=m.source_type,
                )
            )
        return results

    def save(self, db: Session, meeting: Meeting) -> Meeting:
        """Persist a Meeting to the database."""
        db.add(meeting)
        db.flush()
        db.refresh(meeting)
        return meeting

    def link_tasks(self, db: Session, meeting_id: int, task_ids: list[int]) -> None:
        """Link multiple tasks to a meeting, avoiding duplicates."""
        if not task_ids:
            return

        existing_links = {
            mt.task_id
            for mt in db.exec(
                select(MeetingTasks).where(
                    MeetingTasks.meeting_id == meeting_id,
                    col(MeetingTasks.task_id).in_(task_ids),
                )
            ).all()
        }

        for tid in task_ids:
            if tid not in existing_links:
                db.add(MeetingTasks(meeting_id=meeting_id, task_id=tid))
        db.flush()
