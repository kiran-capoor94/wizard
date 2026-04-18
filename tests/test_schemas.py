from wizard.schemas import (
    CreateTaskResponse,
    GetSessionsResponse,
    GetTasksResponse,
    IngestMeetingResponse,
    SaveMeetingSummaryResponse,
    SessionEndResponse,
    SessionStartResponse,
    TaskDetailResponse,
    UpdateTaskResponse,
)


def test_session_start_has_wizard_context_not_sync():
    assert "wizard_context" in SessionStartResponse.model_fields
    assert "sync_results" not in SessionStartResponse.model_fields
    assert "daily_page" not in SessionStartResponse.model_fields


def test_create_task_has_already_existed():
    r = CreateTaskResponse(task_id=1)
    assert r.already_existed is False


def test_update_task_no_writebacks():
    for field in ("notion_write_back", "status_writeback", "due_date_writeback", "priority_writeback"):
        assert field not in UpdateTaskResponse.model_fields


def test_no_notion_writeback_on_meeting_responses():
    assert "notion_write_back" not in IngestMeetingResponse.model_fields
    assert "notion_write_back" not in SaveMeetingSummaryResponse.model_fields


def test_session_end_no_writeback():
    assert "notion_write_back" not in SessionEndResponse.model_fields


def test_query_response_types_exist():
    assert GetTasksResponse.model_fields
    assert GetSessionsResponse.model_fields
    assert TaskDetailResponse.model_fields
