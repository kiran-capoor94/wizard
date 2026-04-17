# ---------------------------------------------------------------------------
# TaskStateRepository
# ---------------------------------------------------------------------------

class TestTaskStateRepository:
    def test_create_for_task_initialises_zero_state(self, db_session):
        from wizard.models import Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        state = repo.create_for_task(db_session, task)

        assert state.task_id == task.id
        assert state.note_count == 0
        assert state.decision_count == 0
        assert state.last_note_at is None
        assert state.last_status_change_at is None
        assert state.last_touched_at == task.created_at
        assert state.stale_days >= 0

    def test_create_for_task_persists_row(self, db_session):
        from wizard.models import Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        loaded = db_session.get(TaskState, task.id)
        assert loaded is not None
        assert loaded.task_id == task.id

    def test_on_note_saved_increments_note_count(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        note = Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id)
        db_session.add(note)
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1
        assert state.decision_count == 0
        assert state.last_note_at == note.created_at
        assert state.last_touched_at == note.created_at

    def test_on_note_saved_counts_decisions(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        for nt, content in [
            (NoteType.INVESTIGATION, "i1"),
            (NoteType.DECISION, "d1"),
            (NoteType.DECISION, "d2"),
            (NoteType.DOCS, "doc1"),
        ]:
            db_session.add(Note(note_type=nt, content=content, task_id=task.id))
            db_session.flush()
            repo.on_note_saved(db_session, task.id)

        from wizard.models import TaskState
        state = db_session.get(TaskState, task.id)
        assert state is not None
        assert state.note_count == 4
        assert state.decision_count == 2

    def test_on_note_saved_does_not_touch_last_status_change_at(self, db_session):
        import datetime as _dt

        from wizard.models import Note, NoteType, Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        sentinel = _dt.datetime(2020, 1, 1, 12, 0, 0)
        state = db_session.get(TaskState, task.id)
        assert state is not None
        state.last_status_change_at = sentinel
        db_session.add(state)
        db_session.flush()

        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="x", task_id=task.id))
        db_session.flush()
        result = repo.on_note_saved(db_session, task.id)

        assert result.last_status_change_at == sentinel

    def test_on_note_saved_dual_lookup_finds_jira_anchored_notes(self, db_session):
        from wizard.models import Note, NoteType, Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t", source_id="AUTH-123", source_type="JIRA")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        # Note attached only by source_id (not task_id) — simulates an
        # earlier note saved before the task row existed locally.
        db_session.add(Note(
            note_type=NoteType.INVESTIGATION,
            content="historical",
            source_id="AUTH-123",
            source_type="JIRA",
        ))
        db_session.flush()

        state = repo.on_note_saved(db_session, task.id)
        assert state.note_count == 1

    def test_on_status_changed_sets_timestamp_and_preserves_other_fields(self, db_session):
        import datetime as _dt

        from wizard.models import Note, NoteType, Task, TaskState
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None
        repo = TaskStateRepository()
        repo.create_for_task(db_session, task)

        db_session.add(Note(note_type=NoteType.INVESTIGATION, content="i", task_id=task.id))
        db_session.add(Note(note_type=NoteType.DECISION, content="d", task_id=task.id))
        db_session.flush()
        repo.on_note_saved(db_session, task.id)

        before = db_session.get(TaskState, task.id)
        assert before is not None
        old_note_count = before.note_count
        old_decision_count = before.decision_count
        old_last_note_at = before.last_note_at
        old_last_touched_at = before.last_touched_at
        old_stale_days = before.stale_days

        result = repo.on_status_changed(db_session, task.id)

        assert result.last_status_change_at is not None
        assert (_dt.datetime.now() - result.last_status_change_at).total_seconds() < 5
        assert result.note_count == old_note_count
        assert result.decision_count == old_decision_count
        assert result.last_note_at == old_last_note_at
        assert result.last_touched_at == old_last_touched_at
        assert result.stale_days == old_stale_days

    def test_on_status_changed_creates_state_if_missing(self, db_session):
        from wizard.models import Task
        from wizard.repositories import TaskStateRepository
        task = Task(name="t")
        db_session.add(task)
        db_session.flush()
        assert task.id is not None

        repo = TaskStateRepository()
        result = repo.on_status_changed(db_session, task.id)
        assert result.task_id == task.id
        assert result.last_status_change_at is not None
