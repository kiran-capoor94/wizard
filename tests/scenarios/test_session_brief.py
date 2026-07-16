import datetime

from sqlalchemy import text
from sqlmodel import Session as SASession
from sqlmodel import SQLModel, create_engine

from wizard.database import engine
from wizard.models import Task, TaskState, TaskStatus, WizardSession
from wizard.repositories import TaskRepository
from wizard.session_brief import build_session_brief, render_brief


def test_render_brief_empty_db_returns_empty():
    # A DB with no open tasks / blocked / summaries → "".
    # Use a throwaway in-memory engine with just the ORM tables.
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    with SASession(eng) as db:
        assert render_brief(db) == ""


def test_render_brief_lists_open_tasks_and_summary():
    with SASession(engine) as db:
        t1 = Task(name="brief-alpha in progress", status=TaskStatus.IN_PROGRESS)
        t2 = Task(name="brief-beta todo", status=TaskStatus.TODO)
        db.add(t1)
        db.add(t2)
        db.flush()
        now = datetime.datetime.now()
        db.add(TaskState(task_id=t1.id, last_touched_at=now))
        db.add(TaskState(task_id=t2.id, last_touched_at=now))
        sess = WizardSession(agent="claude-code", summary="brief-prior-summary marker")
        db.add(sess)
        db.commit()
        try:
            brief = render_brief(db)
            assert "brief-alpha in progress" in brief
            assert "brief-beta todo" in brief
            assert "brief-prior-summary marker" in brief
            assert brief.count("\n") + 1 <= 25          # cap
            # ordering parity: task lines follow get_open_task_index order
            idx = TaskRepository().get_open_task_index(db, limit=5)
            ordered_ids = [e.id for e in idx if e.name.startswith("brief-")]
            positions = [brief.find(f"#{i} ") for i in ordered_ids]
            assert positions == sorted(positions)
        finally:
            db.execute(text("DELETE FROM task_state WHERE task_id IN (:a,:b)"), {"a": t1.id, "b": t2.id})
            db.delete(t1)
            db.delete(t2)
            db.delete(sess)
            db.commit()


def test_build_session_brief_readonly_path(tmp_path):
    db_file = tmp_path / "brief.db"
    eng = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(eng)
    with SASession(eng) as db:
        t = Task(name="brief-file-task", status=TaskStatus.TODO)
        db.add(t)
        db.flush()
        db.add(TaskState(task_id=t.id, last_touched_at=datetime.datetime.now()))
        db.commit()
    eng.dispose()
    out = build_session_brief(str(db_file))
    assert "brief-file-task" in out


def test_build_session_brief_missing_db_returns_empty(tmp_path):
    assert build_session_brief(str(tmp_path / "nope.db")) == ""


def test_cli_session_brief_smoke(monkeypatch):
    from typer.testing import CliRunner

    from wizard.cli.main import app

    # settings is frozen, so don't patch settings.db. hook_session_brief does a
    # local `from wizard.session_brief import build_session_brief`, which re-reads
    # the name from that module at call time — so patch it there.
    monkeypatch.setattr(
        "wizard.session_brief.build_session_brief", lambda _p: "cli-brief-marker"
    )
    result = CliRunner().invoke(app, ["hook", "session-brief"])
    assert result.exit_code == 0
    assert "cli-brief-marker" in result.stdout
