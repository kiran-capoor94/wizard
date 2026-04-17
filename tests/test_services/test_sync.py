from unittest.mock import MagicMock

from wizard.schemas import JiraTaskData, NotionMeetingData, NotionTaskData


def make_sync_service():
    from wizard.integrations import JiraClient, NotionClient
    from wizard.repositories import TaskStateRepository
    from wizard.security import SecurityService
    from wizard.services import SyncService
    jira = MagicMock(spec=JiraClient)
    notion = MagicMock(spec=NotionClient)
    security = SecurityService()
    task_state_repo = TaskStateRepository()
    return SyncService(jira=jira, notion=notion, security=security, task_state_repo=task_state_repo), jira, notion


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
    import httpx

    from wizard.models import Task
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.side_effect = httpx.HTTPError("Jira down")
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
    import httpx

    from wizard.models import Meeting, MeetingCategory
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_tasks.side_effect = httpx.HTTPError("Notion down")
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


def test_sync_jira_creates_task_state_for_new_task(db_session):
    from sqlmodel import select

    from wizard.models import TaskState
    svc, jira, notion = make_sync_service()
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []
    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-10", summary="new jira task", status="To Do",
        priority="Medium", issue_type="Issue", url="",
    )]

    svc.sync_jira(db_session)

    states = list(db_session.exec(select(TaskState)).all())
    assert len(states) == 1
    assert states[0].note_count == 0


def test_sync_notion_tasks_creates_task_state_for_new_task(db_session):
    from sqlmodel import select

    from wizard.models import TaskState
    svc, jira, notion = make_sync_service()
    jira.fetch_open_tasks.return_value = []
    notion.fetch_meetings.return_value = []
    notion.fetch_tasks.return_value = [NotionTaskData(
        notion_id="notion-abc", name="new notion task",
    )]

    svc.sync_notion_tasks(db_session)

    states = list(db_session.exec(select(TaskState)).all())
    assert len(states) == 1
    assert states[0].note_count == 0


def test_sync_jira_does_not_duplicate_task_state_on_upsert(db_session):
    from sqlmodel import select

    from wizard.models import Task, TaskState, TaskStatus
    svc, jira, notion = make_sync_service()
    notion.fetch_tasks.return_value = []
    notion.fetch_meetings.return_value = []

    existing = Task(name="old", source_id="ENG-10", source_type="JIRA", status=TaskStatus.BLOCKED)
    db_session.add(existing)
    db_session.flush()
    db_session.refresh(existing)
    state = TaskState(task_id=existing.id, last_touched_at=existing.created_at, stale_days=5)
    db_session.add(state)
    db_session.flush()

    jira.fetch_open_tasks.return_value = [JiraTaskData(
        key="ENG-10", summary="updated name", status="In Progress",
        priority="High", issue_type="Issue", url="",
    )]

    svc.sync_jira(db_session)

    states = list(db_session.exec(select(TaskState)).all())
    assert len(states) == 1
    assert states[0].stale_days == 5
