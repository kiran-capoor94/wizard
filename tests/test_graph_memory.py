import json
from datetime import datetime
from unittest.mock import MagicMock

from wizard.exceptions import GraphitiUnavailable
from wizard.graph_memory import (
    GraphMemoryService,
    episode_uuid,
    note_body,
    parse_episode_uuid,
)
from wizard.schemas import SearchResult


def _sr(eid: int) -> SearchResult:
    return SearchResult(entity_type="note", entity_id=eid, title="t", snippet="s")


def test_uuid_round_trip():
    assert episode_uuid("note", 42) == "wizard-note-42"
    assert parse_episode_uuid("wizard-note-42") == ("note", 42)


def test_parse_rejects_foreign_uuids():
    assert parse_episode_uuid("kiranos-idea-9") is None
    assert parse_episode_uuid("garbage") is None
    assert parse_episode_uuid("wizard-note-notanint") is None


def test_parse_rejects_task_uuids():
    # Tasks are never written to Graphiti (no dual-write path exists for
    # them), so a "wizard-task-*" uuid can never legitimately be a graph
    # hit — it must be dropped rather than treated as valid-but-unfindable.
    assert parse_episode_uuid("wizard-task-5") is None


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


def test_search_uses_graphiti_when_reachable():
    client = MagicMock()
    client.health.return_value = True
    client.search.return_value = ["wizard-note-42", "kiranos-idea-9", "wizard-note-7"]
    svc = GraphMemoryService(client=client, enabled=True)

    captured = {}
    def fetch_display(db, pairs):
        captured["pairs"] = pairs
        return [_sr(42), _sr(7)]
    repo = MagicMock()

    out = svc.search(db=None, query="q", limit=10, entity_type=None,
                     search_repo=repo, fetch_display=fetch_display)
    # foreign uuid dropped; order preserved
    assert captured["pairs"] == [("note", 42), ("note", 7)]
    assert [r.entity_id for r in out] == [42, 7]
    repo.hybrid_search.assert_not_called()


def test_search_falls_back_when_unreachable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    repo = MagicMock()
    repo.hybrid_search.return_value = [_sr(1)]
    svc = GraphMemoryService(client=client, enabled=True)

    out = svc.search(db=None, query="q", limit=10, entity_type=None,
                     search_repo=repo, fetch_display=lambda db, p: [])
    assert [r.entity_id for r in out] == [1]
    repo.hybrid_search.assert_called_once()
