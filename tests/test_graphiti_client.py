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
    import json

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


def test_search_returns_uuids_in_order():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [
            {"uuid": "wizard-note-42"}, {"uuid": "wizard-session-5"}]})

    assert _client(handler).search("db lock", limit=10) == [
        "wizard-note-42", "wizard-session-5"]


def test_connection_error_raises_graphiti_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(GraphitiUnavailable):
        _client(handler).health()
