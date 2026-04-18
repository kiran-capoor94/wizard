import contextlib
import datetime
import logging
from collections.abc import Callable
from typing import Any

import httpx
from fastmcp import Context
from notion_client.errors import APIResponseError
from sqlmodel import Session, select

from .integrations import JiraClient, NotionClient, extract_krisp_id
from .mappers import MeetingCategoryMapper, PriorityMapper, StatusMapper
from .models import Meeting, MeetingCategory, Note, NoteType, Task, WizardSession
from .repositories import NoteRepository, TaskStateRepository
from .schemas import (
    AutoCloseSummary,
    ClosedSessionSummary,
    SessionState,
    SourceSyncStatus,
    WriteBackStatus,
)
from .security import SecurityService

logger = logging.getLogger(__name__)


class SyncService:
    def __init__(
        self,
        jira: JiraClient,
        notion: NotionClient,
        security: SecurityService,
        task_state_repo: TaskStateRepository | None = None,
    ):
        self._jira = jira
        self._notion = notion
        self._security = security
        self._task_state_repo = task_state_repo or TaskStateRepository()

    def sync_all(self, db: Session) -> list[SourceSyncStatus]:
        results: list[SourceSyncStatus] = []
        source_client = {
            "jira": self._jira,
            "notion_tasks": self._notion,
            "notion_meetings": self._notion,
        }
        for source, fn in [
            ("jira", self.sync_jira),
            ("notion_tasks", self.sync_notion_tasks),
            ("notion_meetings", self.sync_notion_meetings),
        ]:
            if not source_client[source].is_configured:
                results.append(
                    SourceSyncStatus(
                        source=source,
                        ok=True,
                        skipped=True,
                        error="not configured",
                    )
                )
                continue
            try:
                fn(db)
                results.append(SourceSyncStatus(source=source, ok=True))
            except (APIResponseError, httpx.HTTPError, KeyError, TypeError) as e:
                err_msg = self._security.scrub(str(e)).clean
                logger.warning("Sync failed for %s: %s", source, err_msg)
                results.append(SourceSyncStatus(source=source, ok=False, error=err_msg))
        return results

    def sync_jira(self, db: Session) -> None:
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
                db.refresh(task)
                self._task_state_repo.create_for_task(db, task)
        db.flush()

    def sync_notion_tasks(self, db: Session) -> None:
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
                existing = db.exec(select(Task).where(Task.source_id == jira_key)).first()
            if existing is None and notion_id:
                existing = db.exec(select(Task).where(Task.notion_id == notion_id)).first()

            raw_priority = raw.priority or "Medium"
            priority = PriorityMapper.notion_to_local(raw_priority)

            # Parse due_date from ISO string if present
            due_date = None
            raw_due = raw.due_date
            if raw_due:
                with contextlib.suppress(ValueError, TypeError):
                    due_date = datetime.datetime.fromisoformat(raw_due)

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
                db.refresh(task)
                self._task_state_repo.create_for_task(db, task)
        db.flush()

    def sync_notion_meetings(self, db: Session) -> None:
        raw_meetings = self._notion.fetch_meetings()
        for raw in raw_meetings:
            title = raw.title or ""
            scrubbed_title = self._security.scrub(title).clean
            notion_id = raw.notion_id
            krisp_url = raw.krisp_url

            krisp_id = extract_krisp_id(krisp_url)

            # Dedup: krisp_id → source_id, then notion_id
            existing = None
            if krisp_id:
                existing = db.exec(select(Meeting).where(Meeting.source_id == krisp_id)).first()
            if existing is None and notion_id:
                existing = db.exec(select(Meeting).where(Meeting.notion_id == notion_id)).first()

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
                    summary=(self._security.scrub(raw_summary).clean if raw_summary else None),
                    notion_id=notion_id,
                    source_id=krisp_id,
                    source_type="KRISP" if krisp_id else None,
                    source_url=krisp_url,
                    category=category,
                )
                db.add(meeting)
        db.flush()


class WriteBackService:
    def __init__(
        self,
        jira: JiraClient,
        notion: NotionClient,
        security: SecurityService | None = None,
    ):
        self._jira = jira
        self._notion = notion
        self._security = security or SecurityService()

    def _call(self, fn: Callable[[], Any], error_label: str, **status_kwargs) -> WriteBackStatus:
        try:
            result = fn()
            if result:
                return WriteBackStatus(ok=True, **status_kwargs)
            return WriteBackStatus(ok=False, error=f"{error_label} failed")
        except Exception as e:
            err_msg = self._security.scrub(str(e)).clean
            logger.warning("%s failed: %s", error_label, err_msg)
            return WriteBackStatus(ok=False, error=err_msg)

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

    def push_task_due_date(self, task: Task) -> WriteBackStatus:
        """Push due_date to Notion if task has notion_id."""
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        if not task.due_date:
            return WriteBackStatus(ok=False, error="Task has no due_date")
        notion_id = task.notion_id
        due_date_iso = task.due_date.isoformat()
        return self._call(
            lambda: self._notion.update_task_due_date(notion_id, due_date_iso),
            "WriteBack push_task_due_date",
        )

    def push_task_priority(self, task: Task) -> WriteBackStatus:
        """Push priority to Notion if task has notion_id."""
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        notion_id = task.notion_id
        priority_label = PriorityMapper.local_to_notion(task.priority)
        return self._call(
            lambda: self._notion.update_task_priority(notion_id, priority_label),
            "WriteBack push_task_priority",
        )

    def append_task_outcome(self, task: Task, summary: str) -> WriteBackStatus:
        """Append a plain-text outcome paragraph to the task's Notion page."""
        if not task.notion_id:
            return WriteBackStatus(ok=False, error="Task has no notion_id")
        notion_id = task.notion_id
        return self._call(
            lambda: self._notion.append_paragraph_to_page(notion_id, summary),
            "WriteBack append_task_outcome",
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
            return WriteBackStatus(ok=False, error="Notion create_task_page returned no page ID")
        except (APIResponseError, httpx.HTTPError, KeyError, TypeError) as e:
            err_msg = self._security.scrub(str(e)).clean
            logger.warning("WriteBack push_task_to_notion failed: %s", err_msg)
            return WriteBackStatus(ok=False, error=err_msg)

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
                krisp_url=meeting.source_url,
                summary=meeting.summary,
            )
            if page_id:
                return WriteBackStatus(ok=True, page_id=page_id)
            return WriteBackStatus(ok=False, error="Notion create_meeting_page returned no page ID")
        except (APIResponseError, httpx.HTTPError, KeyError, TypeError) as e:
            err_msg = self._security.scrub(str(e)).clean
            logger.warning("WriteBack push_meeting_to_notion (create) failed: %s", err_msg)
            return WriteBackStatus(ok=False, error=err_msg)

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
        if not session.daily_page_id:
            return WriteBackStatus(ok=False, error="Session has no daily_page_id")
        if not session.summary:
            return WriteBackStatus(ok=False, error="Session has no summary")
        page_id = session.daily_page_id
        summary = session.summary
        return self._call(
            lambda: self._notion.update_daily_page(page_id, summary),
            "WriteBack push_session_summary",
        )


