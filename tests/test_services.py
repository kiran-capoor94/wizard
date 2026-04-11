from unittest.mock import MagicMock

from wizard.schemas import JiraTaskData, NotionTaskData, NotionMeetingData


def make_sync_service():
    from wizard.services import SyncService
    from wizard.integrations import JiraClient, NotionClient
    from wizard.security import SecurityService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    security = SecurityService()
    return SyncService(jira=jira, notion=notion, security=security), jira, notion


def test_sync_creates_new_task_from_jira(db_session):
    from wizard.models import Task, TaskStatus
    svc, jira, notion = make_sync_service()
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []
    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-1", summary="Fix login", status="In Progress",
        priority="High", issue_type="Bug",
        url="https://jira.example.com/browse/ENG-1",
    )]

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1
    assert tasks[0].source_id == "ENG-1"
    assert tasks[0].name == "Fix login"
    assert tasks[0].status == TaskStatus.IN_PROGRESS


def test_sync_upserts_existing_task_name_not_status(db_session):
    from wizard.models import Task, TaskStatus
    svc, jira, notion = make_sync_service()
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []

    existing = Task(name="Old name", source_id="ENG-1", status=TaskStatus.DONE, source_type="JIRA")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-1", summary="New name from Jira", status="In Progress",
        priority="Medium", issue_type="Issue",
        url="https://jira.example.com/browse/ENG-1",
    )]

    svc.sync_all(db_session)

    db_session.refresh(existing)
    assert existing.name == "New name from Jira"   # external wins on name
    assert existing.status == TaskStatus.DONE       # local status preserved


def test_sync_continues_on_jira_failure(db_session):
    from wizard.models import Task
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.side_effect = Exception("Jira down")
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []

    svc.sync_all(db_session)  # must not raise

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 0  # no tasks created due to error


def test_sync_scrubs_content_before_storing(db_session):
    from wizard.models import Task
    svc, jira, notion = make_sync_service()
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []
    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-2", summary="1:1 with john@example.com",
        status="To Do", priority="Low", issue_type="Issue",
        url="https://jira.example.com/browse/ENG-2",
    )]

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert "john@example.com" not in tasks[0].name
    assert "[EMAIL_1]" in tasks[0].name


def test_push_task_status_calls_jira(db_session):
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="local-only", source_id=None, status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result.ok is False
    assert result.error == "Task has no Jira source_id"
    jira.update_task_status.assert_not_called()


def test_push_meeting_summary_calls_notion(db_session):
    from wizard.services import WriteBackService
    from wizard.models import Meeting
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import WizardSession
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import WizardSession
    from wizard.integrations import JiraClient, NotionClient
    mock_notion = MagicMock(spec=NotionClient)
    mock_notion.update_daily_page.return_value = True
    service = WriteBackService(jira=MagicMock(spec=JiraClient), notion=mock_notion)
    session = WizardSession(id=1, summary="Good session", daily_page_id="page-xyz")
    result = service.push_session_summary(session)
    assert result.ok is True
    mock_notion.update_daily_page.assert_called_once_with("page-xyz", "Good session")


def test_push_session_summary_fails_without_daily_page_id():
    from wizard.services import WriteBackService
    from wizard.models import WizardSession
    from wizard.integrations import JiraClient, NotionClient
    service = WriteBackService(jira=MagicMock(spec=JiraClient), notion=MagicMock(spec=NotionClient))
    session = WizardSession(id=1, summary="Good session", daily_page_id=None)
    result = service.push_session_summary(session)
    assert result.ok is False
    assert "daily_page_id" in result.error.lower()


# ============================================================================
# New tests: Notion sync (SyncService)
# ============================================================================

def test_sync_notion_creates_task_with_jira_key(db_session):
    """Notion task with Jira URL → creates Task with both notion_id and source_id"""
    from wizard.models import Task, TaskStatus
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = [NotionTaskData(
        notion_id="notion-page-1",
        name="Build API",
        status="In progress",
        priority="High",
        due_date=None,
        jira_url="https://org.atlassian.net/browse/ENG-42",
        jira_key="ENG-42",
    )]
    notion.fetch_meetings.return_value = []

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1
    assert tasks[0].notion_id == "notion-page-1"
    assert tasks[0].source_id == "ENG-42"
    assert tasks[0].status == TaskStatus.IN_PROGRESS


def test_sync_notion_dedup_with_jira_task(db_session):
    """Jira creates task first; Notion finds it by source_id and sets notion_id"""
    from wizard.models import Task
    svc, jira, notion = make_sync_service()

    # Jira creates the task first
    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-10", summary="Existing task", status="In Progress",
        priority="Medium", issue_type="Issue",
        url="https://jira.example.com/browse/ENG-10",
    )]
    notion.fetch_tasks.return_value = [NotionTaskData(
        notion_id="notion-page-10",
        name="Existing task (Notion)",
        status="In progress",
        priority="Medium",
        due_date=None,
        jira_url="https://jira.example.com/browse/ENG-10",
        jira_key="ENG-10",
    )]
    notion.fetch_meetings.return_value = []

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1  # deduped — only one Task
    assert tasks[0].source_id == "ENG-10"
    assert tasks[0].notion_id == "notion-page-10"


