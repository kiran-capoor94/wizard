"""Scenario tests for RegistrationService modes seeding."""
import json
from pathlib import Path

from wizard.services import WIZARD_MODES, RegistrationService


def _make_service(tmp_path: Path) -> RegistrationService:
    from unittest.mock import MagicMock
    settings = MagicMock()
    settings.db = str(tmp_path / "wizard.db")
    settings.model_dump.return_value = {
        "knowledge_store": {"type": "", "notion": {}, "obsidian": {}},
        "scrubbing": {"enabled": True, "allowlist": []},
        "synthesis": {"enabled": True, "backends": []},
        "modes": {"default": None, "allowed": []},
    }
    return RegistrationService(settings)


def test_wizard_modes_constant():
    """WIZARD_MODES contains the three canonical mode skill names."""
    assert set(WIZARD_MODES) == {"architect", "ideation", "product-owner"}


def test_initialize_config_seeds_modes_allowed(tmp_path):
    """initialize_config writes modes.allowed = WIZARD_MODES on first install."""
    svc = _make_service(tmp_path)
    svc.ensure_wizard_home()
    svc.initialize_config()

    config = json.loads((tmp_path / "config.json").read_text())
    assert config["modes"]["allowed"] == sorted(WIZARD_MODES)


def test_initialize_config_modes_default_is_null(tmp_path):
    """initialize_config never sets modes.default."""
    svc = _make_service(tmp_path)
    svc.ensure_wizard_home()
    svc.initialize_config()

    config = json.loads((tmp_path / "config.json").read_text())
    assert config["modes"]["default"] is None


def test_initialize_config_does_not_overwrite_existing(tmp_path):
    """initialize_config is a no-op when config.json already exists."""
    svc = _make_service(tmp_path)
    svc.ensure_wizard_home()
    existing = {"modes": {"default": None, "allowed": ["my-custom-mode"]}}
    (tmp_path / "config.json").write_text(json.dumps(existing))

    svc.initialize_config()

    config = json.loads((tmp_path / "config.json").read_text())
    assert config["modes"]["allowed"] == ["my-custom-mode"]
