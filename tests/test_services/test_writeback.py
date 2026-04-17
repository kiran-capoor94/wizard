from unittest.mock import MagicMock


def make_writeback_service():
    from wizard.integrations import JiraClient, NotionClient
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    return WriteBackService(jira=jira, notion=notion), jira, notion


def test_push_task_status_calls_jira(db_session):
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    jira.update_task_status.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="fix", source_id="ENG-1", status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result.ok is True
    assert result.error is None
    jira.update_task_status.assert_called_once_with("ENG-1", "Done")


def test_push_task_status_skips_when_no_source_id(db_session):
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="local-only", source_id=None, status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result.ok is False
    assert result.error == "Task has no Jira source_id"
    jira.update_task_status.assert_not_called()


def test_push_meeting_summary_calls_notion(db_session):
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Meeting
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_meeting_summary.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    meeting = Meeting(title="standup", content="notes", notion_id="page-abc", summary="summary text")

    result = svc.push_meeting_summary(meeting)

    assert result.ok is True
    assert result.error is None
    notion.update_meeting_summary.assert_called_once_with("page-abc", "summary text")


def test_push_session_summary_calls_notion_daily_page(db_session):
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import WizardSession
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_daily_page.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    session = WizardSession(summary="today's session summary", daily_page_id="page-abc")

    result = svc.push_session_summary(session)

    assert result.ok is True
    assert result.error is None
    notion.update_daily_page.assert_called_once_with("page-abc", "today's session summary")


def test_push_session_summary_uses_session_daily_page_id():
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import WizardSession
    from wizard.services import WriteBackService
    mock_notion = MagicMock(spec=NotionClient)
    mock_notion.update_daily_page.return_value = True
    service = WriteBackService(jira=MagicMock(spec=JiraClient), notion=mock_notion)
    session = WizardSession(id=1, summary="Good session", daily_page_id="page-xyz")
    result = service.push_session_summary(session)
    assert result.ok is True
    mock_notion.update_daily_page.assert_called_once_with("page-xyz", "Good session")


def test_push_session_summary_fails_without_daily_page_id():
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import WizardSession
    from wizard.services import WriteBackService
    service = WriteBackService(jira=MagicMock(spec=JiraClient), notion=MagicMock(spec=NotionClient))
    session = WizardSession(id=1, summary="Good session", daily_page_id=None)
    result = service.push_session_summary(session)
    assert result.ok is False
    assert "daily_page_id" in result.error.lower()


def test_push_task_status_uses_jira_transition_name(db_session):
    """TaskStatus.DONE → sends string 'Done' to Jira, not the enum value 'done'"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    jira.update_task_status.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="fix", source_id="ENG-5", status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result.ok is True
    jira.update_task_status.assert_called_once_with("ENG-5", "Done")


def test_push_task_status_to_notion(db_session):
    """TaskStatus.DONE → calls notion.update_task_status with 'Done'"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_task_status.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="fix", notion_id="notion-page-5", status=TaskStatus.DONE)

    result = svc.push_task_status_to_notion(task)

    assert result.ok is True
    notion.update_task_status.assert_called_once_with("notion-page-5", "Done")


def test_push_task_status_to_notion_skips_when_no_notion_id(db_session):
    """Task without notion_id → push_task_status_to_notion returns error"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="fix", notion_id=None, status=TaskStatus.DONE)

    result = svc.push_task_status_to_notion(task)

    assert result.ok is False
    assert result.error == "Task has no notion_id"
    notion.update_task_status.assert_not_called()


def test_push_task_to_notion_creates_page(db_session):
    """Task without notion_id → create_task_page called, returns page_id"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskPriority, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.create_task_page.return_value = "new-notion-page-id"

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="New task", status=TaskStatus.TODO, priority=TaskPriority.HIGH)

    result = svc.push_task_to_notion(task)

    assert result.ok is True
    assert result.page_id == "new-notion-page-id"
    notion.create_task_page.assert_called_once()


def test_push_task_to_notion_updates_status_if_notion_id_exists(db_session):
    """Task with existing notion_id → update status only, returns existing notion_id"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Task, TaskStatus
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_task_status.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="Existing", notion_id="existing-page-id", status=TaskStatus.IN_PROGRESS)

    result = svc.push_task_to_notion(task)

    assert result.ok is True
    assert result.page_id == "existing-page-id"
    notion.update_task_status.assert_called_once_with("existing-page-id", "In progress")
    notion.create_task_page.assert_not_called()


def test_push_meeting_to_notion_creates_page(db_session):
    """Meeting without notion_id + mappable category → create_meeting_page called, returns page_id"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Meeting, MeetingCategory
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.create_meeting_page.return_value = "new-meeting-page-id"

    svc = WriteBackService(jira=jira, notion=notion)
    meeting = Meeting(title="Standup", content="", category=MeetingCategory.STANDUP)

    result = svc.push_meeting_to_notion(meeting)

    assert result.ok is True
    assert result.page_id == "new-meeting-page-id"
    notion.create_meeting_page.assert_called_once_with(
        title="Standup", category="Standup", krisp_url=None, summary=None,
    )


def test_push_meeting_to_notion_skips_unmapped_category(db_session):
    """Meeting with general category (no Notion mapping) → returns error with reason"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Meeting, MeetingCategory
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)

    svc = WriteBackService(jira=jira, notion=notion)
    meeting = Meeting(title="Chat", content="", category=MeetingCategory.GENERAL)

    result = svc.push_meeting_to_notion(meeting)

    assert result.ok is False
    assert "general" in result.error
    notion.create_meeting_page.assert_not_called()


def test_push_meeting_to_notion_updates_summary_if_notion_id_exists(db_session):
    """Meeting with notion_id and summary -> update summary, returns notion_id"""
    from wizard.integrations import JiraClient, NotionClient
    from wizard.models import Meeting, MeetingCategory
    from wizard.services import WriteBackService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_meeting_summary.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    meeting = Meeting(
        title="Standup", content="notes", notion_id="existing-meeting-id",
        summary="Summary text", category=MeetingCategory.STANDUP,
    )

    result = svc.push_meeting_to_notion(meeting)

    assert result.ok is True
    assert result.page_id == "existing-meeting-id"
    notion.update_meeting_summary.assert_called_once_with("existing-meeting-id", "Summary text")
    notion.create_meeting_page.assert_not_called()
