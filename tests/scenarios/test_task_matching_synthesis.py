"""Scenario: task matching assigns task_id to synthesised notes."""

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import select

from wizard.models import Note, WizardSession
from wizard.schemas import SynthesisNote
from wizard.transcript import OllamaSynthesiser, TranscriptEntry, TranscriptReader


@pytest.mark.asyncio
async def test_get_open_tasks_compact_returns_id_name_pairs(
    db_session, task_repo, seed_task
):
    task = await seed_task(name="Fix auth bug")
    results = task_repo.get_open_tasks_compact(db_session)
    assert len(results) == 1
    assert results[0] == (task.id, "Fix auth bug")


@pytest.mark.asyncio
async def test_get_open_tasks_compact_excludes_done_tasks(
    db_session, task_repo, seed_task
):
    await seed_task(name="Done task", status="done")
    await seed_task(name="Open task", status="todo")
    results = task_repo.get_open_tasks_compact(db_session)
    names = [r[1] for r in results]
    assert "Open task" in names
    assert "Done task" not in names


@pytest.mark.asyncio
async def test_synthesise_path_assigns_task_id_to_matching_note(
    db_session, task_repo, note_repo, security, seed_task
):
    task = await seed_task(name="Fix auth bug")

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = OllamaSynthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        t_repo=task_repo,
    )
    fake_entries = [TranscriptEntry(role="assistant", content="Fixed auth bug")]
    fake_notes = [
        SynthesisNote(task_id=task.id, note_type="investigation", content="Fixed auth bug")
    ]
    with patch.object(synthesiser._reader, "read", return_value=fake_entries), \
         patch.object(synthesiser, "_call_ollama", return_value=fake_notes):
        result = synthesiser.synthesise_path(db_session, wizard_session, Path("dummy.jsonl"))

    assert result.notes_created == 1
    notes = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(notes) == 1
    assert notes[0].task_id == task.id


@pytest.mark.asyncio
async def test_synthesise_path_rejects_hallucinated_task_id(
    db_session, task_repo, note_repo, security, seed_task
):
    await seed_task(name="Real task")  # populates valid task IDs

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = OllamaSynthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        t_repo=task_repo,
    )
    fake_entries = [TranscriptEntry(role="assistant", content="Some work")]
    fake_notes = [
        SynthesisNote(task_id=9999, note_type="investigation", content="Work done")
    ]
    with patch.object(synthesiser._reader, "read", return_value=fake_entries), \
         patch.object(synthesiser, "_call_ollama", return_value=fake_notes):
        synthesiser.synthesise_path(db_session, wizard_session, Path("dummy.jsonl"))

    notes = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(notes) == 1
    assert notes[0].task_id is None  # hallucinated ID rejected, falls back to null
