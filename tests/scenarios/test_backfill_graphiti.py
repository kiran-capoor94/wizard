"""Scenario: `wizard backfill-graphiti` streams existing SQLite notes into the
shared Graphiti graph with deterministic uuids (idempotent, safe to re-run)."""
from unittest.mock import MagicMock

from wizard.cli.graphiti import run_backfill_graphiti
from wizard.models import Note, NoteType
from wizard.repositories import NoteRepository
from wizard.security import SecurityService


def test_backfill_noop_when_disabled(capsys):
    client = MagicMock()

    run_backfill_graphiti(client=client, enabled=False, db=None, security=None)

    client.add_episode.assert_not_called()
    assert "disabled" in capsys.readouterr().out.lower()


def test_backfill_pushes_note_episode(db_session):
    note_repo = NoteRepository()
    note = Note(
        note_type=NoteType.DECISION,
        content="Use WAL mode for the sqlite connection pool.",
        mental_model="WAL avoids writer starvation under concurrent readers.",
    )
    note_repo.save(db_session, note)
    db_session.commit()
    assert note.id is not None

    client = MagicMock()
    security = SecurityService(allowlist=[], enabled=True)

    run_backfill_graphiti(client=client, enabled=True, db=db_session, security=security)

    uuids = [c.kwargs["uuid"] for c in client.add_episode.call_args_list]
    assert f"wizard-note-{note.id}" in uuids
