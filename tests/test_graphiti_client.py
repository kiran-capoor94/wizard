import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from wizard.exceptions import GraphitiUnavailable
from wizard.integrations.graphiti import GraphitiClient


def _client(handler) -> GraphitiClient:
    c = GraphitiClient(url="http://graph.test", group_id="wizard", timeout_seconds=1.0)
    c._transport = httpx.MockTransport(handler)  # test seam
    return c


def test_add_episode_posts_expected_payload():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).add_episode(
        name="note 42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        source_description="wizard:note",
    )
    assert seen["url"] == "http://graph.test/messages"
    assert seen["json"]["group_id"] == "wizard"
    assert seen["json"]["messages"][0]["name"] == "note 42"


def test_search_returns_facts():
    facts = [
        {
            "uuid": "e1", "name": "n1", "fact": "note_42 mentions WAL",
            "created_at": "2026-07-28T00:00:00", "valid_at": "2026-07-28T00:00:00",
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"facts": facts})

    assert _client(handler).search("db lock", limit=10) == facts


def test_connection_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(GraphitiUnavailable):
        _client(handler).health()


def test_add_episode_role_type_is_user():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).add_episode(
        name="note 42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        source_description="wizard:note",
    )
    message = seen["json"]["messages"][0]
    # graphiti-core 0.22.0 422s on any role_type other than "user".
    assert message["role_type"] == "user"
    # server also requires a non-empty "role" (distinct from "role_type").
    assert message["role"]


def test_add_episode_full_message_shape():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    reference_time = datetime(2026, 7, 28, 12, 0, 0)
    _client(handler).add_episode(
        name="note 42", body='{"kind":"note"}',
        reference_time=reference_time,
        source_description="wizard:note",
    )
    assert seen["url"] == "http://graph.test/messages"
    payload = seen["json"]
    assert set(payload.keys()) == {"group_id", "messages"}
    message = payload["messages"][0]
    assert set(message.keys()) == {
        "content", "role_type", "role", "name", "timestamp",
        "source_description",
    }
    # normalised to tz-aware UTC on the wire — see _as_utc
    assert message["timestamp"] == reference_time.astimezone(timezone.utc).isoformat()


def test_search_posts_group_ids_array_and_max_facts():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"facts": []})

    _client(handler).search("db lock", limit=7)
    assert seen["url"] == "http://graph.test/search"
    body = seen["json"]
    assert body["group_ids"] == ["wizard"]
    assert isinstance(body["group_ids"], list)
    assert body["max_facts"] == 7
    assert body["query"] == "db lock"


def test_search_reads_facts_key_not_results():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "results": [{"uuid": "x"}],
            "facts": [{"fact": "real"}],
        })

    # A regression that reads "results" instead of "facts" would return
    # [{"uuid": "x"}] (or silently the wrong shape) here — this fails loudly.
    assert _client(handler).search("q", limit=10) == [{"fact": "real"}]


def test_search_empty_when_facts_absent():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    assert _client(handler).search("q", limit=10) == []


def test_health_hits_healthcheck_route():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["method"] = request.method
        return httpx.Response(200)

    assert _client(handler).health() is True
    assert seen["url"] == "http://graph.test/healthcheck"
    assert seen["method"] == "GET"


def test_add_episode_http_status_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    with pytest.raises(GraphitiUnavailable):
        _client(handler).add_episode(
            name="note 42", body='{"kind":"note"}',
            reference_time=datetime(2026, 7, 28, 12, 0, 0),
            source_description="wizard:note",
        )


def test_search_http_status_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "unprocessable"})

    with pytest.raises(GraphitiUnavailable):
        _client(handler).search("q", limit=10)


def test_health_http_status_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(GraphitiUnavailable):
        _client(handler).health()


def test_add_episode_uses_write_timeout_search_uses_read_timeout(monkeypatch):
    seen_timeouts = []
    real_client = httpx.Client

    def recording_client(*args, **kwargs):
        seen_timeouts.append(kwargs["timeout"])
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", recording_client)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/messages":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(200, json={"facts": []})

    c = GraphitiClient(
        url="http://graph.test", group_id="wizard",
        timeout_seconds=1.0, write_timeout_seconds=30.0,
    )
    c._transport = httpx.MockTransport(handler)

    c.search("q", limit=10)
    c.add_episode(
        name="note 42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        source_description="wizard:note",
    )

    assert seen_timeouts[0] == 1.0
    assert seen_timeouts[1] == 30.0
    assert seen_timeouts[0] != seen_timeouts[1]


