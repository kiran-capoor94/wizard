# CI Tagging & Versioning — Design Spec

**Status:** Design  
**Scope:** Add a GitHub Actions workflow that automatically bumps version, updates source files, and creates git tags on every merge to `main`.

---

## 1. Problem

The wizard project uses semantic versioning (1.1.1) and conventional commits, but has no CI, no git tags, and no automated version management. Version bumps and tagging are manual and easy to forget.

This spec adds:
1. A Python bump script that determines bump type and updates source files
2. A GitHub Actions workflow that runs on push to `main`, calls the script, commits, tags, and pushes

---

## 2. Version Bump Rules

Bump type is determined by inspecting the merged PR title and commit messages. Highest precedence wins.

| Priority | Trigger | Bump | Example |
|----------|---------|------|---------|
| 1 (highest) | PR title contains "Release Candidate" (case-insensitive) | Major (1.x.x → 2.0.0) | PR: "Release Candidate v2" |
| 2 | Any commit starts with `feat:` or `feat(` | Minor (x.1.x → x.2.0) | Commit: `feat: add uninstall command` |
| 3 (default) | Everything else | Patch (x.x.0 → x.x.1) | Commits: `fix: typo`, `docs: readme` |

---

## 3. Bump Script — `scripts/bump_version.py`

### 3.1 Interface

```
PR_TITLE="Some PR title" python scripts/bump_version.py < commit_messages.txt
```

- Reads `PR_TITLE` from environment variable (empty string if unset)
- Reads commit messages from stdin (one per line)
- Prints the new version to stdout (e.g., `1.2.0`)

### 3.2 Logic

1. Read current version from `pyproject.toml` (`version = "x.y.z"` under `[project]`)
2. Read PR title from `$PR_TITLE`
3. Read commit messages from stdin
4. Determine bump type using precedence rules from Section 2
5. Compute new version:
   - Major: increment major, reset minor and patch to 0
   - Minor: increment minor, reset patch to 0
   - Patch: increment patch
6. Update `pyproject.toml`: replace `version = "old"` with `version = "new"`
7. Update `src/wizard/config.py`: replace `version: str = "old"` with `version: str = "new"`
8. Print new version to stdout

### 3.3 File Update Strategy

Simple regex replacement — no TOML parser dependency:
- `pyproject.toml`: match `version = "x.y.z"` under `[project]`
- `config.py`: match `version: str = "x.y.z"`

### 3.4 Edge Cases

- No tags exist yet (first run): use version from `pyproject.toml` as base
- PR title is empty (direct push, no PR): skip RC check, use commit-based detection
- No stdin input (no commits): default to patch bump
- Script is pure stdlib Python — no external dependencies

---

## 4. GitHub Actions Workflow — `.github/workflows/release.yml`

### 4.1 Trigger

```yaml
on:
  push:
    branches: [main]
```

### 4.2 Steps

1. **Checkout** — `actions/checkout@v4` with `fetch-depth: 0` (full history for tag detection and commit log)
2. **Set up Python** — `actions/setup-python@v5` with Python 3.14
3. **Get PR title** — Use `gh pr list --search <sha> --state merged` to find the PR that introduced this push. Set as env var. Falls back to empty string for direct pushes.
4. **Get commits since last tag** — `git log <last-tag>..HEAD --oneline`. If no tags exist, log all commits on `main`.
5. **Run bump script** — Pipe commit log into `python scripts/bump_version.py`, capture new version.
6. **Commit** — Configure git as `github-actions[bot]`, stage `pyproject.toml` and `src/wizard/config.py`, commit with `chore: bump version to vX.Y.Z`.
7. **Tag** — `git tag vX.Y.Z`.
8. **Push** — `git push origin main --tags`.

### 4.3 Permissions

```yaml
permissions:
  contents: write
  pull-requests: read
```

`contents: write` for pushing commits and tags. `pull-requests: read` for querying merged PR title.

### 4.4 Auth

Uses default `GITHUB_TOKEN`. No extra secrets required.

### 4.5 Guard

The workflow checks the HEAD commit message at the start of the job. If it starts with `chore: bump version`, the job exits early with success (no bump, no tag). This prevents infinite loops from the workflow's own version commit triggering another run.

---

## 5. Testing Strategy

### 5.1 Bump Script Unit Tests (`tests/test_bump_version.py`)

All tests use temp directories with fake `pyproject.toml` and `config.py` — no real files touched.

| Test | Input | Expected |
|------|-------|----------|
| Patch bump (default) | Commits: `fix: foo`, `docs: bar`. PR title: "" | x.x.z+1 |
| Minor bump (feat commit) | Commits: `feat: add thing`, `fix: foo`. PR title: "" | x.y+1.0 |
| Major bump (Release Candidate) | Commits: `feat: big`. PR title: "Release Candidate v2" | x+1.0.0 |
| Major wins over minor | Commits: `feat: stuff`. PR title: "Release Candidate" | major |
| Minor wins over patch | Commits: `feat: new`, `fix: old`. PR title: "" | minor |
| Case insensitive RC | PR title: "release candidate for Q2" | major |
| File update pyproject.toml | After bump | `version = "new"` in file |
| File update config.py | After bump | `version: str = "new"` in file |
| No commits (empty stdin) | PR title: "" | patch |

### 5.2 Workflow Testing

No automated tests for the workflow itself — validated by running it on GitHub. The bump script tests cover all the logic; the workflow is pure orchestration.

---

## 6. Files

| File | Change |
|------|--------|
| `scripts/bump_version.py` | **New** — version bump logic |
| `.github/workflows/release.yml` | **New** — CI workflow |
| `tests/test_bump_version.py` | **New** — bump script tests |
