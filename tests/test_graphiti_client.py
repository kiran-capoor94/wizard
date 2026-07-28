import json
from datetime import datetime

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
        uuid="wizard-note-42", source_description="wizard:note",
    )
    assert seen["url"] == "http://graph.test/messages"
    assert seen["json"]["group_id"] == "wizard"
    assert seen["json"]["messages"][0]["uuid"] == "wizard-note-42"


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
        uuid="wizard-note-42", source_description="wizard:note",
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
        uuid="wizard-note-42", source_description="wizard:note",
    )
    assert seen["url"] == "http://graph.test/messages"
    payload = seen["json"]
    assert set(payload.keys()) == {"group_id", "messages"}
    message = payload["messages"][0]
    assert set(message.keys()) == {
        "content", "role_type", "role", "name", "timestamp",
        "source_description", "uuid",
    }
    assert message["timestamp"] == reference_time.isoformat()


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
            uuid="wizard-note-42", source_description="wizard:note",
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
