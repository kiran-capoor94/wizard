from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories.search import SearchRepository


def test_demoted_note_excluded_from_search():
    repo = SearchRepository()
    with SASession(engine) as db:
        n = Note(note_type=NoteType.DECISION,
                 content="quokka migration blueprint alpha", task_id=None,
                 status="superseded", artifact_id="demoted-1", artifact_type="note")
        db.add(n)
        db.commit()
        try:
            res = repo.hybrid_search(db, "quokka migration blueprint", limit=10)
            assert all(r.entity_id != n.id for r in res if r.entity_type == "note")
        finally:
            db.delete(n)
            db.commit()
