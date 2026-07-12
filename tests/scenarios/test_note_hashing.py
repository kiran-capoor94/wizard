import datetime

from sqlalchemy import text
from sqlmodel import Session

from wizard.database import engine
from wizard.models import Note, NoteType, Task, TaskState
from wizard.note_hashing import content_hash, normalize_for_hash
from wizard.repositories.note import NoteRepository


def test_normalize_collapses_whitespace_and_strips():
    assert normalize_for_hash("  a   b\n c \t") == "a b c"


def test_content_hash_ignores_whitespace_variation():
    assert content_hash("redis  caching\n") == content_hash("redis caching")


def test_content_hash_is_case_sensitive():
    # keep case — distinct content must not collapse
    assert content_hash("Cache") != content_hash("cache")


def test_whitespace_variant_note_dedups_by_hash():
    from wizard.note_hashing import content_hash
    repo = NoteRepository()
    with Session(engine) as db:
        t = Task(name="dedup-hash-task"); db.add(t); db.flush()
        now = datetime.datetime.now()
        db.add(TaskState(task_id=t.id, last_touched_at=now)); db.flush()
        h = content_hash("finding X")
        n1 = Note(note_type=NoteType.INVESTIGATION, content="finding X",
                  task_id=t.id, content_hash=h, artifact_id=f"t{t.id}", artifact_type="task")
        db.add(n1); db.commit()
        try:
            # a whitespace-variant produces the SAME hash → dedup lookup finds n1
            assert content_hash("finding   X\n") == h
            hit = repo.get_by_content_hash(db, t.id, content_hash("finding   X\n"))
            assert hit is not None and hit.id == n1.id
        finally:
            db.delete(n1); db.flush()
            db.execute(text("DELETE FROM task_state WHERE task_id=:i"), {"i": t.id})
            db.delete(t); db.commit()
