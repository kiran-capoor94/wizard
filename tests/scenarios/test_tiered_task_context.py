"""Scenario: tiered task_start context delivery.

Verifies that:
1. task_start returns key notes (decisions first, then mental-model notes, then recent)
   rather than a blind recency slice.
2. Decisions are always included even when buried deep in history.
3. older_notes_available is set when notes were excluded from the selection.
4. rolling_summary is populated once mental_models are recorded.
5. Full counts in notes_by_type reflect all notes, not just the returned subset.
6. rewind_task still returns the full history.
"""


async def test_decisions_always_included_over_recency(mcp_client, seed_task):
    """Decisions saved early must appear in prior_notes even when newer junk notes exist."""
    task = await seed_task(name="Prioritised context task")

    # Save 1 decision early, then 5 low-value investigation notes
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "decision",
        "content": "Chose approach X after reviewing options",
    })
    assert not r.is_error, r
    for i in range(5):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation",
            "content": f"Junk investigation note {i}",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content

    returned_types = {n["note_type"] for n in d["prior_notes"]}
    assert "decision" in returned_types, "Decision must be returned despite being oldest"
    assert d["total_notes"] == 6
    assert d["older_notes_available"] is True
    assert d["notes_by_type"].get("investigation", 0) == 5
    assert d["notes_by_type"].get("decision", 0) == 1


async def test_mental_model_notes_included_before_recency_fill(mcp_client, seed_task):
    """Notes with mental_models rank above plain recent notes."""
    task = await seed_task(name="Mental model priority task")

    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Root cause is in the auth layer",
        "mental_model": "OAuth token expiry not refreshed — interceptor missing the 401 path.",
    })
    assert not r.is_error, r
    for i in range(5):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation",
            "content": f"Plain note {i} with no mental model",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    mm_notes = [n for n in r.structured_content["prior_notes"] if n.get("mental_model")]
    assert len(mm_notes) >= 1
    assert any("interceptor" in (n.get("mental_model") or "") for n in r.structured_content["prior_notes"])


async def test_no_cap_when_all_notes_are_key(mcp_client, seed_task):
    """With 2 notes total, all are returned and older_notes_available is False."""
    task = await seed_task(name="Small task")

    for i in range(2):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation", "content": f"Finding {i}",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["total_notes"] == 2
    assert len(d["prior_notes"]) == 2
    assert d["older_notes_available"] is False


async def test_rolling_summary_populated_from_mental_models(mcp_client, seed_task):
    task = await seed_task(name="Mental model task")

    # First note without mental_model -- no summary yet
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "investigation",
        "content": "Root cause investigation",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    assert r.structured_content["rolling_summary"] is None

    # Second note with mental_model -- summary should now be present
    r = await mcp_client.call_tool("save_note", {
        "task_id": task.id, "note_type": "decision",
        "content": "Chose approach X",
        "mental_model": "The bug is in the auth middleware — approach X fixes it cleanly.",
    })
    assert not r.is_error, r

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    d = r.structured_content
    assert d["rolling_summary"] is not None
    assert "approach X fixes it cleanly" in d["rolling_summary"]
    assert "decision" in d["rolling_summary"]


async def test_rewind_task_returns_full_history(mcp_client, seed_task):
    task = await seed_task(name="Rewind history task")

    for i in range(7):
        r = await mcp_client.call_tool("save_note", {
            "task_id": task.id, "note_type": "investigation", "content": f"Note {i}",
        })
        assert not r.is_error, r

    r = await mcp_client.call_tool("rewind_task", {"task_id": task.id})
    assert not r.is_error, r
    rewind_d = r.structured_content

    r = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not r.is_error, r
    ts_d = r.structured_content

    assert rewind_d["summary"]["total_notes"] == 7
    assert len(rewind_d["timeline"]) == 7
    assert len(ts_d["prior_notes"]) < 7
    assert ts_d["older_notes_available"] is True


async def test_task_start_skill_instructions_sent_once_per_session(mcp_client, seed_task):
    """skill_instructions must be included on first task_start, omitted on subsequent calls."""
    task_a = await seed_task(name="Task A")
    task_b = await seed_task(name="Task B")

    r = await mcp_client.call_tool("task_start", {"task_id": task_a.id})
    assert not r.is_error, r
    assert r.structured_content["skill_instructions"] is not None, "First call must include skill_instructions"

    r = await mcp_client.call_tool("task_start", {"task_id": task_b.id})
    assert not r.is_error, r
    assert r.structured_content["skill_instructions"] is None, "Second call must omit skill_instructions"
