"""Fake implementations for behavioural testing.

Fakes implement the same public interface as real clients but store
data in memory. They are not mocks -- they have real behaviour (store,
retrieve, update), just without network I/O.
"""

import uuid

from wizard.models import Meeting, Task, WizardSession
from wizard.schemas import (
    DailyPageResult,
    JiraTaskData,
    NotionMeetingData,
    NotionTaskData,
    SourceSyncStatus,
    WriteBackStatus,
)


class FakeContext:
    """Minimal stand-in for fastmcp.Context used by tool functions."""

    def __init__(self):
        self._state: dict = {}
        self.sample_result = None
        self.sample_error: Exception | None = None

    async def get_state(self, key: str):
        return self._state.get(key)

    async def set_state(self, key: str, value):
        self._state[key] = value

    async def delete_state(self, key: str):
        self._state.pop(key, None)

    async def report_progress(self, current, total, message=""):
        pass

    async def info(self, msg: str):
        pass

    async def error(self, msg: str):
        pass

    async def elicit(self, prompt: str, response_type=None):
        raise NotImplementedError("elicit not available in tests")

    async def sample(self, messages, **kwargs):
        """Configurable fake for ctx.sample().

        Set ``self.sample_result`` to control the return value.
        Set ``self.sample_error`` to make it raise.
        """
        if self.sample_error is not None:
            raise self.sample_error
        return self.sample_result


class FakeJiraClient:
    """In-memory fake of wizard.integrations.JiraClient."""

    def __init__(self, tasks: list[JiraTaskData] | None = None):
        self.tasks: list[JiraTaskData] = tasks or []

    @property
    def is_configured(self) -> bool:
        return True

    def close(self) -> None:
        pass

    def fetch_open_tasks(self) -> list[JiraTaskData]:
        return list(self.tasks)

    def update_task_status(self, source_id: str, status: str) -> bool:
        for t in self.tasks:
            if t.key == source_id:
                idx = self.tasks.index(t)
                self.tasks[idx] = t.model_copy(update={"status": status})
                return True
        return False


class FakeNotionClient:
    """In-memory fake of wizard.integrations.NotionClient."""

    def __init__(
        self,
        tasks: list[NotionTaskData] | None = None,
        meetings: list[NotionMeetingData] | None = None,
    ):
        self.tasks: list[NotionTaskData] = tasks or []
        self.meetings: list[NotionMeetingData] = meetings or []

    @property
    def is_configured(self) -> bool:
        return True

    def fetch_tasks(self) -> list[NotionTaskData]:
        return list(self.tasks)

    def fetch_meetings(self) -> list[NotionMeetingData]:
        return list(self.meetings)

    def create_task_page(
        self,
        name: str,
        status: str,
        priority: str | None = None,
        jira_url: str | None = None,
        due_date: str | None = None,
    ) -> str:
        page_id = f"fake-notion-{uuid.uuid4().hex[:8]}"
        self.tasks.append(
            NotionTaskData(
                notion_id=page_id,
                name=name,
                status=status,
                priority=priority,
                due_date=due_date,
                jira_url=jira_url,
            )
        )
        return page_id

    def create_meeting_page(
        self,
        title: str,
        category: str,
        krisp_url: str | None = None,
        summary: str | None = None,
    ) -> str:
        page_id = f"fake-notion-{uuid.uuid4().hex[:8]}"
        self.meetings.append(
            NotionMeetingData(
                notion_id=page_id,
                title=title,
                categories=[category],
                summary=summary,
                krisp_url=krisp_url,
            )
        )
        return page_id

    def ensure_daily_page(self) -> DailyPageResult:
        return DailyPageResult(page_id="fake-daily-page", created=False, archived_count=0)

    def update_task_status(self, page_id: str, status: str) -> bool:
        return True

    def update_task_due_date(self, page_id: str, due_date: str) -> bool:
        return True

    def update_task_priority(self, page_id: str, priority: str) -> bool:
        return True

    def update_meeting_summary(self, page_id: str, summary: str) -> bool:
        return True

    def append_paragraph_to_page(self, page_id: str, text: str) -> bool:
        return True

    def update_daily_page(self, page_id: str, summary: str) -> bool:
        return True


class FakeSyncService:
    """In-memory fake of wizard.services.SyncService."""

    def sync_all(self, db) -> list[SourceSyncStatus]:
        return [
            SourceSyncStatus(source="jira", ok=True, skipped=False),
            SourceSyncStatus(source="notion_tasks", ok=True, skipped=False),
            SourceSyncStatus(source="notion_meetings", ok=True, skipped=False),
        ]


class FakeWriteBackService:
    """Records calls for assertion but performs no I/O."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    def push_task_status(self, task: Task) -> WriteBackStatus:
        self.calls.append(("push_task_status", str(task.id)))
        return WriteBackStatus(ok=True)

    def push_task_status_to_notion(self, task: Task) -> WriteBackStatus:
        self.calls.append(("push_task_status_to_notion", str(task.id)))
        return WriteBackStatus(ok=True)

    def push_task_to_notion(self, task: Task) -> WriteBackStatus:
        self.calls.append(("push_task_to_notion", str(task.id)))
        return WriteBackStatus(ok=True, page_id=f"fake-page-{task.id}")

    def push_task_due_date(self, task: Task) -> WriteBackStatus:
        self.calls.append(("push_task_due_date", str(task.id)))
        return WriteBackStatus(ok=True)

    def push_task_priority(self, task: Task) -> WriteBackStatus:
        self.calls.append(("push_task_priority", str(task.id)))
        return WriteBackStatus(ok=True)

    def push_meeting_to_notion(self, meeting: Meeting) -> WriteBackStatus:
        self.calls.append(("push_meeting_to_notion", str(meeting.id)))
        return WriteBackStatus(ok=True, page_id=f"fake-meeting-page-{meeting.id}")

    def push_meeting_summary(self, meeting: Meeting) -> WriteBackStatus:
        self.calls.append(("push_meeting_summary", str(meeting.id)))
        return WriteBackStatus(ok=True)

    def push_session_summary(self, session: WizardSession) -> WriteBackStatus:
        self.calls.append(("push_session_summary", str(session.id)))
        return WriteBackStatus(ok=True)

    def append_task_outcome(self, task: Task, summary: str) -> WriteBackStatus:
        self.calls.append(("append_task_outcome", str(task.id), summary))
        return WriteBackStatus(ok=True)
