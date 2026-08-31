import json
from datetime import datetime
from unittest.mock import MagicMock

from wizard.exceptions import GraphitiUnavailable
from wizard.graph_memory import (
    GraphMemoryService,
    episode_uuid,
    fact_to_search_result,
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
        "note", 42, '{"kind":"note"}', datetime(2026, 7, 28))
    client.add_episode.assert_not_called()


def test_push_episode_swallows_unavailable():
    client = MagicMock()
    client.add_episode.side_effect = GraphitiUnavailable("down")
    # must not raise
    GraphMemoryService(client=client, enabled=True).push_episode(
        "note", 42, '{"kind":"note"}', datetime(2026, 7, 28))
    client.add_episode.assert_called_once()


def test_is_reachable_false_on_unavailable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    assert GraphMemoryService(client=client, enabled=True).is_reachable() is False


def test_search_uses_graphiti_when_reachable():
    client = MagicMock()
    client.health.return_value = True
    client.search.return_value = [
        {"name": "n", "fact": "WAL contention", "valid_at": "2026-07-28T00:00:00"},
    ]
    svc = GraphMemoryService(client=client, enabled=True)
    repo = MagicMock()

    out = svc.search(db=None, query="q", limit=10, entity_type=None, search_repo=repo)
    assert len(out) == 1
    result = out[0]
    assert result.entity_type == "fact"
    assert result.entity_id is None
    assert result.snippet == "WAL contention"
    repo.hybrid_search.assert_not_called()


def test_search_falls_back_when_unreachable():
    client = MagicMock()
    client.health.side_effect = GraphitiUnavailable("down")
    repo = MagicMock()
    repo.hybrid_search.return_value = [_sr(1)]
    svc = GraphMemoryService(client=client, enabled=True)

    out = svc.search(db=None, query="q", limit=10, entity_type=None, search_repo=repo)
    assert [r.entity_id for r in out] == [1]
    repo.hybrid_search.assert_called_once()


def test_search_falls_back_when_client_raises_mid_search():
    # Distinct from test_search_falls_back_when_unreachable: health check
    # succeeds (is_reachable() is True) but the subsequent client.search()
    # call itself raises — the mid-search except branch, not the
    # unreachable-short-circuit branch.
    client = MagicMock()
    client.health.return_value = True
    client.search.side_effect = GraphitiUnavailable("down mid-search")
    repo = MagicMock()
    repo.hybrid_search.return_value = [_sr(1)]
    svc = GraphMemoryService(client=client, enabled=True)

    out = svc.search(db=None, query="q", limit=10, entity_type=None, search_repo=repo)
    assert out == repo.hybrid_search.return_value
    repo.hybrid_search.assert_called_once()


def test_fact_to_search_result_maps_fields():
    result = fact_to_search_result({
        "name": "n1", "fact": "note_42 mentions WAL", "valid_at": "2026-07-28T00:00:00",
    })
    assert result.entity_type == "fact"
    assert result.entity_id is None
    assert result.title == "n1"
    assert result.snippet == "note_42 mentions WAL"
    assert result.created_at is not None


def test_fact_to_search_result_prefers_created_at_when_no_valid_at():
    result = fact_to_search_result({
        "name": "n1", "fact": "f", "created_at": "2026-07-28T00:00:00",
    })
    assert result.created_at is not None


def test_fact_to_search_result_handles_missing_fields_without_raising():
    result = fact_to_search_result({})
    assert result.entity_type == "fact"
    assert result.entity_id is None
    assert result.title == "fact"
    assert result.snippet == ""
    assert result.created_at is None


def test_fact_to_search_result_handles_unparseable_timestamp():
    result = fact_to_search_result({"name": "n", "fact": "f", "valid_at": "not-a-date"})
    assert result.created_at is None
