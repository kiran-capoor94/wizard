# CI Tagging & Versioning — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically bump version, update source files, and create git tags on every merge to `main`.

**Architecture:** A pure-stdlib Python script (`scripts/bump_version.py`) handles all version logic. A GitHub Actions workflow (`.github/workflows/release.yml`) orchestrates: get PR title, get commits, run script, commit, tag, push. The script is the brain, the workflow is the plumbing.

**Tech Stack:** Python 3 (stdlib only), GitHub Actions, git

---

## File Structure

| File | Role |
|------|------|
| `scripts/bump_version.py` | **New** — version bump detection, computation, and file updates |
| `.github/workflows/release.yml` | **New** — CI workflow triggered on push to main |
| `tests/test_bump_version.py` | **New** — unit tests for bump script |

---

### Task 1: Bump Detection and Version Computation

**Files:**
- Create: `scripts/bump_version.py`
- Create: `tests/test_bump_version.py`

- [ ] **Step 1: Write failing tests for `determine_bump_type`**

```python
# tests/test_bump_version.py
import sys
from pathlib import Path

# Add scripts/ to path so we can import the module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from bump_version import determine_bump_type


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_bump_version.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bump_version'`

- [ ] **Step 3: Write failing tests for `bump_version`**

```python
# tests/test_bump_version.py (append)
from bump_version import bump_version


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
```

- [ ] **Step 4: Implement `determine_bump_type` and `bump_version`**

```python
# scripts/bump_version.py
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
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bump_version.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/bump_version.py tests/test_bump_version.py
git commit -m "feat: add version bump detection and computation logic"
```

---

### Task 2: File Updates and Script Entry Point

**Files:**
- Modify: `scripts/bump_version.py`
- Modify: `tests/test_bump_version.py`

- [ ] **Step 1: Write failing tests for `read_current_version`**

```python
# tests/test_bump_version.py (append)
from bump_version import read_current_version


def test_read_current_version_from_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "wizard"\nversion = "1.2.3"\n')
    assert read_current_version(tmp_path) == "1.2.3"
```

- [ ] **Step 2: Write failing tests for `update_version_files`**

```python
# tests/test_bump_version.py (append)
from bump_version import update_version_files


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_bump_version.py -v -k "read_current or update_version"`
Expected: FAIL — `ImportError: cannot import name 'read_current_version'`

- [ ] **Step 4: Implement `read_current_version` and `update_version_files`**

```python
# scripts/bump_version.py (append before any main block)

_PYPROJECT_VERSION_RE = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
_CONFIG_VERSION_RE = re.compile(r'^(\s*version:\s*str\s*=\s*")([^"]+)(")', re.MULTILINE)


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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_bump_version.py -v`
Expected: All PASS

- [ ] **Step 6: Write failing test for `main` entry point**

```python
# tests/test_bump_version.py (append)
import subprocess


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
```

- [ ] **Step 7: Implement `main`**

```python
# scripts/bump_version.py (append at the bottom)

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
```

Note: `BUMP_PROJECT_ROOT` env var allows tests to redirect file operations to a temp directory. In production (CI), it is unset and defaults to `_PROJECT_ROOT`.

- [ ] **Step 8: Run all tests to verify they pass**

Run: `uv run pytest tests/test_bump_version.py -v`
Expected: All PASS

- [ ] **Step 9: Commit**

```bash
git add scripts/bump_version.py tests/test_bump_version.py
git commit -m "feat: add file updates and entry point to bump_version script"
```

---

### Task 3: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create `.github/workflows/` directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Write the workflow file**

```yaml
# .github/workflows/release.yml
name: Release — bump version and tag

on:
  push:
    branches: [main]

permissions:
  contents: write
  pull-requests: read

jobs:
  bump-and-tag:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Skip if version bump commit
        id: guard
        run: |
          msg=$(git log -1 --pretty=%s)
          if [[ "$msg" == chore:\ bump\ version* ]]; then
            echo "skip=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Set up Python
        if: steps.guard.outputs.skip != 'true'
        uses: actions/setup-python@v5
        with:
          python-version: "3.14"

      - name: Get merged PR title
        if: steps.guard.outputs.skip != 'true'
        id: pr
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          sha="${{ github.sha }}"
          title=$(gh pr list --search "$sha" --state merged --json title --jq '.[0].title // ""')
          echo "title=$title" >> "$GITHUB_OUTPUT"

      - name: Get commits since last tag
        if: steps.guard.outputs.skip != 'true'
        id: commits
        run: |
          last_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
          if [ -z "$last_tag" ]; then
            git log --oneline > /tmp/commits.txt
          else
            git log "${last_tag}..HEAD" --oneline > /tmp/commits.txt
          fi

      - name: Run bump script
        if: steps.guard.outputs.skip != 'true'
        id: bump
        env:
          PR_TITLE: ${{ steps.pr.outputs.title }}
        run: |
          new_version=$(python scripts/bump_version.py < /tmp/commits.txt)
          echo "version=$new_version" >> "$GITHUB_OUTPUT"

      - name: Commit, tag, and push
        if: steps.guard.outputs.skip != 'true'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add pyproject.toml src/wizard/config.py
          git commit -m "chore: bump version to v${{ steps.bump.outputs.version }}"
          git tag "v${{ steps.bump.outputs.version }}"
          git push origin main --tags
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat: add GitHub Actions release workflow for auto-tagging"
```
