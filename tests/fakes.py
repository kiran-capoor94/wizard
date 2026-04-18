"""Fake implementations for behavioural testing.

Fakes implement the same public interface as real clients but store
data in memory. They are not mocks -- they have real behaviour (store,
retrieve, update), just without network I/O.
"""

from wizard.models import (  # noqa: F401 (used by tests that import from here)
    Meeting,
    Task,
    WizardSession,
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


class FakeSessionCloser:
    """Fake SessionCloser that does nothing."""

    async def close_abandoned(self, db, ctx, current_session_id: int) -> list:
        return []


class FakeJiraClient:
    """Stub FakeJiraClient — returns empty data, used by scenario tests until Task 6-8 strip the deps."""

    @property
    def is_configured(self) -> bool:
        return False

    def close(self) -> None:
        pass

    def fetch_open_tasks(self) -> list:
        return []

    def update_task_status(self, source_id: str, status: str) -> bool:
        return True


class FakeNotionClient:
    """Stub FakeNotionClient — returns empty data, used by scenario tests until Task 6-8 strip the deps."""

    @property
    def is_configured(self) -> bool:
        return False

    def fetch_tasks(self) -> list:
        return []

    def fetch_meetings(self) -> list:
        return []

    def create_task_page(self, name, status, priority=None, jira_url=None, due_date=None) -> str:
        return "fake-page-id"

    def create_meeting_page(self, title, category, krisp_url=None, summary=None) -> str:
        return "fake-meeting-page-id"

    def ensure_daily_page(self):
        # DailyPageResult was removed from schemas — return a simple object
        class _DailyPage:
            page_id = "fake-daily-page"
            created = False
            archived_count = 0

        return _DailyPage()

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
    """Stub FakeSyncService — returns empty results."""

    def sync_all(self, db) -> list:
        return []


class FakeWriteBackService:
    """Stub FakeWriteBackService — records calls but performs no I/O."""

    def __init__(self):
        self.calls: list[tuple[str, ...]] = []

    @staticmethod
    def _make_status(ok: bool = True, error: str = "", page_id: str = "") -> object:
        """Create a mock WriteBackStatus with required attributes."""
        class WriteBackStatus:
            pass
        status = WriteBackStatus()
        status.ok = ok
        status.error = error
        status.page_id = page_id
        return status

    def push_task_status(self, task) -> object:
        self.calls.append(("push_task_status", str(task.id)))
        return self._make_status()

    def push_task_status_to_notion(self, task) -> object:
        self.calls.append(("push_task_status_to_notion", str(task.id)))
        return self._make_status()

    def push_task_to_notion(self, task) -> object:
        self.calls.append(("push_task_to_notion", str(task.id)))
        return self._make_status(page_id=f"fake-page-{task.id}")

    def push_task_due_date(self, task) -> object:
        self.calls.append(("push_task_due_date", str(task.id)))
        return self._make_status()

    def push_task_priority(self, task) -> object:
        self.calls.append(("push_task_priority", str(task.id)))
        return self._make_status()

    def push_meeting_to_notion(self, meeting) -> object:
        self.calls.append(("push_meeting_to_notion", str(meeting.id)))
        return self._make_status(page_id=f"fake-meeting-page-{meeting.id}")

    def push_meeting_summary(self, meeting) -> object:
        self.calls.append(("push_meeting_summary", str(meeting.id)))
        return self._make_status()

    def push_session_summary(self, session) -> object:
        self.calls.append(("push_session_summary", str(session.id)))
        return self._make_status()

    def append_task_outcome(self, task, summary: str) -> object:
        self.calls.append(("append_task_outcome", str(task.id), summary))
        return self._make_status()
