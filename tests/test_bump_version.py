# tests/test_bump_version.py
import os
import subprocess
import sys
from pathlib import Path

# Add scripts/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bump_version import (
    bump_version,
    determine_bump_type,
    read_current_version,
    update_version_files,
)

# --- determine_bump_type tests ---


def test_patch_bump_default():
    result = determine_bump_type(pr_title="", commits=["fix: typo", "docs: update readme"])
    assert result == "patch"


def test_minor_bump_on_feat_commit():
    result = determine_bump_type(pr_title="", commits=["feat: add uninstall", "fix: typo"])
    assert result == "minor"


def test_minor_bump_on_feat_with_scope():
    result = determine_bump_type(pr_title="", commits=["feat(cli): add doctor command"])
    assert result == "minor"


def test_major_bump_on_release_candidate():
    result = determine_bump_type(pr_title="Release Candidate v2", commits=["feat: big change"])
    assert result == "major"


def test_major_wins_over_minor():
    result = determine_bump_type(pr_title="Release Candidate", commits=["feat: something"])
    assert result == "major"


def test_minor_wins_over_patch():
    result = determine_bump_type(pr_title="Add new features", commits=["feat: new", "fix: old"])
    assert result == "minor"


def test_release_candidate_case_insensitive():
    result = determine_bump_type(pr_title="release candidate for Q2", commits=["fix: stuff"])
    assert result == "major"


def test_no_commits_defaults_to_patch():
    result = determine_bump_type(pr_title="", commits=[])
    assert result == "patch"


def test_empty_pr_title_skips_rc_check():
    result = determine_bump_type(pr_title="", commits=["feat: thing"])
    assert result == "minor"


# --- bump_version tests ---


def test_patch_bump():
    assert bump_version("1.1.1", "patch") == "1.1.2"


def test_minor_bump_resets_patch():
    assert bump_version("1.1.3", "minor") == "1.2.0"


def test_major_bump_resets_minor_and_patch():
    assert bump_version("1.2.3", "major") == "2.0.0"


def test_bump_from_zero():
    assert bump_version("0.0.0", "patch") == "0.0.1"


def test_bump_minor_from_zero():
    assert bump_version("0.0.5", "minor") == "0.1.0"


# --- read_current_version tests ---


def test_read_current_version_from_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.2.3"\n')
    assert read_current_version(tmp_path) == "1.2.3"


# --- update_version_files tests ---


def test_update_version_in_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.1.1"\nrequires-python = ">=3.14"\n')

    config_dir = tmp_path / "src" / "wizard"
    config_dir.mkdir(parents=True)
    config_py = config_dir / "config.py"
    config_py.write_text('class Settings:\n    version: str = "1.1.1"\n    name: str = "wizard"\n')

    update_version_files("1.1.1", "1.2.0", tmp_path)

    assert 'version = "1.2.0"' in pyproject.read_text()
    assert 'version: str = "1.2.0"' in config_py.read_text()
    # Other content preserved
    assert 'name = "wizard"' in pyproject.read_text()
    assert 'name: str = "wizard"' in config_py.read_text()


def test_update_version_only_replaces_exact_match(tmp_path):
    """Ensure we don't accidentally replace version strings in other contexts."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.1.1"\n\n[other]\nversion = "2.0.0"\n')

    config_dir = tmp_path / "src" / "wizard"
    config_dir.mkdir(parents=True)
    config_py = config_dir / "config.py"
    config_py.write_text('class Settings:\n    version: str = "1.1.1"\n')

    update_version_files("1.1.1", "1.2.0", tmp_path)

    content = pyproject.read_text()
    assert 'version = "1.2.0"' in content
    # The [other] section's version should NOT be changed
    assert 'version = "2.0.0"' in content


# --- main entry point tests ---


def test_main_prints_new_version(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.0.0"\n')

    config_dir = tmp_path / "src" / "wizard"
    config_dir.mkdir(parents=True)
    config_py = config_dir / "config.py"
    config_py.write_text('class Settings:\n    version: str = "1.0.0"\n')

    script = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input="fix: a bug\ndocs: update readme\n",
        capture_output=True,
        text=True,
        env={**os.environ, "PR_TITLE": "", "BUMP_PROJECT_ROOT": str(tmp_path)},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "1.0.1"
    assert 'version = "1.0.1"' in pyproject.read_text()
    assert 'version: str = "1.0.1"' in config_py.read_text()


def test_main_feat_commit_bumps_minor(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.0.0"\n')

    config_dir = tmp_path / "src" / "wizard"
    config_dir.mkdir(parents=True)
    config_py = config_dir / "config.py"
    config_py.write_text('class Settings:\n    version: str = "1.0.0"\n')

    script = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input="feat: new feature\nfix: a bug\n",
        capture_output=True,
        text=True,
        env={**os.environ, "PR_TITLE": "", "BUMP_PROJECT_ROOT": str(tmp_path)},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "1.1.0"


def test_main_release_candidate_bumps_major(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.2.3"\n')

    config_dir = tmp_path / "src" / "wizard"
    config_dir.mkdir(parents=True)
    config_py = config_dir / "config.py"
    config_py.write_text('class Settings:\n    version: str = "1.2.3"\n')

    script = Path(__file__).resolve().parent.parent / "scripts" / "bump_version.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        input="feat: big change\n",
        capture_output=True,
        text=True,
        env={**os.environ, "PR_TITLE": "Release Candidate v2", "BUMP_PROJECT_ROOT": str(tmp_path)},
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "2.0.0"