class SessionCloser:
    """Auto-closes abandoned sessions with a three-tier fallback chain:
    1. LLM sampling via ctx.sample()
    2. Synthetic summary from DB data
    3. Minimal warn fallback
    """

    def __init__(
        self,
        note_repo: NoteRepository | None = None,
        security: SecurityService | None = None,
    ):
        self._note_repo = note_repo or NoteRepository()
        self._security = security or SecurityService()

    async def close_abandoned(
        self, db: Session, ctx: Context, current_session_id: int,
    ) -> list[ClosedSessionSummary]:
        abandoned = self._find_abandoned(db, current_session_id)
        return [await self._close_one(db, ctx, s) for s in abandoned]

    def _find_abandoned(self, db: Session, current_session_id: int) -> list[WizardSession]:
        stmt = (
            select(WizardSession)
            .where(
                WizardSession.summary == None,  # noqa: E711
                WizardSession.closed_by == None,  # noqa: E711
                WizardSession.id != current_session_id,
            )
            .order_by(WizardSession.created_at.desc())  # type: ignore[union-attr]
        )
        return list(db.exec(stmt).all())

    async def _close_one(
        self, db: Session, ctx: Context, session: WizardSession,
    ) -> ClosedSessionSummary:
        session_id = session.id
        assert session_id is not None
        notes = self._get_session_notes(db, session_id)
        task_ids = list({n.task_id for n in notes if n.task_id is not None})
        note_count = len(notes)
        state = SessionState(
            intent="", working_set=task_ids, state_delta="",
            open_loops=[], next_actions=[], closure_status="interrupted",
        )
        # Tier 1: try LLM sampling
        summary_text, closed_via = await self._try_sampling(ctx, notes)
        # Tier 2: synthetic fallback
        if summary_text is None:
            summary_text, closed_via = self._synthetic_summary(session, notes, task_ids)
        clean_summary = self._security.scrub(summary_text).clean
        session.summary = clean_summary
        session.session_state = state.model_dump_json()
        session.closed_by = "auto"
        db.add(session)
        db.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY, content=clean_summary,
            session_id=session_id,
        )
        self._note_repo.save(db, note)
        return ClosedSessionSummary(
            session_id=session_id, summary=clean_summary,
            closed_via=closed_via, task_ids=task_ids, note_count=note_count,
        )

    def _get_session_notes(self, db: Session, session_id: int) -> list[Note]:
        stmt = (
            select(Note)
            .where(Note.session_id == session_id)
            .order_by(Note.created_at.asc())  # type: ignore[union-attr]
        )
        return list(db.exec(stmt).all())

    async def _try_sampling(
        self, ctx: Context, notes: list[Note]
    ) -> tuple[str | None, str]:
        if not notes:
            return None, ""
        prompt = self._build_sampling_prompt(notes)
        try:
            result = await ctx.sample(
                messages=prompt,
                system_prompt=(
                    "You are summarising an abandoned coding session. "
                    "Be concise. Focus on what was accomplished and what remains."
                ),
                result_type=AutoCloseSummary,
                max_tokens=500,
                temperature=0.3,
            )
            auto_summary: AutoCloseSummary = result.result
            return auto_summary.summary, "sampling"
        except Exception as e:
            logger.warning("SessionCloser sampling failed: %s", e)
            return None, ""

    def _build_sampling_prompt(self, notes: list[Note]) -> str:
        lines = ["The following notes were saved during an abandoned session:\n"]
        for n in notes:
            lines.append(f"- [{n.note_type.value}] {n.content[:300]}")
        lines.append(
            "\nSummarise what was accomplished, the likely intent, "
            "and any open loops."
        )
        return "\n".join(lines)

    def _synthetic_summary(
        self,
        session: WizardSession,
        notes: list[Note],
        task_ids: list[int],
    ) -> tuple[str, str]:
        note_count = len(notes)
        task_count = len(task_ids)
        last_activity = session.last_active_at or session.updated_at
        return (
            f"Auto-closed: {note_count} note(s) across {task_count} task(s). "
            f"Last activity: {last_activity}."
        ), "synthetic"
