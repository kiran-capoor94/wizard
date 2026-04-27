"""Scenario: full session lifecycle -- session_start, task_start, save_note, session_end."""

from unittest.mock import patch


async def test_session_lifecycle(mcp_client, seed_task):
    task = await seed_task(name="Fix auth bug")

    # 1. session_start
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    d = r.structured_content
    session_id = d["session_id"]
    assert session_id is not None
    assert d["source"] == "startup"
    assert isinstance(d["open_tasks"], str)
    assert d["open_tasks"].startswith("[")

    # 2. task_start
    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["task"]["id"] == task.id
    assert d["compounding"] is False
    initial_note_count = sum(d["notes_by_type"].values())

    # 3. save_note
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Found the root cause in the OAuth flow",
    })
    assert not r.is_error, r
    assert r.structured_content["note_id"] is not None

    # 4. task_start again -- note count increases, compounding flips
    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["compounding"] is True
    assert sum(d["notes_by_type"].values()) == initial_note_count + 1

    # 5. what_am_i_missing
    r = await mcp_client.call_tool("what_am_i_missing", {"task_id": task.id})
    assert not r.is_error, r
    assert isinstance(r.structured_content["signals"], list)

    # 6. session_end
    r = await mcp_client.call_tool("session_end", {
        "session_id": session_id,
        "summary": "Fixed the OAuth bug",
        "intent": "Bug fix",
        "working_set": [task.id],
        "state_delta": "Identified and fixed root cause",
        "open_loops": [],
        "next_actions": ["Deploy to staging"],
        "closure_status": "clean",
    })
    assert not r.is_error, r
    d = r.structured_content
    assert d["note_id"] is not None
    assert d["session_state_saved"] is True
    assert d["closure_status"] == "clean"


async def test_session_start_writes_wizard_id_to_keyed_dir(mcp_client, tmp_path):
    """session_start must write wizard_id to SESSIONS_DIR/<uuid>/wizard_id."""
    uuid = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    sessions_dir = tmp_path / "sessions"
    (sessions_dir / uuid).mkdir(parents=True)
    (sessions_dir / uuid / "source").write_text("startup")

    with patch("wizard.tools.session_tools.SESSIONS_DIR", sessions_dir):
        r = await mcp_client.call_tool("session_start", {"agent_session_id": uuid})

    assert not r.is_error, r
    wizard_id_file = sessions_dir / uuid / "wizard_id"
    assert wizard_id_file.exists()
    assert wizard_id_file.read_text().strip() == str(r.structured_content["session_id"])
    assert r.structured_content["source"] == "startup"
