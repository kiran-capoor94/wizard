import json

from wizard.graph_memory import (
    episode_uuid, parse_episode_uuid, note_body,
)


def test_uuid_round_trip():
    assert episode_uuid("note", 42) == "wizard-note-42"
    assert parse_episode_uuid("wizard-note-42") == ("note", 42)


def test_parse_rejects_foreign_uuids():
    assert parse_episode_uuid("kiranos-idea-9") is None
    assert parse_episode_uuid("garbage") is None
    assert parse_episode_uuid("wizard-note-notanint") is None


def test_note_body_encodes_supersedes_uuid():
    body = json.loads(note_body(
        note_type="DECISION", content="use WAL", mental_model="lock contention",
        task_id=17, session_id=5, supersedes_note_id=39,
    ))
    assert body == {
        "kind": "note", "id": None, "note_type": "DECISION", "content": "use WAL",
        "mental_model": "lock contention", "task_id": 17, "session_id": 5,
        "supersedes": "wizard-note-39",
    }
