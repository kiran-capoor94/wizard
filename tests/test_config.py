from wizard.config import Settings


def test_graphiti_defaults_are_inert():
    s = Settings()
    assert s.graphiti.enabled is False
    assert s.graphiti.url == "http://localhost:8000"
    assert s.graphiti.group_id == "wizard"
    assert s.graphiti.timeout_seconds == 2.0
    assert s.graphiti.health_ttl_seconds == 30.0
