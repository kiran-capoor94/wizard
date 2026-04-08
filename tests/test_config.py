import json
import os
import pytest
from pathlib import Path


def test_config_path_returns_dev_path_by_default(monkeypatch):
    monkeypatch.delenv("WIZARD_ENV", raising=False)
    monkeypatch.delenv("WIZARD_CONFIG_FILE", raising=False)

    from src.config import _config_path

    result = _config_path()

    assert result == Path(__file__).parent.parent / "config.json"


def test_config_path_returns_prod_path(monkeypatch):
    monkeypatch.setenv("WIZARD_ENV", "production")
    monkeypatch.delenv("WIZARD_CONFIG_FILE", raising=False)

    from src.config import _config_path

    result = _config_path()

    assert result == Path.home() / ".wizard" / "config.json"


def test_config_path_override_takes_precedence(monkeypatch, tmp_path):
    override = str(tmp_path / "custom.json")
    monkeypatch.setenv("WIZARD_CONFIG_FILE", override)

    from src.config import _config_path

    result = _config_path()

    assert result == Path(override)


def test_settings_loads_values_from_json(monkeypatch, tmp_path):
    config = {"name": "My Server", "version": "2.0.0", "log_level": "DEBUG"}
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(config_file))

    # Force reimport so settings_customise_sources picks up the new env var
    import importlib
    import src.config
    importlib.reload(src.config)
    from src.config import Settings

    settings = Settings()

    assert settings.name == "My Server"
    assert settings.version == "2.0.0"
    assert settings.log_level == "DEBUG"


def test_settings_uses_defaults_when_config_file_missing(monkeypatch, tmp_path):
    missing = tmp_path / "nonexistent.json"
    monkeypatch.setenv("WIZARD_CONFIG_FILE", str(missing))

    import importlib
    import src.config
    importlib.reload(src.config)
    from src.config import Settings

    settings = Settings()

    assert settings.name == "Wizard MCP Server"
    assert settings.version == "1.2.0"
    assert settings.log_level == "INFO"
