from wizard.models import Meeting, Note, Task, WizardSession


def test_task_has_no_notion_id():
    assert "notion_id" not in Task.model_fields


def test_meeting_has_no_notion_id():
    assert "notion_id" not in Meeting.model_fields


def test_wizard_session_has_no_daily_page_id():
    assert "daily_page_id" not in WizardSession.model_fields


def test_note_has_no_source_fields():
    for field in ("source_id", "source_type", "source_url"):
        assert field not in Note.model_fields
