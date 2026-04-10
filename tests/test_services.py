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
