from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlmodel import Session, select

from .integrations import JiraClient, NotionClient
from .schemas import SourceSyncStatus, WriteBackStatus
from .security import SecurityService

if TYPE_CHECKING:
    from .models import Meeting, Task, WizardSession

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

_NOTION_STATUS_MAP = {
    "not started": "todo",
    "in progress": "in_progress",
    "blocked": "blocked",
    "done": "done",
    "archive": "archived",
}

# 1:1 mapping — Notion uses capitalised labels that map directly to TaskPriority values.
# Kept separate from _JIRA_PRIORITY_MAP to avoid accidental cross-contamination.
_NOTION_PRIORITY_MAP = {
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_LOCAL_TO_NOTION_STATUS = {
    "todo": "Not started",
    "in_progress": "In progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Archive",
}

_LOCAL_TO_JIRA_STATUS = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "blocked": "Blocked",
    "done": "Done",
    "archived": "Done",
}

_NOTION_MEETING_CATEGORY_MAP = {
    "standup": "standup",
    "planning": "planning",
    "retro": "retro",
    "presentation": "general",
    "customer call": "general",
}

# None = no Notion page created for these categories.
# ONE_ON_ONE and GENERAL are local-only; Notion write-back is silently skipped.
_LOCAL_TO_NOTION_MEETING_CATEGORY = {
    "standup": "Standup",
    "planning": "Planning",
    "retro": "Retro",
    "one_on_one": None,
    "general": None,
}


class SyncService:
    def __init__(self, jira: JiraClient, notion: NotionClient, security: SecurityService):
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
        from .models import Task, TaskStatus, TaskPriority

        raw_tasks = self._jira.fetch_open_tasks()
        for raw in raw_tasks:
            scrubbed_name = self._security.scrub(raw.summary).clean
            existing = db.exec(select(Task).where(Task.source_id == raw.key)).first()
            if existing:
                existing.name = scrubbed_name
                existing.priority = TaskPriority(
                    _JIRA_PRIORITY_MAP.get(raw.priority.lower(), "medium")
                )
                existing.source_url = raw.url
                db.add(existing)
            else:
                task = Task(
                    name=scrubbed_name,
                    source_id=raw.key,
                    source_type="JIRA",
                    source_url=raw.url,
                    priority=TaskPriority(
                        _JIRA_PRIORITY_MAP.get(raw.priority.lower(), "medium")
                    ),
                    status=TaskStatus(
                        _JIRA_STATUS_MAP.get(raw.status.lower(), "todo")
                    ),
                )
                db.add(task)
        db.commit()

    def _sync_notion_tasks(self, db: Session) -> None:
        from .models import Task, TaskStatus, TaskPriority
        import datetime as _dt

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
            priority = TaskPriority(
                _NOTION_PRIORITY_MAP.get(raw_priority.lower(), "medium")
            )

            # Parse due_date from ISO string if present
            due_date = None
            raw_due = raw.due_date
            if raw_due:
                try:
                    due_date = _dt.datetime.fromisoformat(raw_due)
                except (ValueError, TypeError):
                    pass

            if existing:
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
                status_value = _NOTION_STATUS_MAP.get(raw_status.lower(), "todo")
                task = Task(
                    name=scrubbed_name,
                    notion_id=notion_id,
                    source_id=jira_key,
                    source_type="NOTION" if not jira_key else "JIRA",
                    source_url=jira_url,
                    priority=priority,
                    due_date=due_date,
                    status=TaskStatus(status_value),
                )
                db.add(task)
        db.commit()

    def _sync_notion_meetings(self, db: Session) -> None:
        from .models import Meeting, MeetingCategory

        raw_meetings = self._notion.fetch_meetings()
        for raw in raw_meetings:
            title = raw.title or ""
            scrubbed_title = self._security.scrub(title).clean
            notion_id = raw.notion_id
            krisp_url = raw.krisp_url

            # Extract krisp_id from krisp_url last path segment
            krisp_id = None
            if krisp_url:
                try:
                    segment = krisp_url.rstrip("/").split("/")[-1].split("?")[0].strip()
                    if segment:
                        krisp_id = segment
                except Exception:
                    pass

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

            # Map category — first match wins, fallback GENERAL
            raw_categories = raw.categories or []
            category = MeetingCategory.GENERAL
            for raw_cat in raw_categories:
                mapped = _NOTION_MEETING_CATEGORY_MAP.get(raw_cat.lower())
                if mapped:
                    category = MeetingCategory(mapped)
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
                    summary=self._security.scrub(raw_summary).clean if raw_summary else None,
                    notion_id=notion_id,
                    source_id=krisp_id,
                    source_type="KRISP" if krisp_id else None,
                    source_url=krisp_url,
                    category=category,
                )
                db.add(meeting)
        db.commit()


