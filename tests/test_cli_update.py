from unittest.mock import patch


def test_refresh_skills_copies_from_source(tmp_path):
    from wizard.cli.main import _refresh_skills

    source = tmp_path / "source_skills"
    source.mkdir()
    (source / "session-start").mkdir()
    (source / "session-start" / "SKILL.md").write_text("skill")
    dest = tmp_path / "dest_skills"

    with patch("wizard.cli.main._package_skills_dir", return_value=source):
        _refresh_skills(dest)

    assert (dest / "session-start" / "SKILL.md").exists()


def test_refresh_skills_overwrites_existing_dest(tmp_path):
    from wizard.cli.main import _refresh_skills

    source = tmp_path / "source_skills"
    source.mkdir()
    (source / "new-skill").mkdir()
    (source / "new-skill" / "SKILL.md").write_text("new")
    dest = tmp_path / "dest_skills"
    dest.mkdir()
    (dest / "old-skill").mkdir()

    with patch("wizard.cli.main._package_skills_dir", return_value=source):
        _refresh_skills(dest)

    assert (dest / "new-skill" / "SKILL.md").exists()
    assert not (dest / "old-skill").exists()


def test_refresh_skills_noop_when_source_missing(tmp_path):
    from wizard.cli.main import _refresh_skills

    missing_source = tmp_path / "nonexistent"
    dest = tmp_path / "dest"

    with patch("wizard.cli.main._package_skills_dir", return_value=missing_source):
        _refresh_skills(dest)

    assert not dest.exists()


def test_run_update_step_returns_true_on_success(tmp_path):
    from unittest.mock import MagicMock
    from wizard.cli.main import _run_update_step

    mock_result = MagicMock(returncode=0, stdout="all good\n", stderr="")
    with patch("wizard.cli.main.subprocess.run", return_value=mock_result):
        ok, output = _run_update_step("test step", ["echo", "hi"], tmp_path)

    assert ok is True
    assert "all good" in output


def test_run_update_step_returns_false_on_failure(tmp_path):
    from unittest.mock import MagicMock
    from wizard.cli.main import _run_update_step

    mock_result = MagicMock(returncode=1, stdout="", stderr="fatal: not a git repo\n")
    with patch("wizard.cli.main.subprocess.run", return_value=mock_result):
        ok, output = _run_update_step("git pull", ["git", "pull"], tmp_path)

    assert ok is False
    assert "fatal: not a git repo" in output


def test_run_update_step_passes_cwd_to_subprocess(tmp_path):
    from unittest.mock import MagicMock
    from wizard.cli.main import _run_update_step

    mock_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("wizard.cli.main.subprocess.run", return_value=mock_result) as mock_run:
        _run_update_step("label", ["cmd"], tmp_path)

    mock_run.assert_called_once_with(
        ["cmd"], cwd=tmp_path, capture_output=True, text=True
    )


import sys
from typer.testing import CliRunner

runner = CliRunner()


def _fresh_update_app(wizard_dir):
    """Return a context manager that patches WIZARD_HOME and yields a fresh app."""
    class _Ctx:
        def __enter__(self):
            sys.modules.pop("wizard.cli.main", None)
            self._patcher = patch("wizard.cli.main.WIZARD_HOME", wizard_dir)
            self._patcher.start()
            from wizard.cli.main import app
            self.app = app
            return self

        def __exit__(self, *_):
            self._patcher.stop()

    return _Ctx()


def test_update_runs_all_three_subprocess_steps(tmp_path):
    from unittest.mock import MagicMock

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    mock_step = MagicMock(return_value=(True, ""))
    mock_refresh = MagicMock()

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", mock_step),
            patch("wizard.cli.main._refresh_skills", mock_refresh),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            result = runner.invoke(ctx.app, ["update"])

    assert result.exit_code == 0
    assert mock_step.call_count == 3
    mock_refresh.assert_called_once()


def test_update_uses_uv_sync_when_uv_available(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    captured_calls = []

    def capturing_step(label, args, _cwd):
        captured_calls.append((label, args))
        return True, ""

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=capturing_step),
            patch("wizard.cli.main._refresh_skills"),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            runner.invoke(ctx.app, ["update"])

    assert any(args == ["uv", "sync"] for _, args in captured_calls)


def test_update_falls_back_to_pip_when_uv_missing(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    captured_calls = []

    def capturing_step(label, args, _cwd):
        captured_calls.append((label, args))
        return True, ""

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=capturing_step),
            patch("wizard.cli.main._refresh_skills"),
            patch("wizard.cli.main.shutil.which", return_value=None),
        ):
            runner.invoke(ctx.app, ["update"])

    assert any(
        args[0] == sys.executable and "-m" in args and "pip" in args
        for _, args in captured_calls
    )


def test_update_exits_1_on_step_failure(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()

    def failing_step(*_):
        return False, "fatal: not a git repo"

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=failing_step),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            result = runner.invoke(ctx.app, ["update"])

    assert result.exit_code == 1


def test_update_stops_after_first_failure(tmp_path):
    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    call_count = 0

    def step_that_fails_first(*_):
        nonlocal call_count
        call_count += 1
        return False, "error"

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=step_that_fails_first),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            runner.invoke(ctx.app, ["update"])

    assert call_count == 1
