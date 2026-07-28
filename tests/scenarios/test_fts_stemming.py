"""Porter stemming: a query word-form matches a differently-inflected note."""
from sqlalchemy.orm import Session as SASession

from wizard.database import engine
from wizard.models import Note, NoteType
from wizard.repositories import search as search_mod
from wizard.repositories.search import SearchRepository


def test_word_form_variation_matches_after_stemming(monkeypatch):
    monkeypatch.setattr(search_mod, "embed", lambda _t: None)
    with SASession(engine) as db:
        n = Note(note_type=NoteType.DECISION,
                 content="we will cache the rendered template fragments",
                 # ck_note_has_artifact_ref requires one of these set; this note
                 # is standalone (no task/session/meeting), so give it an
                 # artifact_id directly.
                 artifact_id="test-fts-stemming-note")
        db.add(n)
        db.commit()
        try:
            # "caching" (query) vs "cache" (note) only match if stemmed.
            results = SearchRepository().hybrid_search(db, "caching templates", limit=10)
            assert any(r.entity_id == n.id for r in results)
        finally:
            db.delete(n)
            db.commit()
