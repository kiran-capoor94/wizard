from unittest.mock import patch

from tests.helpers import MockContext, mock_session


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# save_note
# ---------------------------------------------------------------------------


async def test_save_note_scrubs_and_persists(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
    from wizard.security import SecurityService
    from wizard.tools import save_note

    task = Task(name="fix auth", source_id="ENG-1")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="john@example.com found a bug",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.note_id is not None

    saved_note = db_session.get(Note, result.note_id)
    assert "john@example.com" not in saved_note.content
    assert "[EMAIL_1]" in saved_note.content


async def test_save_note_stores_mental_model_when_provided(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Race condition between token refresh and request",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model == "Race condition between token refresh and request"
    assert response.mental_model_saved is True


async def test_save_note_leaves_mental_model_null_when_not_provided(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        response = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="ref material",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, response.note_id)
    assert note is not None
    assert note.mental_model is None
    assert response.mental_model_saved is False


async def test_save_note_mental_model_saved_true_when_model_provided(db_session):
    from wizard.models import NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t2")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="some investigation",
            mental_model="State machine pattern",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.mental_model_saved is True


async def test_save_note_mental_model_saved_false_when_model_absent(db_session):
    from wizard.models import NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t3")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="some docs",
            mental_model=None,
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.mental_model_saved is False


async def test_save_note_updates_task_state(db_session):
    from wizard.models import NoteType, Task, TaskState
    from wizard.repositories import TaskStateRepository as _TaskStateRepo
    from wizard.tools import save_note

    def task_state_repo():
        return _TaskStateRepo()

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    # Pre-create the TaskState row so we can refresh it from the same session.
    task_state_repo().create_for_task(db_session, task)

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DECISION,
            content="d",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    state = db_session.get(TaskState, task.id)
    db_session.refresh(state)
    assert state is not None
    assert state.note_count == 1
    assert state.decision_count == 1
    assert state.last_note_at is not None


async def test_save_note_uses_session_id_from_ctx_state_when_set(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    await ctx.set_state("current_session_id", 42)

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="content",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id == 42


async def test_save_note_session_id_null_when_no_ctx_state(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()  # no set_state called

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="content",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.session_id is None


# --- elicitation: save_note ---


async def test_save_note_elicits_mental_model_for_investigation(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="I now understand the root cause is X")

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="looked at logs",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "I now understand the root cause is X"


async def test_save_note_elicits_mental_model_for_decision(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="We chose approach B for simplicity")

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DECISION,
            content="chose B",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "We chose approach B for simplicity"


async def test_save_note_does_not_elicit_for_docs_notes(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="should not be used")

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.DOCS,
            content="docs",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    # DOCS note: elicit should NOT have been called, mental_model stays None
    assert note.mental_model is None


async def test_save_note_mental_model_param_skips_elicitation(db_session):
    from wizard.models import Note, NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(elicit_response="this should not win")

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            mental_model="caller provided this",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note.mental_model == "caller provided this"


async def test_save_note_handles_elicit_failure_gracefully(db_session):
    from wizard.models import NoteType, Task, TaskStatus
    from wizard.tools import save_note

    task = Task(name="task", status=TaskStatus.IN_PROGRESS)
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext(supports_elicit=False)

    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="investigation",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    assert result.note_id is not None  # tool succeeded despite elicit failure


async def test_save_note_scrubs_mental_model_when_passed_directly(db_session):
    from wizard.models import Note, NoteType, Task
    from wizard.tools import save_note

    task = Task(name="t")
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    assert task.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.task_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
        from wizard.security import SecurityService
        result = await save_note(
            ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content="findings",
            mental_model="Spoke with john@example.com about the issue",
            t_repo=TaskRepository(),
            sec=SecurityService(),
            n_repo=NoteRepository(),
            t_state_repo=TaskStateRepository(),
        )

    note = db_session.get(Note, result.note_id)
    assert note is not None
    assert "john@example.com" not in note.mental_model
    assert "[EMAIL_1]" in note.mental_model
