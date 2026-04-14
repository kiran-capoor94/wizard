# wizard update command — design spec

**Date:** 2026-04-15
**Status:** Approved

## Context

Wizard is installed as an editable install (`pip install -e .`) pointing at the local source tree. There is no `wizard update` command today. Updating manually would require: `git pull`, syncing deps, running migrations, and refreshing skills. This spec designs a single command that does all four steps automatically.

## Scope

Developer-only workflow. Not designed for end-users installing from PyPI.

## Command

```
wizard update
```

No flags. Runs four steps in sequence, stops at first failure.

## Steps

1. **`git pull`** — fetch and fast-forward latest commits in the repo root
2. **`uv sync`** (fallback: `pip install -e .`) — install any new or changed dependencies
3. **`alembic upgrade head`** — run any pending DB migrations automatically
4. **Skills refresh** — re-copy package skills to `~/.wizard/skills/`

Each step prints a label and `ok` or `FAILED` with captured output on failure.

## Architecture

### Repo root detection

`Path(__file__).resolve().parents[3]`

`main.py` lives at `src/wizard/cli/main.py`. Three levels up is the repo root. Valid only for editable installs — the only context this command targets.

### Step runner

Private helper:

```python
def _run_update_step(label: str, args: list[str], cwd: Path) -> tuple[bool, str]:
```

Wraps `subprocess.run(args, cwd=cwd, capture_output=True, text=True)`. Returns `(ok, output)`. The `update` command calls it for each step, prints progress, and exits on first failure.

### Skills refresh

Extract the skills-copy block from `setup()` into a `_refresh_skills()` helper. Both `setup` and `update` call it — no duplication.

### `uv` detection

`shutil.which("uv")` — if found, use `["uv", "sync"]`; otherwise fall back to `[sys.executable, "-m", "pip", "install", "-e", str(repo_root)]` to ensure the same Python interpreter that runs wizard installs the deps.

### Alembic step

Run as subprocess: `["alembic", "upgrade", "head"]` with `cwd=repo_root`. Avoids importing alembic internals, produces consistent output style.

## Error handling

- Non-zero exit from any step: print captured output, `raise typer.Exit(1)`.
- No rollback needed: `git pull` and `uv sync` are safe to re-run; alembic migrations are idempotent.

## Testing

- Unit tests patch `subprocess.run` and `shutil.which`.
- Three cases per step: success, failure, uv-not-found fallback for the sync step.
- Skills refresh reuses the existing pattern from `setup` tests.

## Files changed

- `src/wizard/cli/main.py` — add `_run_update_step()`, extract `_refresh_skills()`, add `update` command
- `tests/cli/test_update.py` — new test file