def test_write_timeout_defaults_to_read_timeout_when_not_given():
    c = GraphitiClient(url="http://graph.test", group_id="wizard", timeout_seconds=1.0)
    assert c._write_timeout == 1.0
    assert c._read_timeout == 1.0


# --- uuid must never be sent (graphiti-core 0.22.0) --------------------------
# add_episode(uuid=...) is an UPDATE selector: graphiti.py:368 does
# EpisodicNode.get_by_uuid(uuid) and raises NodeNotFoundError for a new
# episode. That escapes graph_service's worker() and kills the single async
# ingest consumer process-wide, so every later POST returns 202 into a dead
# queue. Verified live: with uuid, 0 nodes; without, episode + entities extract.
# /search returns EDGE uuids, never episode uuids, so sending one bought
# nothing on the read path either.

def test_add_episode_sends_no_uuid():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).add_episode(
        name="wizard-note-42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        source_description="wizard:note",
    )
    assert "uuid" not in seen["json"]["messages"][0]


def test_add_episode_carries_identity_in_name():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    _client(handler).add_episode(
        name="wizard-note-42", body='{"kind":"note"}',
        reference_time=datetime(2026, 7, 28, 12, 0, 0),
        source_description="wizard:note",
    )
    assert seen["json"]["messages"][0]["name"] == "wizard-note-42"


# --- timestamps must be timezone-aware UTC --------------------------------
# Wizard's SQLite timestamps come from datetime.now() — LOCAL and naive. Sent
# as-is, Graphiti stores a naive valid_at, and retrieve_episodes (which
# compares against an aware datetime.now(timezone.utc)) never matches them.
# Consequences: GET /episodes returns [] for the wizard partition, and
# add_episode's own previous-episodes lookup is always empty, so every episode
# is extracted with no prior context and no entity resolution against earlier
# ones. Verified live: kiranos episodes (aware) are returned, wizard's are not.

def test_add_episode_converts_naive_local_timestamp_to_utc():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    naive = datetime(2026, 7, 28, 12, 0, 0)  # local, no tzinfo
    _client(handler).add_episode(
        name="wizard-note-42", body="{}", reference_time=naive,
        source_description="wizard:note",
    )
    sent = seen["json"]["messages"][0]["timestamp"]
    parsed = datetime.fromisoformat(sent)
    assert parsed.tzinfo is not None, f"timestamp must be tz-aware, got {sent!r}"
    assert parsed.utcoffset() == timedelta(0), "must be normalised to UTC"
    assert parsed == naive.astimezone(timezone.utc)


def test_add_episode_normalises_an_aware_timestamp_to_utc():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"status": "ok"})

    aware = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    _client(handler).add_episode(
        name="wizard-note-42", body="{}", reference_time=aware,
        source_description="wizard:note",
    )
    parsed = datetime.fromisoformat(seen["json"]["messages"][0]["timestamp"])
    assert parsed.utcoffset() == timedelta(0)
    assert parsed == aware.astimezone(timezone.utc)


# --- existing episode names, for idempotent/resumable backfill ------------

def test_existing_episode_names_returns_the_set_of_names():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/episodes/wizard"
        return httpx.Response(200, json=[
            {"uuid": "a", "name": "wizard-note-1"},
            {"uuid": "b", "name": "wizard-note-2"},
        ])

    assert _client(handler).existing_episode_names(limit=500) == {
        "wizard-note-1", "wizard-note-2",
    }


def test_existing_episode_names_tolerates_entries_without_a_name():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"uuid": "a"}, {"uuid": "b", "name": "wizard-note-2"}])

    assert _client(handler).existing_episode_names(limit=500) == {"wizard-note-2"}


def test_existing_episode_names_raises_graphiti_unavailable_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(GraphitiUnavailable):
        _client(handler).existing_episode_names(limit=500)
