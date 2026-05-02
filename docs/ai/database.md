# Database — AI Fact Sheet

## Engine Setup

- Driver: SQLite via SQLModel / SQLAlchemy
- URL: `sqlite:///<settings.db>` (default: `~/.wizard/wizard.db`); `:memory:` special-cased to `sqlite://`
- `connect_args`: `check_same_thread=False`, `timeout=30`
- Pragmas set on every connection via `event.listens_for(engine, "connect")`:
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA busy_timeout=30000` (30 s)

## `get_session()` Context Manager

```python
@contextmanager
def get_session() -> Generator[Session, None, None]:
```

- Opens a `sqlmodel.Session` wrapping the module-level `engine`.
- **Commits on clean exit.**
- **Rolls back on any exception**, then re-raises.
- **All DB access must go through `get_session()`** — never construct a `Session` directly.

## `run_migrations()`

```python
def run_migrations() -> None:
```

- Resolves the alembic directory via `importlib.resources.files("wizard").joinpath("alembic")`.
- Works for both editable installs (`src/wizard/alembic/`) and `uv tool install` (installed package path).
- Sets `script_location` and `sqlalchemy.url` on a fresh `alembic.Config` object (does **not** read `alembic.ini`).
- Runs `alembic upgrade head`.

## Alembic CLI Commands

Run from repo root:

| Command | Purpose |
|---|---|
| `uv run alembic upgrade head` | Apply all pending migrations |
| `uv run alembic current` | Show current revision applied to the DB |
| `uv run alembic check` | Verify schema matches models (exits non-zero if drift) |
| `uv run alembic revision -m "..."` | Generate a new migration script |

## `alembic.ini` Settings

File: `alembic.ini` (repo root)

| Key | Value |
|---|---|
| `script_location` | `%(here)s/src/wizard/alembic` |
| `prepend_sys_path` | `src` |
| `sqlalchemy.url` | *(blank — set at runtime by `env.py`)* |
| `path_separator` | `os` |

## `include_object` Filter (`src/wizard/alembic/env.py`)

```python
_FTS_SUFFIXES = ("_fts", "_fts_data", "_fts_idx", "_fts_docsize", "_fts_config")
```

- Tables whose names end with any of these suffixes are **excluded from autogenerate comparison**.
- This prevents alembic from generating spurious drop/create migrations for SQLite FTS5 virtual tables.
- `pseudonym_map` is a standard `SQLModel` class — **not excluded**; it is tracked normally.

## Migration Chain (oldest → head)

| # | Revision ID | Slug |
|---|---|---|
| 1 | `1bbc6e61da58` | `initial` |
| 2 | `bdb1a20e53d2` | `add_daily_page_id_to_wizardsession` |
| 3 | `15146de1d71a` | `add_toolcall_table` |
| 4 | `c821b5437485` | `add_task_state_mental_model_session_` |
| 5 | `3fc6e6059028` | `add_session_lifecycle_columns` |
| 6 | `adf0790585cc` | `add_transcript_path_and_agent_to_` |
| 7 | `af6f28588a06` | `strip_external_ids` |
| 8 | `d4e9f1a2b3c7` | `add_is_synthesised_to_wizardsession` |
| 9 | `e7f3a2c1b8d5` | `add_agent_session_id_continued_from_id` |
| 10 | `f1a2b3c4d5e6` | `add_rolling_summary_to_task_state` |
| 11 | `a9b8c7d6e5f4` | `add_transcript_raw_to_wizardsession` |
| 12 | `f0fb7ac74c46` | `artifact_identity` |
| 13 | `95ee99a3db06` | `backfill_artifact_ids` |
| 14 | `a1b2c3d4e5f6` | `add_active_mode_to_wizardsession` |
| 15 | `9e7c35956d62` | `add_pseudonym_map` |
| 16 | `75c94727cfc5` | `note_artifact_ref_check` |
| 17 | `a2b3c4d5e6f7` | `add_fts5_search_tables` ← **HEAD** |
