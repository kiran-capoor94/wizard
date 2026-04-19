from wizard.schemas import TaskRecommendation, WorkRecommendationResponse


def test_task_recommendation_fields():
    rec = TaskRecommendation(
        task_id=1,
        name="Fix auth bug",
        priority="high",
        status="in_progress",
        score=0.87,
        reason="High priority with active momentum",
        momentum="active",
        last_note_preview="Investigating the race condition in token refresh",
    )
    assert rec.task_id == 1
    assert rec.momentum == "active"
    assert rec.last_note_preview is not None


def test_work_recommendation_response_allows_none_recommended():
    resp = WorkRecommendationResponse(
        recommended_task=None,
        alternatives=[],
        skipped_blocked=0,
        message="No open tasks",
    )
    assert resp.recommended_task is None
    assert resp.message == "No open tasks"
