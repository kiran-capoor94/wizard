from unittest.mock import MagicMock, patch

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _make_notion_mock(notion=None):
    """Build a notion_client mock. Default: ensure_daily_page raises (non-fatal path)."""
    import httpx
    if notion is not None:
        return notion
    mock = MagicMock()
    mock.ensure_daily_page.side_effect = httpx.HTTPError("notion not configured in tests")
    return mock


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# session_start
# ---------------------------------------------------------------------------


async def test_session_start_surfaces_sync_errors(db_session):
    from wizard.repositories import MeetingRepository, TaskRepository, TaskStateRepository
    from wizard.schemas import SourceSyncStatus
    from wizard.tools import session_start

    ctx = MockContext()
    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = [
        SourceSyncStatus(source="jira", ok=False, error="Jira token not configured"),
        SourceSyncStatus(source="notion_tasks", ok=True),
        SourceSyncStatus(source="notion_meetings", ok=True),
    ]

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert len(result.sync_results) == 3
    jira_sync = result.sync_results[0]
    assert jira_sync.source == "jira"
    assert jira_sync.ok is False
    assert jira_sync.error == "Jira token not configured"
    assert result.sync_results[1].ok is True


async def test_session_start_resolves_daily_page(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import MeetingRepository, TaskRepository, TaskStateRepository
    from wizard.schemas import DailyPageResult
    from wizard.tools import session_start

    ctx = MockContext()
    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.return_value = DailyPageResult(
        page_id="today-page-id",
        created=True,
        archived_count=1,
    )
    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=notion_mock,
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert result.daily_page is not None
    assert result.daily_page.page_id == "today-page-id"
    assert result.daily_page.created is True

    session = db_session.get(WizardSession, result.session_id)
    assert session.daily_page_id == "today-page-id"


async def test_session_start_daily_page_failure_is_non_fatal(db_session):
    import httpx

    from wizard.repositories import MeetingRepository, TaskRepository, TaskStateRepository
    from wizard.tools import session_start

    ctx = MockContext()
    notion_mock = MagicMock()
    notion_mock.ensure_daily_page.side_effect = httpx.HTTPError("notion API down")
    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=notion_mock,
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert result.session_id is not None
    assert result.daily_page is None


async def test_session_start_refreshes_stale_days(db_session):
    from wizard.repositories import MeetingRepository, TaskRepository
    from wizard.tools import session_start

    ctx = MockContext()
    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)
    task_state_mock = MagicMock()

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=task_state_mock,
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    task_state_mock.refresh_stale_days.assert_called_once()


async def test_session_start_refresh_stale_days_failure_is_non_fatal(db_session):
    import sqlalchemy.exc

    from wizard.repositories import MeetingRepository, TaskRepository
    from wizard.tools import session_start

    ctx = MockContext()
    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)
    task_state_mock = MagicMock()
    task_state_mock.refresh_stale_days.side_effect = sqlalchemy.exc.OperationalError("db error", None, None)

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=task_state_mock,
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert result.session_id is not None


# --- session threading ---


async def test_session_start_sets_current_session_id_in_ctx_state(db_session):
    from wizard.repositories import MeetingRepository, TaskRepository, TaskStateRepository
    from wizard.tools import session_start

    sync_mock = MagicMock()
    sync_mock.sync_jira = MagicMock(return_value=None)
    sync_mock.sync_notion_tasks = MagicMock(return_value=None)
    sync_mock.sync_notion_meetings = MagicMock(return_value=None)

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert await ctx.get_state("current_session_id") == result.session_id


# --- progress ---


async def test_session_start_reports_progress(db_session):
    from wizard.repositories import MeetingRepository, TaskRepository, TaskStateRepository
    from wizard.schemas import SourceSyncStatus
    from wizard.tools import session_start

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = [
        SourceSyncStatus(source="jira", ok=True),
        SourceSyncStatus(source="notion_tasks", ok=True),
        SourceSyncStatus(source="notion_meetings", ok=True),
    ]

    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        await session_start(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_state_repo=TaskStateRepository(),
            t_repo=TaskRepository(),
            m_repo=MeetingRepository(),
        )

    assert len(impl.progress_calls) == 1
    assert impl.progress_calls[0] == (1, 1, "Sync complete.")
