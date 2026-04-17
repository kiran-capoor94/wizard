# ---------------------------------------------------------------------------
# MeetingRepository
# ---------------------------------------------------------------------------

def test_meeting_get_by_id(db_session):
    from wizard.models import Meeting
    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    meeting = Meeting(title="standup", content="notes")
    db_session.add(meeting)
    db_session.commit()
    db_session.refresh(meeting)
    assert meeting.id is not None

    found = repo.get_by_id(db_session, meeting.id)
    assert found.title == "standup"


def test_meeting_get_by_id_raises_when_missing(db_session):
    import pytest

    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    with pytest.raises(ValueError, match="Meeting 999 not found"):
        repo.get_by_id(db_session, 999)


def test_unsummarised_contexts(db_session):
    from wizard.models import Meeting
    from wizard.repositories import MeetingRepository
    repo = MeetingRepository()
    unsummarised = Meeting(title="standup", content="notes")
    summarised = Meeting(title="retro", content="notes", summary="done")
    db_session.add_all([unsummarised, summarised])
    db_session.commit()

    contexts = repo.get_unsummarised_contexts(db_session)
    assert len(contexts) == 1
    assert contexts[0].title == "standup"
    assert contexts[0].already_summarised is False


# ---------------------------------------------------------------------------
# find_latest_session_with_notes
# ---------------------------------------------------------------------------

def test_find_latest_session_with_notes_returns_none_when_no_sessions(db_session):
    from wizard.repositories import find_latest_session_with_notes
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_none_when_sessions_have_no_notes(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import find_latest_session_with_notes

    s = WizardSession()
    db_session.add(s)
    db_session.flush()
    result = find_latest_session_with_notes(db_session)
    assert result is None


def test_find_latest_session_with_notes_returns_most_recent_session_with_notes(db_session):
    import datetime

    from wizard.models import (
        Note,
        NoteType,
        Task,
        TaskCategory,
        TaskPriority,
        TaskStatus,
        WizardSession,
    )
    from wizard.repositories import find_latest_session_with_notes

    s1 = WizardSession(created_at=datetime.datetime(2026, 4, 1))
    s2 = WizardSession(created_at=datetime.datetime(2026, 4, 5))
    s3 = WizardSession(created_at=datetime.datetime(2026, 4, 10))  # most recent but no notes
    db_session.add_all([s1, s2, s3])
    db_session.flush()

    task = Task(name="T", status=TaskStatus.TODO, priority=TaskPriority.HIGH,
                category=TaskCategory.ISSUE)
    db_session.add(task)
    db_session.flush()

    n1 = Note(task_id=task.id, session_id=s1.id, note_type=NoteType.INVESTIGATION, content="a")
    n2 = Note(task_id=task.id, session_id=s2.id, note_type=NoteType.INVESTIGATION, content="b")
    db_session.add_all([n1, n2])
    db_session.flush()

    result = find_latest_session_with_notes(db_session)
    assert result is not None
    assert result.id == s2.id  # s2 is most recent with notes; s3 has no notes
