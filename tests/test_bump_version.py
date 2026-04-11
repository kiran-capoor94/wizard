# tests/test_bump_version.py
import sys
from pathlib import Path

# Add scripts/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bump_version import determine_bump_type, bump_version


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
