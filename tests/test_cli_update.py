import shutil
from pathlib import Path
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
