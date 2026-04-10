import pytest
from unittest.mock import MagicMock, patch


def make_sync_service():
    from src.services import SyncService
    from src.integrations import JiraClient, KrispClient
    from src.security import SecurityService
    jira = MagicMock(spec=JiraClient)
    krisp = MagicMock(spec=KrispClient)
    security = SecurityService()
    return SyncService(jira=jira, krisp=krisp, security=security), jira, krisp


def test_sync_creates_new_task_from_jira(db_session):
    from src.models import Task, TaskStatus
    svc, jira, krisp = make_sync_service()
    jira.fetch_open_tasks.return_value = [{
        "key": "ENG-1", "summary": "Fix login", "status": "In Progress",
        "priority": "High", "issue_type": "Bug",
        "url": "https://jira.example.com/browse/ENG-1",
    }]
    krisp.fetch_recent_meetings.return_value = []

    svc.sync_all(db_session)

    from sqlmodel import select
    tasks = list(db_session.exec(select(Task)).all())
    assert len(tasks) == 1
    assert tasks[0].source_id == "ENG-1"
    assert tasks[0].name == "Fix login"
    assert tasks[0].status == TaskStatus.IN_PROGRESS


def test_sync_upserts_existing_task_name_not_status(db_session):
    from src.models import Task, TaskStatus
    svc, jira, krisp = make_sync_service()

    existing = Task(name="Old name", source_id="ENG-1", status=TaskStatus.DONE, source_type="JIRA")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    jira.fetch_open_tasks.return_value = [{
        "key": "ENG-1", "summary": "New name from Jira", "status": "In Progress",
        "priority": "Medium", "issue_type": "Issue",
        "url": "https://jira.example.com/browse/ENG-1",
    }]
    krisp.fetch_recent_meetings.return_value = []

    svc.sync_all(db_session)

    db_session.refresh(existing)
    assert existing.name == "New name from Jira"   # external wins on name
    assert existing.status == TaskStatus.DONE       # local status preserved


def test_sync_continues_on_jira_failure(db_session):
    from src.models import Meeting
    svc, jira, krisp = make_sync_service()
    jira.fetch_open_tasks.side_effect = Exception("Jira down")
    krisp.fetch_recent_meetings.return_value = [{
        "id": "m1", "title": "Standup", "transcript": "discussed things",
        "url": "https://krisp.ai/m/1",
    }]

    svc.sync_all(db_session)  # must not raise

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert len(meetings) == 1  # krisp still ran


def test_sync_scrubs_content_before_storing(db_session):
    from src.models import Meeting
    svc, jira, krisp = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    krisp.fetch_recent_meetings.return_value = [{
        "id": "m2", "title": "1:1 with john@example.com",
        "transcript": "patient 943 476 5919 discussed",
        "url": "https://krisp.ai/m/2",
    }]

    svc.sync_all(db_session)

    from sqlmodel import select
    meetings = list(db_session.exec(select(Meeting)).all())
    assert "john@example.com" not in meetings[0].content
    assert "943 476 5919" not in meetings[0].content
    assert "[EMAIL_1]" in meetings[0].title or "[EMAIL_1]" in meetings[0].content


def test_push_task_status_calls_jira(db_session):
    from src.services import WriteBackService
    from src.models import Task, TaskStatus
    from src.integrations import JiraClient, NotionClient
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    jira.update_task_status.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="fix", source_id="ENG-1", status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result is True
    jira.update_task_status.assert_called_once_with("ENG-1", TaskStatus.DONE)


def test_push_task_status_skips_when_no_source_id(db_session):
    from src.services import WriteBackService
    from src.models import Task, TaskStatus
    from src.integrations import JiraClient, NotionClient
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)

    svc = WriteBackService(jira=jira, notion=notion)
    task = Task(name="local-only", source_id=None, status=TaskStatus.DONE)

    result = svc.push_task_status(task)

    assert result is False
    jira.update_task_status.assert_not_called()


def test_push_meeting_summary_calls_notion(db_session):
    from src.services import WriteBackService
    from src.models import Meeting
    from src.integrations import JiraClient, NotionClient
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_page_property.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    meeting = Meeting(title="standup", content="notes", notion_id="page-abc", summary="summary text")

    result = svc.push_meeting_summary(meeting)

    assert result is True
    notion.update_page_property.assert_called_once_with("page-abc", "Summary", "summary text")


def test_push_session_summary_calls_notion_daily_page(db_session):
    from src.services import WriteBackService
    from src.models import WizardSession
    from src.integrations import JiraClient, NotionClient
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    notion.update_daily_page.return_value = True

    svc = WriteBackService(jira=jira, notion=notion)
    session = WizardSession(summary="today's session summary")

    result = svc.push_session_summary(session)

    assert result is True
    notion.update_daily_page.assert_called_once_with("today's session summary")