def test_sync_notion_creates_meeting(db_session):
    """Notion meeting with Planning category → creates Meeting with PLANNING"""
    from wizard.models import Meeting, MeetingCategory
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = [NotionMeetingData(
        notion_id="meeting-page-1",
        title="Sprint Planning",
        categories=["Planning"],
        summary=None,
        krisp_url=None,
        date=None,
    )]

    svc.sync_all(db_session)

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert len(meetings) == 1
    assert meetings[0].notion_id == "meeting-page-1"
    assert meetings[0].category == MeetingCategory.PLANNING
    assert meetings[0].title == "Sprint Planning"


def test_sync_notion_meeting_category_fallback_to_general(db_session):
    """"Customer call" category → GENERAL fallback"""
    from wizard.models import Meeting, MeetingCategory
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = [NotionMeetingData(
        notion_id="meeting-page-2",
        title="Customer call",
        categories=["Customer call"],
        summary=None,
        krisp_url=None,
        date=None,
    )]

    svc.sync_all(db_session)

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert len(meetings) == 1
    assert meetings[0].category == MeetingCategory.GENERAL


def test_sync_continues_on_notion_tasks_failure(db_session):
    """Notion tasks fetch fails; Notion meetings sync still runs"""
    from wizard.models import Meeting, MeetingCategory
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.side_effect = Exception("Notion down")
    notion.fetch_meetings.return_value = [NotionMeetingData(
        notion_id="meeting-page-3",
        title="Retro",
        categories=["Retro"],
        summary=None,
        krisp_url=None,
        date=None,
    )]

    svc.sync_all(db_session)  # must not raise

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert len(meetings) == 1
    assert meetings[0].category == MeetingCategory.RETRO


# ============================================================================
# New tests: WriteBackService
# ============================================================================

def test_push_task_status_uses_jira_transition_name(db_session):
    """TaskStatus.DONE → sends string 'Done' to Jira, not the enum value 'done'"""
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus, TaskPriority
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Task, TaskStatus
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Meeting, MeetingCategory
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Meeting, MeetingCategory
    from wizard.integrations import JiraClient, NotionClient
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
    from wizard.services import WriteBackService
    from wizard.models import Meeting, MeetingCategory
    from wizard.integrations import JiraClient, NotionClient
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


# ============================================================================
# Notion sync: due_date, source_url, summary (review fixes)
# ============================================================================

def test_sync_notion_task_sets_due_date(db_session):
    """Notion task with due_date -> stored on new Task"""
    from wizard.models import Task
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = [NotionTaskData(
        notion_id="np-dd",
        name="With due date",
        status="Not started",
        priority="Medium",
        due_date="2026-04-15",
        jira_url=None,
        jira_key=None,
    )]
    notion.fetch_meetings.return_value = []

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1
    assert tasks[0].due_date is not None
    assert tasks[0].due_date.day == 15


def test_sync_notion_task_sets_source_url(db_session):
    """Notion task with jira_url -> source_url set on new Task"""
    from wizard.models import Task
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = [NotionTaskData(
        notion_id="np-url",
        name="With URL",
        status="Not started",
        priority="Low",
        due_date=None,
        jira_url="https://org.atlassian.net/browse/ENG-99",
        jira_key="ENG-99",
    )]
    notion.fetch_meetings.return_value = []

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1
    assert tasks[0].source_url == "https://org.atlassian.net/browse/ENG-99"


def test_sync_notion_meeting_updates_source_on_existing(db_session):
    """Existing meeting (from Notion) gets source_id/source_url when Krisp URL appears"""
    from wizard.models import Meeting
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = []

    existing = Meeting(title="Old", content="", notion_id="nm-existing")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    notion.fetch_meetings.return_value = [NotionMeetingData(
        notion_id="nm-existing",
        title="Updated",
        categories=[],
        summary=None,
        krisp_url="https://krisp.ai/m/abc123",
        date=None,
    )]

    svc.sync_all(db_session)

    db_session.refresh(existing)
    assert existing.source_id == "abc123"
    assert existing.source_url == "https://krisp.ai/m/abc123"


def test_sync_notion_new_meeting_stores_summary(db_session):
    """New meeting from Notion with summary -> summary stored"""
    from wizard.models import Meeting
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = [NotionMeetingData(
        notion_id="nm-with-summary",
        title="Standup",
        categories=["Standup"],
        summary="Quick sync on sprint progress",
        krisp_url=None,
        date=None,
    )]

    svc.sync_all(db_session)

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert len(meetings) == 1
    assert meetings[0].summary == "Quick sync on sprint progress"
