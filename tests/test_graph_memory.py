import json
from datetime import datetime
from unittest.mock import MagicMock

from wizard.exceptions import GraphitiUnavailable
from wizard.graph_memory import (
    GraphMemoryService, episode_uuid, parse_episode_uuid, note_body,
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


def test_push_episode_noop_when_disabled():
    client = MagicMock()
    GraphMemoryService(client=client, enabled=False).push_episode(
        "note", 42, '{"kind":"note"}', "note 42", datetime(2026, 7, 28))
    client.add_episode.assert_not_called()


def test_push_episode_swallows_unavailable():
    client = MagicMock()
    client.add_episode.side_effect = GraphitiUnavailable("down")
    # must not raise
    GraphMemoryService(client=client, enabled=True).push_episode(
        "note", 42, '{"kind":"note"}', "note 42", datetime(2026, 7, 28))
    client.add_episode.assert_called_once()


def test_is_reachable_false_on_unavailable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    assert GraphMemoryService(client=client, enabled=True).is_reachable() is False
