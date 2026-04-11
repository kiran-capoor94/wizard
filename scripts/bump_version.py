"""Determine version bump type and update source files.

Usage:
    PR_TITLE="Some PR title" python scripts/bump_version.py < commit_messages.txt

Reads PR_TITLE from env, commit messages from stdin.
Prints new version to stdout.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def determine_bump_type(pr_title: str, commits: list[str]) -> str:
    """Return 'major', 'minor', or 'patch' based on PR title and commits."""
    if pr_title and "release candidate" in pr_title.lower():
        return "major"

    for commit in commits:
        if re.match(r"^feat[:(]", commit):
            return "minor"

    return "patch"


def bump_version(current: str, bump_type: str) -> str:
    """Compute new version string from current version and bump type."""
    major, minor, patch = (int(x) for x in current.split("."))

    if bump_type == "major":
        return f"{major + 1}.0.0"
    if bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)


def read_current_version(project_root: Path | None = None) -> str:
    """Read current version from pyproject.toml."""
    root = project_root or _PROJECT_ROOT
    pyproject = root / "pyproject.toml"
    match = _PYPROJECT_VERSION_RE.search(pyproject.read_text())
    if not match:
        print("Error: could not find version in pyproject.toml", file=sys.stderr)
        sys.exit(1)
    return match.group(2)


def update_version_files(old: str, new: str, project_root: Path | None = None) -> None:
    """Replace old version with new in pyproject.toml and config.py."""
    root = project_root or _PROJECT_ROOT

    pyproject = root / "pyproject.toml"
    content = pyproject.read_text()
    content = content.replace(f'version = "{old}"', f'version = "{new}"', 1)
    pyproject.write_text(content)

    config_py = root / "src" / "wizard" / "config.py"
    content = config_py.read_text()
    content = content.replace(f'version: str = "{old}"', f'version: str = "{new}"', 1)
    config_py.write_text(content)


def main() -> None:
    root_override = os.environ.get("BUMP_PROJECT_ROOT")
    project_root = Path(root_override) if root_override else _PROJECT_ROOT

    pr_title = os.environ.get("PR_TITLE", "")
    commits = [line.strip() for line in sys.stdin if line.strip()]

    current = read_current_version(project_root)
    bump_type = determine_bump_type(pr_title, commits)
    new = bump_version(current, bump_type)
    update_version_files(current, new, project_root)

    print(new)


if __name__ == "__main__":
    main()
