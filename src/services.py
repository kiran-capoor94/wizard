import logging
from sqlmodel import Session, select

from .integrations import JiraClient, KrispClient, NotionClient
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
                existing.priority = TaskPriority(
                    _JIRA_PRIORITY_MAP.get(raw["priority"].lower(), "medium")
                )
                existing.source_url = raw.get("url")
                db.add(existing)
            else:
                task = Task(
                    name=scrubbed_name,
                    source_id=raw["key"],
                    source_type="JIRA",
                    source_url=raw.get("url"),
                    priority=TaskPriority(
                        _JIRA_PRIORITY_MAP.get(raw["priority"].lower(), "medium")
                    ),
                    status=TaskStatus(
                        _JIRA_STATUS_MAP.get(raw["status"].lower(), "todo")
                    ),
                )
                db.add(task)
        db.commit()

    def _sync_krisp(self, db: Session) -> None:
        from .models import Meeting

        raw_meetings = self._krisp.fetch_recent_meetings()
        for raw in raw_meetings:
            scrubbed_title = self._security.scrub(raw.get("title", "")).clean
            scrubbed_content = self._security.scrub(raw.get("transcript", "")).clean
            existing = db.exec(
                select(Meeting).where(Meeting.source_id == raw["id"])
            ).first()
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


class WriteBackService:
    def __init__(self, jira: JiraClient, notion: NotionClient):
        self._jira = jira
        self._notion = notion

    def push_task_status(self, task) -> bool:
        if not task.source_id:
            return False
        try:
            return self._jira.update_task_status(task.source_id, task.status)
        except Exception as e:
            logger.warning("WriteBack push_task_status failed: %s", e)
            return False

    def push_meeting_summary(self, meeting) -> bool:
        if not meeting.notion_id or not meeting.summary:
            return False
        try:
            return self._notion.update_page_property(
                meeting.notion_id, "Summary", meeting.summary
            )
        except Exception as e:
            logger.warning("WriteBack push_meeting_summary failed: %s", e)
            return False

    def push_session_summary(self, session) -> bool:
        if not session.summary:
            return False
        try:
            return self._notion.update_daily_page(session.summary)
        except Exception as e:
            logger.warning("WriteBack push_session_summary failed: %s", e)
            return False
