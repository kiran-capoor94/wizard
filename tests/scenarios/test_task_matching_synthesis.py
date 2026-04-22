"""Scenario: task matching assigns task_id to synthesised notes."""

import pytest
from sqlmodel import select

from wizard.models import Note, WizardSession
from wizard.schemas import SynthesisNote
from wizard.synthesis import Synthesiser
from wizard.transcript import TranscriptReader


@pytest.mark.asyncio
async def test_synthesise_assigns_task_id_to_matching_note(
    db_session, task_repo, note_repo, security, seed_task
):
    task = await seed_task(name="Fix auth bug")

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        t_repo=task_repo,
        backend={"model": "mock"},
    )
    notes = [SynthesisNote(task_id=task.id, note_type="investigation", content="Fixed auth bug")]
    synthesiser._save_notes(db_session, notes, wizard_session, valid_task_ids={task.id})

    saved = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(saved) == 1
    assert saved[0].task_id == task.id


@pytest.mark.asyncio
async def test_synthesise_rejects_hallucinated_task_id(
    db_session, task_repo, note_repo, security, seed_task
):
    await seed_task(name="Real task")  # populates the DB so valid_task_ids is non-empty

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        t_repo=task_repo,
        backend={"model": "mock"},
    )
    notes = [SynthesisNote(task_id=9999, note_type="investigation", content="Work done")]
    # valid_task_ids does not include 9999 — simulates an LLM hallucination
    synthesiser._save_notes(db_session, notes, wizard_session, valid_task_ids={1})

    saved = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(saved) == 1
    assert saved[0].task_id is None  # hallucinated ID rejected, falls back to null
