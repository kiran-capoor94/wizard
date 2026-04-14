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
    from unittest.mock import MagicMock, call
    from wizard.cli.main import _run_update_step

    mock_result = MagicMock(returncode=0, stdout="", stderr="")
    with patch("wizard.cli.main.subprocess.run", return_value=mock_result) as mock_run:
        _run_update_step("label", ["cmd"], tmp_path)

    mock_run.assert_called_once_with(
        ["cmd"], cwd=tmp_path, capture_output=True, text=True
    )
