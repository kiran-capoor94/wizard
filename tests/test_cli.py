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


import pytest


@pytest.mark.skip(reason="requires skills from Task 5")
def test_setup_copies_skills(tmp_path):
    wizard_dir = tmp_path / ".wizard"

    with _fresh_app(wizard_dir) as ctx:
        result = runner.invoke(ctx.app, ["setup"])

    assert result.exit_code == 0
    skills_dir = wizard_dir / "skills"
    assert skills_dir.exists()
    assert (skills_dir / "session-start" / "SKILL.md").exists()
    assert (skills_dir / "task-start" / "SKILL.md").exists()
    assert (skills_dir / "note" / "SKILL.md").exists()
    assert (skills_dir / "meeting" / "SKILL.md").exists()
    assert (skills_dir / "code-review" / "SKILL.md").exists()
    assert (skills_dir / "architecture-debate" / "SKILL.md").exists()
    assert (skills_dir / "session-end" / "SKILL.md").exists()


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


# --- sync command tests ---

from unittest.mock import MagicMock


def test_sync_calls_sync_all(db_session):
    from tests.helpers import mock_session

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = []

    with (
        patch("wizard.deps.sync_service", return_value=sync_mock),
        patch("wizard.database.get_session", mock_session(db_session)),
    ):
        from wizard.cli.main import app

        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    sync_mock.sync_all.assert_called_once()


def test_sync_reports_results(db_session):
    from wizard.schemas import SourceSyncStatus
    from tests.helpers import mock_session

    sync_mock = MagicMock()
    sync_mock.sync_all.return_value = [
        SourceSyncStatus(source="jira", ok=True),
        SourceSyncStatus(source="notion_tasks", ok=False, error="timeout"),
    ]

    with (
        patch("wizard.deps.sync_service", return_value=sync_mock),
        patch("wizard.database.get_session", mock_session(db_session)),
    ):
        from wizard.cli.main import app

        result = runner.invoke(app, ["sync"])

    assert result.exit_code == 0
    assert "jira" in result.output.lower()
    assert "notion_tasks" in result.output.lower()
    assert "timeout" in result.output.lower()
