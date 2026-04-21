import logging

from sqlmodel import Session, select

from ..models import Meeting
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
