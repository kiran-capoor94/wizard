import json
import sys
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

runner = CliRunner()


def _fresh_app(wizard_dir: Path):
    """Return a context manager that patches WIZARD_HOME and yields a fresh app."""
    # Ensure the module is not cached so patch triggers a fresh import
    sys.modules.pop("wizard.cli.main", None)

    class _Ctx:
        def __enter__(self):
            self._patcher = patch("wizard.cli.main.WIZARD_HOME", wizard_dir)
            self._patcher.start()
            # Now import — module is freshly loaded with patch applied
            from wizard.cli.main import app

            self.app = app
            return self

        def __exit__(self, *exc):
            self._patcher.stop()

    return _Ctx()


def test_setup_creates_wizard_dir(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0
    assert wizard_dir.exists()
    assert (wizard_dir / "config.json").exists()


def test_setup_creates_default_config(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["setup"])

    config = json.loads((wizard_dir / "config.json").read_text())
    assert "jira" in config
    assert "notion" in config
    assert "scrubbing" in config


def test_setup_handles_missing_skills_source(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0


def test_setup_is_idempotent(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        runner.invoke(ctx.app, ["setup"])
        result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0
