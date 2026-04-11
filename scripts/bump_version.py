"""Determine version bump type and update source files.

Usage:
    PR_TITLE="Some PR title" python scripts/bump_version.py < commit_messages.txt

Reads PR_TITLE from env, commit messages from stdin.
Prints new version to stdout.
"""

from __future__ import annotations

import re


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
