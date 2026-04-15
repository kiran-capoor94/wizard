from pathlib import Path

import typer


def _check_db_file() -> tuple[bool, str]:
    import os

    from wizard.config import settings

    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if db_path.exists():
        return True, f"Database found: {db_path}"
    return False, f"Database not found: {db_path} — run 'wizard setup' first"


def _check_db_tables() -> tuple[bool, str]:
    import os
    import sqlite3

    from wizard.config import settings

    db_path_str = os.environ.get("WIZARD_DB", settings.db)
    db_path = Path(db_path_str)
    if not db_path.exists():
        return False, "Database file missing — cannot check tables"
    try:
        conn = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()
        required = {"task", "note", "meeting", "wizardsession", "toolcall", "task_state"}
        missing = required - tables
        if missing:
            return False, f"Missing tables: {missing}"
        return True, "All required tables present"
    except Exception as exc:
        return False, f"Could not inspect tables: {exc}"


def _check_config_file() -> tuple[bool, str]:
    import os

    config_path = Path(
        os.environ.get(
            "WIZARD_CONFIG_FILE", str(Path.home() / ".wizard" / "config.json")
        )
    )
    if config_path.exists():
        return True, f"Config file found: {config_path}"
    return False, f"Config file not found: {config_path}"


def _check_notion_token() -> tuple[bool, str]:
    from wizard.config import Settings

    s = Settings()
    if s.notion.token:
        return True, "Notion token configured"
    return False, "Notion token not set (notion.token)"


def _check_jira_token() -> tuple[bool, str]:
    from wizard.config import Settings

    s = Settings()
    if s.jira.token:
        return True, "Jira token configured"
    return False, "Jira token not set (jira.token) — Jira sync disabled"


def _check_allowlist_file() -> tuple[bool, str]:
    allowlist = Path.home() / ".wizard" / "allowlist.txt"
    if allowlist.exists():
        return True, f"Allowlist found: {allowlist}"
    return False, f"Allowlist not found: {allowlist}"


def _check_agent_registrations() -> tuple[bool, str]:
    from wizard import agent_registration

    registered = agent_registration.read_registered_agents()
    if not registered:
        registered = agent_registration.scan_all_registered()
    if registered:
        return True, f"Registered agents: {', '.join(registered)}"
    return False, "No agents registered — run 'wizard setup --agent <agent>'"


def _check_migration_current() -> tuple[bool, str]:
    try:
        import os

        from sqlalchemy import create_engine

        from alembic.runtime.migration import MigrationContext
        from wizard.config import settings

        db_path_str = os.environ.get("WIZARD_DB", settings.db)
        engine = create_engine(f"sqlite:///{db_path_str}")
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current = ctx.get_current_revision()
        return True, f"Migration current: {current}"
    except Exception as exc:
        return False, f"Migration check failed: {exc}"


def _check_skills_installed() -> tuple[bool, str]:
    skills_dir = Path.home() / ".wizard" / "skills"
    if skills_dir.exists() and any(skills_dir.iterdir()):
        return True, f"Skills directory present: {skills_dir}"
    return (
        False,
        f"Skills not installed at {skills_dir} — run 'wizard setup --agent claude-code'",
    )


def _validate_properties(
    available: dict[str, str], expected: list[tuple[str, str]]
) -> list[str]:
    """Return error strings for each property that is missing or has the wrong type."""
    errors = []
    for name, expected_type in expected:
        if name not in available:
            errors.append(f"'{name}' not found (expected {expected_type})")
        elif available[name] != expected_type:
            errors.append(f"'{name}' is {available[name]}, expected {expected_type}")
    return errors


def _check_notion_schema() -> tuple[bool, str]:
    from wizard import notion_discovery
    from wizard.config import Settings
    from wizard.integrations import NotionSdkClient

    s = Settings()
    notion = s.notion
    schema = notion.notion_schema

    if not notion.token or not notion.tasks_ds_id or not notion.meetings_ds_id:
        return False, "Notion not configured — run 'wizard configure --notion'"

    client = NotionSdkClient(auth=notion.token)
    tasks_props = notion_discovery.fetch_db_properties(client, notion.tasks_ds_id)
    meetings_props = notion_discovery.fetch_db_properties(client, notion.meetings_ds_id)

    if not tasks_props and not meetings_props:
        return False, "Could not reach Notion API — check token and network"

    task_fields: list[tuple[str, str]] = [
        (schema.task_name, "title"),
        (schema.task_status, "status"),
        (schema.task_priority, "select"),
        (schema.task_due_date, "date"),
        (schema.task_jira_key, "url"),
    ]
    meeting_fields: list[tuple[str, str]] = [
        (schema.meeting_title, "title"),
        (schema.meeting_date, "date"),
        (schema.meeting_url, "url"),
        (schema.meeting_summary, "rich_text"),
        (schema.meeting_category, "multi_select"),
    ]

    task_errors = _validate_properties(tasks_props, task_fields)
    meeting_errors = _validate_properties(meetings_props, meeting_fields)

    parts = []
    if task_errors:
        parts.append(f"Tasks DB: {'; '.join(task_errors)}")
    if meeting_errors:
        parts.append(f"Meetings DB: {'; '.join(meeting_errors)}")

    if parts:
        return False, " | ".join(parts)
    return True, "Notion schema matches live DB"


# Index of the Notion schema check in the ordered list below (1-based).
# Used to skip it when the Notion token is not configured.
_NOTION_SCHEMA_CHECK_INDEX = 8


def doctor(
    all_checks: bool = typer.Option(
        False, "--all", help="Report all failures instead of stopping at first"
    ),
) -> None:
    """Run health checks on the wizard installation."""
    checks = [
        ("DB file exists", _check_db_file),
        ("Notion token", _check_notion_token),
        ("Jira token", _check_jira_token),
        ("Config file", _check_config_file),
        ("DB tables", _check_db_tables),
        ("Allowlist file", _check_allowlist_file),
        ("Agent registered", _check_agent_registrations),
        ("Notion schema", _check_notion_schema),
        ("Migration current", _check_migration_current),
        ("Skills installed", _check_skills_installed),
    ]

    failures = []
    notion_token_ok = True

    for i, (name, check_fn) in enumerate(checks, 1):
        if i == _NOTION_SCHEMA_CHECK_INDEX and not notion_token_ok:
            typer.echo(f"  [{i:2d}] SKIP  {name} (Notion token not configured)")
            continue

        passed, message = check_fn()

        if i == 2:  # Notion token check
            notion_token_ok = passed

        status = "PASS" if passed else "FAIL"
        typer.echo(f"  [{i:2d}] {status}  {name}: {message}")

        if not passed:
            failures.append((i, name, message))
            if not all_checks:
                raise typer.Exit(1)

    if failures:
        raise typer.Exit(1)
    typer.echo("All checks passed.")
