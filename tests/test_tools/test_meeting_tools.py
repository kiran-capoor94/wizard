from unittest.mock import MagicMock, patch

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# get_meeting
# ---------------------------------------------------------------------------


async def test_get_meeting_returns_content_and_open_tasks(db_session):
    from wizard.models import Meeting, MeetingTasks, Task, TaskStatus
    from wizard.repositories import MeetingRepository, TaskRepository
    from wizard.tools import get_meeting

    task = Task(name="fix auth", status=TaskStatus.IN_PROGRESS)
    meeting = Meeting(title="standup", content="we discussed fix auth")
    db_session.add(task)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(task)
    db_session.refresh(meeting)
    assert task.id is not None
    assert meeting.id is not None

    link = MeetingTasks(meeting_id=meeting.id, task_id=task.id)
    db_session.add(link)
    db_session.commit()

    ctx = MockContext()
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        result = await get_meeting(ctx, meeting_id=meeting.id, m_repo=MeetingRepository(), t_repo=TaskRepository())

    assert result.meeting_id == meeting.id
    assert result.already_summarised is False
    assert len(result.open_tasks) == 1


# ---------------------------------------------------------------------------
# save_meeting_summary
# ---------------------------------------------------------------------------


async def test_save_meeting_summary_scrubs_and_persists(db_session):
    from wizard.models import Meeting, Note, WizardSession
    from wizard.repositories import MeetingRepository, NoteRepository
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import save_meeting_summary

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(session)
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(meeting)
    assert session.id is not None
    assert meeting.id is not None

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="patient 943 476 5919 was discussed",
            m_repo=MeetingRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.note_id is not None

    saved = db_session.get(Note, result.note_id)
    assert "943 476 5919" not in saved.content
    assert "[NHS_ID_1]" in saved.content


async def test_save_meeting_summary_tasks_linked_count(db_session):
    from wizard.models import Meeting, Task, WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import save_meeting_summary

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    meeting = Meeting(title="sprint review", content="discussed items")
    task1 = Task(name="task one")
    task2 = Task(name="task two")
    db_session.add(session)
    db_session.add(meeting)
    db_session.add(task1)
    db_session.add(task2)
    db_session.commit()
    db_session.refresh(session)
    db_session.refresh(meeting)
    db_session.refresh(task1)
    db_session.refresh(task2)
    assert session.id is not None
    assert meeting.id is not None
    assert task1.id is not None
    assert task2.id is not None

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        from wizard.repositories import MeetingRepository, NoteRepository
        from wizard.security import SecurityService
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="sprint summary",
            task_ids=[task1.id, task2.id],
            m_repo=MeetingRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.tasks_linked == 2


async def test_save_meeting_summary_reads_session_id_from_ctx_state(db_session):
    """session_id must come from ctx state, not as an explicit parameter."""
    from wizard.models import Meeting, Note, WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import save_meeting_summary

    session = WizardSession()
    meeting = Meeting(title="planning", content="content")
    db_session.add(session)
    db_session.add(meeting)
    db_session.flush()
    db_session.refresh(session)
    db_session.refresh(meeting)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_meeting_summary.return_value = WriteBackStatus(ok=True)
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        from wizard.repositories import MeetingRepository, NoteRepository
        from wizard.security import SecurityService
        result = await save_meeting_summary(
            ctx,
            meeting_id=meeting.id,
            summary="planning notes",
            m_repo=MeetingRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    saved = db_session.get(Note, result.note_id)
    assert saved.session_id == session.id


# ---------------------------------------------------------------------------
# ingest_meeting
# ---------------------------------------------------------------------------


async def test_ingest_meeting_creates_meeting(db_session):
    from wizard.models import Meeting, MeetingCategory
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import ingest_meeting

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-meeting-page-id",
    )

    ctx = MockContext()
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        result = await ingest_meeting(
            ctx,
            title="Sprint Planning",
            content="john@example.com reported a bug",
            source_id="krisp-abc",
            source_url="https://krisp.ai/m/abc",
            category=MeetingCategory.PLANNING,
            sec=SecurityService(),
            wb=wb_mock,
        )

    assert result.meeting_id is not None
    assert result.already_existed is False
    meeting = db_session.get(Meeting, result.meeting_id)
    assert "john@example.com" not in meeting.content
    assert "[EMAIL_1]" in meeting.content


async def test_ingest_meeting_dedup_by_source_id(db_session):
    from wizard.models import Meeting
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import ingest_meeting

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=True,
        page_id="notion-meeting-page-id",
    )

    existing = Meeting(title="Old", content="old", source_id="krisp-abc")
    db_session.add(existing)
    db_session.commit()
    db_session.refresh(existing)

    ctx = MockContext()
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        result = await ingest_meeting(
            ctx,
            title="New",
            content="new",
            source_id="krisp-abc",
            sec=SecurityService(),
            wb=wb_mock,
        )

    assert result.already_existed is True
    assert result.meeting_id == existing.id


async def test_ingest_meeting_with_active_session(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import ingest_meeting

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    db_session.refresh(session)

    impl = _MockContextImpl()
    impl._state["current_session_id"] = session.id
    ctx = mock_ctx(impl)

    wb_mock = MagicMock()
    wb_mock.push_meeting_to_notion.return_value = WriteBackStatus(
        ok=False, error="no notion"
    )
    with patch.multiple("wizard.tools.meeting_tools", **_patch_tools(db_session)):
        from wizard.security import SecurityService
        result = await ingest_meeting(
            ctx,
            title="standup",
            content="discussed items",
            sec=SecurityService(),
            wb=wb_mock,
        )

    assert result.meeting_id is not None
