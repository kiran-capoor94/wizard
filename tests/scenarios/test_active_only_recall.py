import datetime

from sqlalchemy import text
from sqlmodel import Session

from wizard.database import engine
from wizard.models import Note, NoteType, Task, TaskState
from wizard.repositories.note import NoteRepository


def test_get_for_task_active_only_excludes_demoted():
    repo = NoteRepository()
    with Session(engine) as db:
        t = Task(name="active-only-task")
        db.add(t)
        db.flush()
        now = datetime.datetime.now()
        db.add(TaskState(task_id=t.id, last_touched_at=now))
        db.flush()
        a = Note(note_type=NoteType.DECISION, content="live decision", task_id=t.id,
                 status="active", artifact_id=f"t{t.id}", artifact_type="task")
        s = Note(note_type=NoteType.DECISION, content="stale decision", task_id=t.id,
                 status="superseded", artifact_id=f"t{t.id}", artifact_type="task")
        db.add(a)
        db.add(s)
        db.commit()
        try:
            all_notes = repo.get_for_task(db, t.id)                     # default False
            active = repo.get_for_task(db, t.id, active_only=True)
            all_ids = {n.id for n in all_notes}
            active_ids = {n.id for n in active}
            assert a.id in all_ids and s.id in all_ids                  # history sees both
            assert a.id in active_ids and s.id not in active_ids        # recall excludes demoted
        finally:
            db.delete(a)
            db.delete(s)
            db.flush()
            db.execute(text("DELETE FROM task_state WHERE task_id=:i"), {"i": t.id})
            db.delete(t)
            db.commit()
