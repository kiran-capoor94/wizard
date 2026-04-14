# wizard update command — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `wizard update` CLI command that runs `git pull`, syncs deps, runs DB migrations, and refreshes skills — all in sequence from the editable install's repo root.

**Architecture:** Three private helpers (`_refresh_skills`, `_run_update_step`, repo root detection) support a single `update` command in `src/wizard/cli/main.py`. `_refresh_skills` is extracted from the existing `setup` command to eliminate duplication. All subprocess steps go through `_run_update_step` for consistent output and error handling.

**Tech Stack:** Python stdlib (`subprocess`, `sys`, `shutil`, `pathlib`), Typer, pytest, `unittest.mock`

---

## File Map

| File | Change |
|------|--------|
| `src/wizard/cli/main.py` | Add `import subprocess`, `import sys` at top; extract `_refresh_skills(dest)`; add `_run_update_step(label, args, cwd)`; add `update` command |
| `tests/test_cli_update.py` | New file — tests for all three additions |

---

### Task 1: Extract `_refresh_skills()` from `setup()`

**Files:**
- Modify: `src/wizard/cli/main.py` (skills-copy block in `setup`, lines 122–131)
- Create: `tests/test_cli_update.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_cli_update.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/agntx/Documents/repos/personal/wizard
.venv/bin/pytest tests/test_cli_update.py -v
```

Expected: `ImportError` or `AttributeError` — `_refresh_skills` doesn't exist yet.

- [ ] **Step 3: Extract `_refresh_skills()` in `main.py`**

In `src/wizard/cli/main.py`, add this function directly before the `setup` command (around line 96):

```python
def _refresh_skills(dest: Path) -> None:
    """Copy skills from the package into dest, replacing any existing copy."""
    source = _package_skills_dir()
    if source.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        typer.echo(f"Installed skills to {dest}")
    else:
        typer.echo("No skills found in package — skipping skill install")
```

Then in `setup()`, replace the skills-copy block (lines 122–131):

```python
    # before:
    source = _package_skills_dir()
    dest = WIZARD_HOME / "skills"
    if source.exists():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        typer.echo(f"Installed skills to {dest}")
    else:
        typer.echo("No skills found in package — skipping skill install")

    # after:
    _refresh_skills(WIZARD_HOME / "skills")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_cli_update.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Verify existing setup tests still pass**

```bash
.venv/bin/pytest tests/test_cli.py -v -k "skills"
```

Expected: all skills-related tests PASSED (extraction must not break setup).

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli_update.py
git commit -m "refactor: extract _refresh_skills helper from setup"
```

---

### Task 2: Add `_run_update_step()` helper

**Files:**
- Modify: `src/wizard/cli/main.py` — add `import subprocess`, `import sys` at top; add `_run_update_step`
- Modify: `tests/test_cli_update.py` — append new tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_update.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cli_update.py::test_run_update_step_returns_true_on_success tests/test_cli_update.py::test_run_update_step_returns_false_on_failure tests/test_cli_update.py::test_run_update_step_passes_cwd_to_subprocess -v
```

Expected: `ImportError` or `AttributeError` — `_run_update_step` doesn't exist yet.

- [ ] **Step 3: Add `import subprocess` and `import sys` to `main.py`**

At the top of `src/wizard/cli/main.py`, after the existing stdlib imports, add:

```python
import subprocess
import sys
```

The import block should look like:

```python
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional
```

- [ ] **Step 4: Add `_run_update_step()` to `main.py`**

Add directly after `_refresh_skills` (before the `setup` command):

```python
def _run_update_step(label: str, args: list[str], cwd: Path) -> tuple[bool, str]:
    """Run a subprocess step, printing label and ok/FAILED. Returns (success, output)."""
    typer.echo(f"  {label}...", nl=False)
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    ok = result.returncode == 0
    typer.echo(" ok" if ok else " FAILED")
    return ok, (result.stdout + result.stderr).strip()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
.venv/bin/pytest tests/test_cli_update.py -v
```

Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli_update.py
git commit -m "feat: add _run_update_step helper for wizard update command"
```

---

### Task 3: Add `update` command

**Files:**
- Modify: `src/wizard/cli/main.py` — add `update` command
- Modify: `tests/test_cli_update.py` — append command-level tests

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_update.py`:

```python
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

        def __exit__(self, *exc):
            self._patcher.stop()

    return _Ctx()


def test_update_runs_all_three_subprocess_steps(tmp_path):
    from unittest.mock import MagicMock, call

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
    from unittest.mock import MagicMock, call

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    captured_calls = []

    def capturing_step(label, args, cwd):
        captured_calls.append((label, args))
        return True, ""

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=capturing_step),
            patch("wizard.cli.main._refresh_skills"),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            runner.invoke(ctx.app, ["update"])

    sync_args = [args for label, args in captured_calls if "sync" in label or "uv" in str(args)]
    assert any(args == ["uv", "sync"] for _, args in captured_calls)


def test_update_falls_back_to_pip_when_uv_missing(tmp_path):
    from unittest.mock import MagicMock

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    captured_calls = []

    def capturing_step(label, args, cwd):
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
    from unittest.mock import MagicMock

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()

    def failing_step(label, args, cwd):
        return False, "fatal: not a git repo"

    with _fresh_update_app(wizard_dir) as ctx:
        with (
            patch("wizard.cli.main._run_update_step", side_effect=failing_step),
            patch("wizard.cli.main.shutil.which", return_value="/usr/bin/uv"),
        ):
            result = runner.invoke(ctx.app, ["update"])

    assert result.exit_code == 1


def test_update_stops_after_first_failure(tmp_path):
    from unittest.mock import MagicMock

    wizard_dir = tmp_path / ".wizard"
    wizard_dir.mkdir()
    call_count = 0

    def step_that_fails_first(label, args, cwd):
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/pytest tests/test_cli_update.py::test_update_runs_all_three_subprocess_steps tests/test_cli_update.py::test_update_exits_1_on_step_failure -v
```

Expected: `FAILED` — `update` command doesn't exist yet.

- [ ] **Step 3: Add `update` command to `main.py`**

Add after the `analytics` command at the end of `src/wizard/cli/main.py`:

```python
@app.command()
def update() -> None:
    """Pull latest code, sync deps, run migrations, and refresh skills."""
    repo_root = Path(__file__).resolve().parents[3]
    sync_args = ["uv", "sync"] if shutil.which("uv") else [sys.executable, "-m", "pip", "install", "-e", str(repo_root)]

    steps: list[tuple[str, list[str]]] = [
        ("git pull", ["git", "pull"]),
        ("sync deps", sync_args),
        ("run migrations", ["alembic", "upgrade", "head"]),
    ]

    for label, args in steps:
        ok, output = _run_update_step(label, args, repo_root)
        if not ok:
            typer.echo(output, err=True)
            raise typer.Exit(1)

    _refresh_skills(WIZARD_HOME / "skills")
    typer.echo("Wizard updated.")
```

- [ ] **Step 4: Run all update tests to verify they pass**

```bash
.venv/bin/pytest tests/test_cli_update.py -v
```

Expected: all PASSED.

- [ ] **Step 5: Run full test suite to verify no regressions**

```bash
.venv/bin/pytest tests/ -v
```

Expected: all PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/wizard/cli/main.py tests/test_cli_update.py
git commit -m "feat: add wizard update command"
```
