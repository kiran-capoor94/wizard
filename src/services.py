import datetime
import logging
from collections.abc import Callable
from typing import Any

from sqlmodel import Session, select

from .integrations import JiraClient, NotionClient, _extract_krisp_id
from .mappers import MeetingCategoryMapper, PriorityMapper, StatusMapper
from .models import Meeting, MeetingCategory, Task, WizardSession
from .schemas import SourceSyncStatus, WriteBackStatus
from .security import SecurityService

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(
        self, jira: JiraClient, notion: NotionClient, security: SecurityService
    ):
        self._jira = jira
        self._notion = notion
        self._security = security

    def sync_all(self, db: Session) -> list[SourceSyncStatus]:
        results: list[SourceSyncStatus] = []
        for source, fn in [
            ("jira", self._sync_jira),
            ("notion_tasks", self._sync_notion_tasks),
            ("notion_meetings", self._sync_notion_meetings),
        ]:
            try:
                fn(db)
                results.append(SourceSyncStatus(source=source, ok=True))
            except Exception as e:
                logger.warning("Sync failed for %s: %s", source, e)
                results.append(SourceSyncStatus(source=source, ok=False, error=str(e)))
        return results

    def _sync_jira(self, db: Session) -> None:
        raw_tasks = self._jira.fetch_open_tasks()
        for raw in raw_tasks:
            scrubbed_name = self._security.scrub(raw.summary).clean
            existing = db.exec(select(Task).where(Task.source_id == raw.key)).first()
            if existing:
                # Upsert rule: external source wins on name/priority/url.
                # Status is preserved — local status reflects user actions
                # (e.g. manually marking BLOCKED) that Jira may not know about.
                existing.name = scrubbed_name
                existing.priority = PriorityMapper.jira_to_local(raw.priority)
                existing.source_url = raw.url
                db.add(existing)
            else:
                task = Task(
                    name=scrubbed_name,
                    source_id=raw.key,
                    source_type="JIRA",
                    source_url=raw.url,
                    priority=PriorityMapper.jira_to_local(raw.priority),
                    status=StatusMapper.jira_to_local(raw.status),
                )
                db.add(task)
        db.flush()

    def _sync_notion_tasks(self, db: Session) -> None:
        raw_tasks = self._notion.fetch_tasks()
        for raw in raw_tasks:
            name = raw.name or ""
            scrubbed_name = self._security.scrub(name).clean
            jira_key = raw.jira_key
            jira_url = raw.jira_url
            notion_id = raw.notion_id

            # Dedup: jira_key → source_id lookup first, then notion_id
            existing = None
            if jira_key:
                existing = db.exec(
                    select(Task).where(Task.source_id == jira_key)
                ).first()
            if existing is None and notion_id:
                existing = db.exec(
                    select(Task).where(Task.notion_id == notion_id)
                ).first()

            raw_priority = raw.priority or "Medium"
            priority = PriorityMapper.notion_to_local(raw_priority)

            # Parse due_date from ISO string if present
            due_date = None
            raw_due = raw.due_date
            if raw_due:
                try:
                    due_date = datetime.datetime.fromisoformat(raw_due)
                except (ValueError, TypeError):
                    pass

            if existing:
                # Upsert rule: same as Jira sync — external wins on name/priority/due_date,
                # local status preserved. IDs are set-once (don't overwrite existing links).
                existing.name = scrubbed_name
                existing.priority = priority
                existing.due_date = due_date
                if jira_url and not existing.source_url:
                    existing.source_url = jira_url
                if not existing.notion_id and notion_id:
                    existing.notion_id = notion_id
                if not existing.source_id and jira_key:
                    existing.source_id = jira_key
                db.add(existing)
            else:
                raw_status = raw.status or "not started"
                task = Task(
                    name=scrubbed_name,
                    notion_id=notion_id,
                    source_id=jira_key,
                    source_type="NOTION" if not jira_key else "JIRA",
                    source_url=jira_url,
                    priority=priority,
                    due_date=due_date,
                    status=StatusMapper.notion_to_local(raw_status),
                )
                db.add(task)
        db.flush()

    def _sync_notion_meetings(self, db: Session) -> None:
        raw_meetings = self._notion.fetch_meetings()
        for raw in raw_meetings:
            title = raw.title or ""
            scrubbed_title = self._security.scrub(title).clean
            notion_id = raw.notion_id
            krisp_url = raw.krisp_url

            krisp_id = _extract_krisp_id(krisp_url)

            # Dedup: krisp_id → source_id, then notion_id
            existing = None
            if krisp_id:
                existing = db.exec(
                    select(Meeting).where(Meeting.source_id == krisp_id)
                ).first()
            if existing is None and notion_id:
                existing = db.exec(
                    select(Meeting).where(Meeting.notion_id == notion_id)
                ).first()

            # Map category — first non-GENERAL match wins, fallback GENERAL
            raw_categories = raw.categories or []
            category = MeetingCategory.GENERAL
            for raw_cat in raw_categories:
                category = MeetingCategoryMapper.notion_to_local(raw_cat)
                if category != MeetingCategory.GENERAL:
                    break

            if existing:
                existing.title = scrubbed_title
                existing.category = category
                if not existing.notion_id and notion_id:
                    existing.notion_id = notion_id
                if krisp_id and not existing.source_id:
                    existing.source_id = krisp_id
                if krisp_url and not existing.source_url:
                    existing.source_url = krisp_url
                db.add(existing)
            else:
                raw_summary = raw.summary
                meeting = Meeting(
                    title=scrubbed_title,
                    content="",
                    summary=(
                        self._security.scrub(raw_summary).clean if raw_summary else None
                    ),
                    notion_id=notion_id,
                    source_id=krisp_id,
                    source_type="KRISP" if krisp_id else None,
                    source_url=krisp_url,
                    category=category,
                )
                db.add(meeting)
        db.flush()


