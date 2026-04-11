def test_session_triage_returns_messages():
    from wizard.prompts import session_triage

    result = session_triage(session_data="test session data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test session data" in result[1].content.text


def test_task_investigation_returns_messages():
    from wizard.prompts import task_investigation

    result = task_investigation(task_data="test task data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test task data" in result[1].content.text


def test_meeting_summarisation_returns_messages():
    from wizard.prompts import meeting_summarisation

    result = meeting_summarisation(meeting_data="test meeting data")
    assert isinstance(result, list)
    assert len(result) >= 2
    assert "test meeting data" in result[1].content.text


def test_session_wrapup_returns_messages():
    from wizard.prompts import session_wrapup

    result = session_wrapup()
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "ending a Wizard session" in result[0].content.text


def test_user_elicitation_returns_messages():
    from wizard.prompts import user_elicitation

    result = user_elicitation()
    assert isinstance(result, list)
    assert len(result) >= 1
    assert "Ask the user when" in result[0].content.text
