"""Scenario: `wizard backfill-graphiti` streams existing SQLite notes into the
shared Graphiti graph, carrying the namespaced identity in each episode's
`name`. NOT idempotent — graphiti-core 0.22.0 has no uuid upsert, so re-running
creates duplicates (see wizard.cli.graphiti).

Also covers the batch pacing added after the first live backfill OOM-killed
the shared Graphiti service: firing all episodes with no backpressure let a
serial worker fall behind an unbounded in-memory queue. `_paced_push` batches
submissions and sleeps between batches so the worker can drain.
"""
import json
from unittest.mock import MagicMock

from wizard.cli.graphiti import _paced_push, run_backfill_graphiti
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

    # identity now travels in `name` — no uuid is sent (see GraphitiClient)
    uuids = [c.kwargs["name"] for c in client.add_episode.call_args_list]
    assert f"wizard-note-{note.id}" in uuids


def test_paced_push_batches_and_sleeps_between_but_not_after_last_batch():
    client = MagicMock()
    episodes = [
        {
            "name": f"note {i}", "body": "b", "reference_time": None,
            "uuid": f"wizard-note-{i}", "source_description": "wizard:note",
        }
        for i in range(60)
    ]
    sleep = MagicMock()

    pushed = _paced_push(client, episodes, batch_size=25, pause_seconds=5.0, sleep=sleep)

    assert pushed == 60
    assert client.add_episode.call_count == 60
    assert sleep.call_count == 2
    sleep.assert_called_with(5.0)


def test_paced_push_no_sleep_when_all_episodes_fit_in_one_batch():
    client = MagicMock()
    episodes = [
        {
            "name": "note 1", "body": "b", "reference_time": None,
            "uuid": "wizard-note-1", "source_description": "wizard:note",
        }
    ]
    sleep = MagicMock()

    pushed = _paced_push(client, episodes, batch_size=25, pause_seconds=5.0, sleep=sleep)

    assert pushed == 1
    sleep.assert_not_called()


def test_backfill_threads_pacing_settings_and_paces_between_batches(db_session):
    note_repo = NoteRepository()
    for i in range(3):
        note = Note(
            note_type=NoteType.DECISION,
            content=f"decision {i}",
            mental_model="model",
        )
        note_repo.save(db_session, note)
    db_session.commit()

    client = MagicMock()
    security = SecurityService(allowlist=[], enabled=True)
    sleep = MagicMock()

    run_backfill_graphiti(
        client=client, enabled=True, db=db_session, security=security,
        batch_size=2, pause_seconds=1.0, sleep=sleep,
    )

    assert client.add_episode.call_count == 3
    # 3 notes, batch_size=2 -> batches of [2, 1] -> exactly one pause between them.
    sleep.assert_called_once_with(1.0)


def test_backfill_handles_sessions_with_null_last_active_at(db_session):
    """last_active_at is nullable and NULL for every historical row. Using it
    directly as reference_time raised ValueError on the first session and
    aborted the whole command, so the meetings phase never ran either."""
    from wizard.models import WizardSession

    session = WizardSession(
        summary="Auto-closed session",
        session_state=json.dumps({
            "intent": "ship the thing", "state_delta": "shipped",
            "open_loops": [], "next_actions": [], "closure_status": "clean",
        }),
        last_active_at=None,
    )
    db_session.add(session)
    db_session.commit()
    assert session.last_active_at is None

    client = MagicMock()
    security = SecurityService(allowlist=[], enabled=True)

    run_backfill_graphiti(client=client, enabled=True, db=db_session, security=security)

    names = [c.kwargs["name"] for c in client.add_episode.call_args_list]
    assert f"wizard-session-{session.id}" in names


def test_one_failing_phase_does_not_abort_the_others(db_session, capsys):
    """A malformed historical row in one phase must not cost the other phases."""
    note_repo = NoteRepository()
    note_repo.save(db_session, Note(note_type=NoteType.DECISION, content="c"))
    db_session.commit()

    client = MagicMock()
    security = SecurityService(allowlist=[], enabled=True)

    import wizard.cli.graphiti as g

    original = g._backfill_sessions
    g._backfill_sessions = MagicMock(side_effect=ValueError("boom"))
    try:
        run_backfill_graphiti(client=client, enabled=True, db=db_session, security=security)
    finally:
        g._backfill_sessions = original

    out = capsys.readouterr()
    # notes ran before the failing phase, meetings ran after it
    assert "1 note episode(s)" in out.out
    assert "0 session episode(s)" in out.out
    assert "session phase FAILED" in out.err
