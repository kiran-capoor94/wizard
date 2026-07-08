"""Scenario: caveman is the default mode applied on session_start."""
from wizard.config import ModesSettings


def test_modes_settings_default_is_caveman():
    """ModesSettings.default is caveman out of the box."""
    m = ModesSettings()
    assert m.default == "caveman"


async def test_session_start_applies_caveman_default_mode(mcp_client):
    """session_start's _apply_default_mode wiring actually sets active_mode —
    checking ModesSettings in isolation (above) doesn't exercise this at all;
    an inverted condition or wrong settings path there would ship undetected."""
    r = await mcp_client.call_tool("session_start", {})
    assert not r.is_error, r
    assert r.structured_content["active_mode"] == "caveman"
