"""Scenario: task matching assigns task_id to synthesised notes."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from sqlmodel import select

from wizard.config import settings
from wizard.models import Note, Task, WizardSession
from wizard.schemas import SynthesisNote
from wizard.synthesis import Synthesiser
from wizard.transcript import TranscriptReader


def _make_synthesiser(note_repo, security, task_repo=None):
    return Synthesiser(
        reader=TranscriptReader(),
        note_repo=note_repo,
        security=security,
        settings=settings,
        t_repo=task_repo,
        backend={"model": "mock"},
    )


def _write_jsonl(lines: list[dict]) -> str:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    ) as f:
        for line in lines:
            f.write(json.dumps(line) + "\n")
        return f.name


def test_synthesise_assigns_task_id_to_matching_note(db_session, task_repo, note_repo, security):
    task = Task(name="Fix auth bug")
    db_session.add(task)
    db_session.flush()
    db_session.refresh(task)

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    assert task.id is not None
    synthesiser = _make_synthesiser(note_repo, security, task_repo)
    llm_response = [SynthesisNote(task_id=task.id, note_type="investigation", content="Fixed auth bug")]

    tmp = _write_jsonl([{"type": "user", "content": "Fixed auth bug"}])
    try:
        with patch("wizard.synthesis.llm_complete", return_value=llm_response):
            synthesiser.synthesise_path(db_session, wizard_session, Path(tmp), terminal=True)
    finally:
        os.unlink(tmp)

    saved = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(saved) == 1
    assert saved[0].task_id == task.id


def test_synthesise_rejects_hallucinated_task_id(db_session, task_repo, note_repo, security):
    # A real task in the DB so the open-tasks table is non-empty
    real_task = Task(name="Real task")
    db_session.add(real_task)
    db_session.flush()
    db_session.refresh(real_task)

    wizard_session = WizardSession(agent="claude-code")
    db_session.add(wizard_session)
    db_session.flush()
    db_session.refresh(wizard_session)

    synthesiser = _make_synthesiser(note_repo, security, task_repo)
    # LLM returns task_id=9999 which is not in open tasks — hallucination
    llm_response = [SynthesisNote(task_id=9999, note_type="investigation", content="Work done")]

    tmp = _write_jsonl([{"type": "user", "content": "Work done"}])
    try:
        with patch("wizard.synthesis.llm_complete", return_value=llm_response):
            synthesiser.synthesise_path(db_session, wizard_session, Path(tmp), terminal=True)
    finally:
        os.unlink(tmp)

    saved = list(
        db_session.execute(
            select(Note).where(Note.session_id == wizard_session.id)
        ).scalars().all()
    )
    assert len(saved) == 1
    assert saved[0].task_id is None  # hallucinated ID rejected, falls back to null
