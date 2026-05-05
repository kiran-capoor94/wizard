"""Scenario: caveman is the default mode applied on session_start."""
from wizard.config import ModesSettings


def test_modes_settings_default_is_caveman():
    """ModesSettings.default is caveman out of the box."""
    m = ModesSettings()
    assert m.default == "caveman"
