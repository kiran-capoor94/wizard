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
