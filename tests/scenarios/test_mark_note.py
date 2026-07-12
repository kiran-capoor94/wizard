import pytest
from fastmcp.exceptions import ToolError
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories.note import NoteRepository


def _mk_note(db, content, status="active"):
    n = Note(note_type=NoteType.INVESTIGATION, content=content, task_id=None,
              status=status, artifact_id=f"mn-{content}", artifact_type="note")
    db.add(n)
    db.flush()
    return n


def test_set_status_demotes_and_links():
    repo = NoteRepository()
    with SASession(engine) as db:
        old = _mk_note(db, "old finding")
        new = _mk_note(db, "new finding")
        db.commit()
        try:
            repo.set_status(db, old.id, "superseded", superseded_by_note_id=new.id)
            db.commit()
            db.refresh(old)
            db.refresh(new)
            assert old.status == "superseded"
            assert new.supersedes_note_id == old.id
        finally:
            db.delete(old)
            db.delete(new)
            db.commit()


def test_set_status_reversible():
    repo = NoteRepository()
    with SASession(engine) as db:
        n = _mk_note(db, "toggle", status="superseded")
        db.commit()
        try:
            repo.set_status(db, n.id, "active")
            db.commit()
            db.refresh(n)
            assert n.status == "active"
        finally:
            db.delete(n)
            db.commit()


async def test_mark_note_rejects_bad_status():
    from wizard.repositories.note import NoteRepository
    from wizard.tools.note_tools import mark_note
    with SASession(engine) as db:
        n = _mk_note(db, "bad-status")
        db.commit()
        note_id = n.id
    try:
        with pytest.raises(ToolError):
            await mark_note(note_id, "bogus", n_repo=NoteRepository())
        with pytest.raises(ToolError):
            await mark_note(
                note_id, "active", superseded_by_note_id=note_id, n_repo=NoteRepository()
            )
    finally:
        with SASession(engine) as db:
            db.delete(db.get(Note, note_id))
            db.commit()


async def test_mark_note_rejects_self_supersede():
    from wizard.tools.note_tools import mark_note
    with SASession(engine) as db:
        n = _mk_note(db, "self-supersede-candidate")
        db.commit()
        note_id = n.id
    try:
        with pytest.raises(ToolError):
            await mark_note(
                note_id, "superseded", superseded_by_note_id=note_id, n_repo=NoteRepository()
            )
    finally:
        with SASession(engine) as db:
            db.delete(db.get(Note, note_id))
            db.commit()


async def test_mark_note_reversible_clears_backlink():
    """Minor #4: reverting a demoted note back to 'active' must clear the
    winner's back-link (supersedes_note_id)."""
    from wizard.tools.note_tools import mark_note
    with SASession(engine) as db:
        old = _mk_note(db, "old-for-reversal")
        winner = _mk_note(db, "winner-for-reversal")
        db.commit()
        old_id, winner_id = old.id, winner.id
    try:
        demote = await mark_note(
            old_id, "superseded", superseded_by_note_id=winner_id, n_repo=NoteRepository()
        )
        assert demote.status == "superseded"
        with SASession(engine) as db:
            w = db.get(Note, winner_id)
            assert w.supersedes_note_id == old_id

        revert = await mark_note(old_id, "active", n_repo=NoteRepository())
        assert revert.status == "active"
        with SASession(engine) as db:
            w = db.get(Note, winner_id)
            assert w.supersedes_note_id is None
    finally:
        with SASession(engine) as db:
            db.delete(db.get(Note, old_id))
            db.delete(db.get(Note, winner_id))
            db.commit()


async def test_mark_note_scrubs_rolling_summary(mcp_client, seed_task):
    """Important #1: demoting a note must scrub it from the task's cached
    rolling_summary immediately (not just on the next note save)."""
    task = await seed_task(name="Rolling summary scrub task")
    await mcp_client.call_tool("session_start", {})

    old = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "old finding content",
        "mental_model": "OLD-MENTAL-MODEL-ZULU",
    })
    assert not old.is_error, old
    old_note_id = old.structured_content["note_id"]

    new = await mcp_client.call_tool("save_note", {
        "task_id": task.id,
        "note_type": "INVESTIGATION",
        "content": "new finding content",
        "mental_model": "NEW-MENTAL-MODEL-YANKEE",
    })
    assert not new.is_error, new
    new_note_id = new.structured_content["note_id"]

    before = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not before.is_error, before
    assert "OLD-MENTAL-MODEL-ZULU" in before.structured_content["rolling_summary"]
    assert "NEW-MENTAL-MODEL-YANKEE" in before.structured_content["rolling_summary"]

    demote = await mcp_client.call_tool("mark_note", {
        "note_id": old_note_id,
        "status": "superseded",
        "superseded_by_note_id": new_note_id,
    })
    assert not demote.is_error, demote

    after = await mcp_client.call_tool("task_start", {"task_id": task.id})
    assert not after.is_error, after
    rolling_summary = after.structured_content.get("rolling_summary") or ""
    assert "OLD-MENTAL-MODEL-ZULU" not in rolling_summary
    assert "NEW-MENTAL-MODEL-YANKEE" in rolling_summary


def test_demote_hides_note_from_search():
    from wizard.repositories.search import SearchRepository
    repo = NoteRepository()
    search = SearchRepository()
    with SASession(engine) as db:
        n = _mk_note(db, "wombat telemetry pipeline zeta")
        db.commit()
        try:
            before = search.hybrid_search(db, "wombat telemetry pipeline", limit=10)
            assert any(r.entity_id == n.id for r in before if r.entity_type == "note")
            repo.set_status(db, n.id, "superseded")
            db.commit()
            after = search.hybrid_search(db, "wombat telemetry pipeline", limit=10)
            assert all(r.entity_id != n.id for r in after if r.entity_type == "note")
        finally:
            db.delete(db.get(Note, n.id))
            db.commit()
