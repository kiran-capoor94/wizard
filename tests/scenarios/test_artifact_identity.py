"""Scenario tests for Wizard v3 artifact identity layer — Phase 1–2."""

import uuid

from wizard.models import Meeting, Note, NoteType, Task, WizardSession
from wizard.repositories.note import NoteRepository, detect_drift


class TestNewEntitiesGetArtifactId:
    def test_new_task_has_artifact_id(self, db_session):
        task = Task(name="test task")
        db_session.add(task)
        db_session.flush()
        assert task.artifact_id is not None
        assert len(task.artifact_id) == 36  # UUID format

    def test_new_session_has_artifact_id(self, db_session):
        s = WizardSession()
        db_session.add(s)
        db_session.flush()
        assert s.artifact_id is not None

    def test_new_meeting_has_artifact_id(self, db_session):
        m = Meeting(title="test", content="content")
        db_session.add(m)
        db_session.flush()
        assert m.artifact_id is not None

    def test_artifact_ids_are_unique(self, db_session):
        t1 = Task(name="task 1")
        t2 = Task(name="task 2")
        db_session.add(t1)
        db_session.add(t2)
        db_session.flush()
        assert t1.artifact_id != t2.artifact_id

    def test_session_default_persistence_is_ephemeral(self, db_session):
        s = WizardSession()
        db_session.add(s)
        db_session.flush()
        assert s.persistence == "ephemeral"

    def test_task_default_persistence_is_persistent(self, db_session):
        t = Task(name="persistent task")
        db_session.add(t)
        db_session.flush()
        assert t.persistence == "persistent"


class TestNoteAnchorInheritance:
    def test_note_inherits_task_artifact_id(self, db_session):
        task = Task(name="anchor task")
        db_session.add(task)
        db_session.flush()
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="some finding",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        assert note.artifact_id == task.artifact_id
        assert note.artifact_type == "task"

    def test_note_inherits_session_artifact_id(self, db_session):
        s = WizardSession()
        db_session.add(s)
        db_session.flush()
        note = Note(
            note_type=NoteType.SESSION_SUMMARY,
            content="session summary",
            session_id=s.id,
            artifact_id=s.artifact_id,
            artifact_type="session",
        )
        db_session.add(note)
        db_session.flush()
        assert note.artifact_id == s.artifact_id
        assert note.artifact_type == "session"


class TestNoteStatus:
    def test_new_note_has_active_status(self, db_session):
        task = Task(name="status test")
        db_session.add(task)
        db_session.flush()
        note = Note(
            note_type=NoteType.DECISION,
            content="a decision",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        assert note.status == "active"

    def test_superseded_note_tracks_replacement(self, db_session):
        task = Task(name="supersede test")
        db_session.add(task)
        db_session.flush()
        old = Note(
            note_type=NoteType.DECISION,
            content="old decision",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(old)
        db_session.flush()
        new = Note(
            note_type=NoteType.DECISION,
            content="new decision superseding old",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
            supersedes_note_id=old.id,
        )
        old.status = "superseded"
        db_session.add(new)
        db_session.flush()
        db_session.refresh(old)
        assert old.status == "superseded"
        assert new.supersedes_note_id == old.id

    def test_unclassified_status_for_synthesis_failures(self, db_session):
        s = WizardSession()
        db_session.add(s)
        db_session.flush()
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="Synthesis failed for session 1.",
            session_id=s.id,
            artifact_id=s.artifact_id,
            artifact_type="session",
            synthesis_confidence=0.0,
            status="unclassified",
        )
        db_session.add(note)
        db_session.flush()
        assert note.status == "unclassified"
        assert note.synthesis_confidence == 0.0


class TestGetNotesByArtifactId:
    def test_returns_notes_for_artifact(self, db_session):
        task = Task(name="repo test task")
        db_session.add(task)
        db_session.flush()
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="finding",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        repo = NoteRepository()
        results = repo.get_notes_by_artifact_id(db_session, task.artifact_id)
        ids = [n.id for n in results]
        assert note.id in ids

    def test_returns_empty_for_unknown_artifact(self, db_session):
        repo = NoteRepository()
        results = repo.get_notes_by_artifact_id(db_session, str(uuid.uuid4()))
        assert results == []

    def test_ordered_by_created_at_desc_by_default(self, db_session):
        task = Task(name="order test")
        db_session.add(task)
        db_session.flush()
        n1 = Note(
            note_type=NoteType.INVESTIGATION,
            content="first",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(n1)
        db_session.flush()
        n2 = Note(
            note_type=NoteType.DECISION,
            content="second",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(n2)
        db_session.flush()
        repo = NoteRepository()
        results = repo.get_notes_by_artifact_id(db_session, task.artifact_id)
        result_ids = [n.id for n in results]
        assert result_ids.index(n2.id) < result_ids.index(n1.id)

    def test_get_artifact_id_hashes_returns_non_null_hashes(self, db_session):
        task = Task(name="hash test")
        db_session.add(task)
        db_session.flush()
        note_with_hash = Note(
            note_type=NoteType.INVESTIGATION,
            content="hashed finding",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
            synthesis_content_hash="abc123",
        )
        note_without_hash = Note(
            note_type=NoteType.DECISION,
            content="unhashed decision",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note_with_hash)
        db_session.add(note_without_hash)
        db_session.flush()
        repo = NoteRepository()
        hashes = repo.get_artifact_id_hashes(db_session, task.artifact_id)
        assert "abc123" in hashes
        assert None not in hashes


class TestDriftDetection:
    def test_no_drift_when_paths_agree(self, db_session):
        task = Task(name="drift test")
        db_session.add(task)
        db_session.flush()
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="finding",
            task_id=task.id,
            artifact_id=task.artifact_id,
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        repo = NoteRepository()
        old_ids = {n.id for n in repo.get_for_task(db_session, task.id)}
        new_ids = {n.id for n in repo.get_notes_by_artifact_id(db_session, task.artifact_id)}
        result = detect_drift(old_ids, new_ids, task.id, task.artifact_id)
        assert result is None

    def test_drift_detected_when_artifact_id_misrouted(self, db_session):
        task = Task(name="drift mismatch")
        db_session.add(task)
        db_session.flush()
        wrong_aid = str(uuid.uuid4())
        note = Note(
            note_type=NoteType.INVESTIGATION,
            content="misrouted",
            task_id=task.id,
            artifact_id=wrong_aid,  # wrong — doesn't match task.artifact_id
            artifact_type="task",
        )
        db_session.add(note)
        db_session.flush()
        repo = NoteRepository()
        old_ids = {n.id for n in repo.get_for_task(db_session, task.id)}
        new_ids = {n.id for n in repo.get_notes_by_artifact_id(db_session, task.artifact_id)}
        result = detect_drift(old_ids, new_ids, task.id, task.artifact_id)
        assert result is not None
        assert note.id in result["missing_from_new"]

    def test_detect_drift_returns_none_for_empty_sets(self):
        result = detect_drift(set(), set(), 999, str(uuid.uuid4()))
        assert result is None


class TestNoToonInTools:
    def test_tool_files_do_not_import_toon(self):
        """After Phase 4: no tool file should import from toon."""
        import pathlib

        tools_dir = pathlib.Path(__file__).parent.parent.parent / "src/wizard/tools"
        for f in tools_dir.glob("*.py"):
            src = f.read_text()
            assert "from ..toon" not in src, f"{f.name} still imports toon"
            assert "import toon" not in src, f"{f.name} still imports toon"