class WriteBackService:
    def __init__(self, jira: JiraClient, notion: NotionClient):
        self._jira = jira
        self._notion = notion

    def push_task_status(self, task: Task) -> WriteBackStatus:
        if not task.source_id:
            return WriteBackStatus(ok=False, error="Task has no Jira source_id")
        status_key = task.status.value if hasattr(task.status, "value") else task.status
        jira_status = _LOCAL_TO_JIRA_STATUS.get(status_key)
        if not jira_status:
            return WriteBackStatus(ok=False, error=f"No Jira status mapping for '{status_key}'")
        try:
            ok = self._jira.update_task_status(task.source_id, jira_status)
            if ok:
                return WriteBackStatus(ok=True)
            return WriteBackStatus(ok=False, error="Jira API call failed")
        except Exception as e:
            logger.warning("WriteBack push_task_status (Jira) failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_task_status_to_notion(self, task: Task) -> WriteBackStatus:
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        status_key = task.status.value if hasattr(task.status, "value") else task.status
        notion_status = _LOCAL_TO_NOTION_STATUS.get(status_key)
        if not notion_status:
            return WriteBackStatus(ok=False, error=f"No Notion status mapping for '{status_key}'")
        try:
            ok = self._notion.update_task_status(task.notion_id, notion_status)
            if ok:
                return WriteBackStatus(ok=True)
            return WriteBackStatus(ok=False, error="Notion API call failed")
        except Exception as e:
            logger.warning("WriteBack push_task_status (Notion) failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_task_to_notion(self, task: Task) -> WriteBackStatus:
        """Create or update task in Notion. Returns page_id in WriteBackStatus on success."""
        if task.notion_id:
            result = self.push_task_status_to_notion(task)
            return WriteBackStatus(
                ok=result.ok,
                error=result.error,
                page_id=task.notion_id if result.ok else None,
            )
        notion_status = _LOCAL_TO_NOTION_STATUS.get(
            task.status.value if hasattr(task.status, "value") else task.status,
            "Not started",
        )
        priority = task.priority.value if hasattr(task.priority, "value") else task.priority
        priority_label = priority.capitalize() if priority else None
        try:
            page_id = self._notion.create_task_page(
                name=task.name,
                status=notion_status,
                priority=priority_label,
                jira_url=task.source_url if task.source_type == "JIRA" else None,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(ok=False, error="Notion create_task_page returned no page ID")
        except Exception as e:
            logger.warning("WriteBack push_task_to_notion failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_meeting_to_notion(self, meeting: Meeting) -> WriteBackStatus:
        """Create or update meeting in Notion. Returns page_id in WriteBackStatus on success."""
        if meeting.notion_id:
            if meeting.summary:
                try:
                    ok = self._notion.update_meeting_summary(meeting.notion_id, meeting.summary)
                    if ok:
                        return WriteBackStatus(ok=True, page_id=meeting.notion_id)
                    return WriteBackStatus(ok=False, error="Notion update_meeting_summary failed")
                except Exception as e:
                    logger.warning("WriteBack push_meeting_to_notion (update) failed: %s", e)
                    return WriteBackStatus(ok=False, error=str(e))
            return WriteBackStatus(ok=True, page_id=meeting.notion_id)
        category_value = meeting.category.value if hasattr(meeting.category, "value") else meeting.category
        notion_category = _LOCAL_TO_NOTION_MEETING_CATEGORY.get(category_value)
        if not notion_category:
            return WriteBackStatus(
                ok=False,
                error=f"No Notion category mapping for '{category_value}'",
            )
        try:
            page_id = self._notion.create_meeting_page(
                title=meeting.title,
                category=notion_category,
                krisp_url=meeting.source_url if meeting.source_type == "KRISP" else None,
                summary=meeting.summary,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(ok=False, error="Notion create_meeting_page returned no page ID")
        except Exception as e:
            logger.warning("WriteBack push_meeting_to_notion (create) failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_meeting_summary(self, meeting: Meeting) -> WriteBackStatus:
        if not meeting.notion_id:
            return WriteBackStatus(ok=False, error="Meeting has no notion_id")
        if not meeting.summary:
            return WriteBackStatus(ok=False, error="Meeting has no summary")
        try:
            ok = self._notion.update_meeting_summary(
                meeting.notion_id, meeting.summary
            )
            if ok:
                return WriteBackStatus(ok=True)
            return WriteBackStatus(ok=False, error="Notion update_meeting_summary failed")
        except Exception as e:
            logger.warning("WriteBack push_meeting_summary failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))

    def push_session_summary(self, session: WizardSession) -> WriteBackStatus:
        if not session.summary:
            return WriteBackStatus(ok=False, error="Session has no summary")
        try:
            ok = self._notion.update_daily_page(session.summary)
            if ok:
                return WriteBackStatus(ok=True)
            return WriteBackStatus(ok=False, error="Notion update_daily_page failed")
        except Exception as e:
            logger.warning("WriteBack push_session_summary failed: %s", e)
            return WriteBackStatus(ok=False, error=str(e))
