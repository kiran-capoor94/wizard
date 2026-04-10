import logging
from typing import Optional
from sqlmodel import Session, select

from .integrations import JiraClient, KrispClient
from .security import SecurityService

logger = logging.getLogger(__name__)

_JIRA_STATUS_MAP = {
    "to do": "todo",
    "in progress": "in_progress",
    "blocked": "blocked",
    "done": "done",
}

_JIRA_PRIORITY_MAP = {
    "highest": "high",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "lowest": "low",
}


class SyncService:
    def __init__(self, jira: JiraClient, krisp: KrispClient, security: SecurityService):
        self._jira = jira
        self._krisp = krisp
        self._security = security

    def sync_all(self, db: Session) -> None:
        for source, fn in [("jira", self._sync_jira), ("krisp", self._sync_krisp)]:
            try:
                fn(db)
            except Exception as e:
                logger.warning("Sync failed for %s: %s", source, e)

    def _sync_jira(self, db: Session) -> None:
        from .models import Task, TaskStatus, TaskPriority
        
        raw_tasks = self._jira.fetch_open_tasks()
        for raw in raw_tasks:
            scrubbed_name = self._security.scrub(raw["summary"]).clean
            existing = db.exec(select(Task).where(Task.source_id == raw["key"])).first()
            if existing:
                existing.name = scrubbed_name
                existing.priority = TaskPriority(_JIRA_PRIORITY_MAP.get(raw["priority"].lower(), "medium"))
                existing.source_url = raw.get("url")
                db.add(existing)
            else:
                task = Task(
                    name=scrubbed_name,
                    source_id=raw["key"],
                    source_type="JIRA",
                    source_url=raw.get("url"),
                    priority=TaskPriority(_JIRA_PRIORITY_MAP.get(raw["priority"].lower(), "medium")),
                    status=TaskStatus(_JIRA_STATUS_MAP.get(raw["status"].lower(), "todo")),
                )
                db.add(task)
        db.commit()

    def _sync_krisp(self, db: Session) -> None:
        from .models import Meeting
        
        raw_meetings = self._krisp.fetch_recent_meetings()
        for raw in raw_meetings:
            scrubbed_title = self._security.scrub(raw.get("title", "")).clean
            scrubbed_content = self._security.scrub(raw.get("transcript", "")).clean
            existing = db.exec(select(Meeting).where(Meeting.source_id == raw["id"])).first()
            if existing:
                existing.title = scrubbed_title
                existing.content = scrubbed_content
                existing.source_url = raw.get("url")
                db.add(existing)
            else:
                meeting = Meeting(
                    title=scrubbed_title,
                    content=scrubbed_content,
                    source_id=raw["id"],
                    source_type="KRISP",
                    source_url=raw.get("url"),
                )
                db.add(meeting)
        db.commit()