class WriteBackService:
    def __init__(self, jira: JiraClient, notion: NotionClient):
        self._jira = jira
        self._notion = notion

    def _call(self, fn: Callable[[], Any], error_label: str, **status_kwargs) -> WriteBackStatus:
        try:
            result = fn()
            if result:
                return WriteBackStatus(ok=True, **status_kwargs)
            return WriteBackStatus(ok=False, error=f"{error_label} failed")
        except Exception as e:
            logger.warning("%s failed: %s", error_label, e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_task_status(self, task: Task) -> WriteBackStatus:
        if not task.source_id:
            return WriteBackStatus(ok=False, error="Task has no Jira source_id")
        source_id = task.source_id
        jira_status = StatusMapper.local_to_jira(task.status)
        return self._call(
            lambda: self._jira.update_task_status(source_id, jira_status),
            "WriteBack push_task_status (Jira)",
        )

    def push_task_status_to_notion(self, task: Task) -> WriteBackStatus:
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        notion_id = task.notion_id
        notion_status = StatusMapper.local_to_notion(task.status)
        return self._call(
            lambda: self._notion.update_task_status(notion_id, notion_status),
            "WriteBack push_task_status (Notion)",
        )

    def push_task_to_notion(self, task: Task) -> WriteBackStatus:
        """Create or update task in Notion. Returns page_id in WriteBackStatus on success."""
        if task.notion_id:
            result = self.push_task_status_to_notion(task)
            return WriteBackStatus(
                ok=result.ok,
                error=result.error,
                page_id=task.notion_id if result.ok else None,
            )
        notion_status = StatusMapper.local_to_notion(task.status)
        priority_label = PriorityMapper.local_to_notion(task.priority)
        try:
            page_id = self._notion.create_task_page(
                name=task.name,
                status=notion_status,
                priority=priority_label,
                jira_url=task.source_url if task.source_type == "JIRA" else None,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(
                ok=False, error="Notion create_task_page returned no page ID"
            )
        except Exception as e:
            logger.warning("WriteBack push_task_to_notion failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_meeting_to_notion(self, meeting: Meeting) -> WriteBackStatus:
        """Create or update meeting in Notion. Returns page_id in WriteBackStatus on success."""
        if meeting.notion_id:
            if not meeting.summary:
                return WriteBackStatus(ok=True, page_id=meeting.notion_id)
            notion_id = meeting.notion_id
            summary = meeting.summary
            return self._call(
                lambda: self._notion.update_meeting_summary(notion_id, summary),
                "WriteBack push_meeting_to_notion (update)",
                page_id=notion_id,
            )
        notion_category = MeetingCategoryMapper.local_to_notion(meeting.category)
        if not notion_category:
            return WriteBackStatus(
                ok=False,
                error=f"No Notion category mapping for '{meeting.category.value}'",
            )
        try:
            page_id = self._notion.create_meeting_page(
                title=meeting.title,
                category=notion_category,
                krisp_url=(
                    meeting.source_url if meeting.source_type == "KRISP" else None
                ),
                summary=meeting.summary,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(
                ok=False, error="Notion create_meeting_page returned no page ID"
            )
        except Exception as e:
            logger.warning("WriteBack push_meeting_to_notion (create) failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_meeting_summary(self, meeting: Meeting) -> WriteBackStatus:
        if not meeting.notion_id:
            return WriteBackStatus(ok=False, error="Meeting has no notion_id")
        if not meeting.summary:
            return WriteBackStatus(ok=False, error="Meeting has no summary")
        notion_id = meeting.notion_id
        summary = meeting.summary
        return self._call(
            lambda: self._notion.update_meeting_summary(notion_id, summary),
            "WriteBack push_meeting_summary",
        )

    def push_session_summary(self, session: WizardSession) -> WriteBackStatus:
        if not session.summary:
            return WriteBackStatus(ok=False, error="Session has no summary")
        summary = session.summary
        return self._call(
            lambda: self._notion.update_daily_page(summary),
            "WriteBack push_session_summary",
        )
