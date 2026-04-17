import json
import re
from pathlib import Path

import httpx
import typer
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError

from wizard import notion_discovery
from wizard.integrations import ConfigurationError


def run_notion_discovery(config_path: Path) -> None:
    if not config_path.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)

    with open(config_path) as f:
        cfg = json.load(f)

    notion_cfg = cfg.get("notion", {})
    token = notion_cfg.get("token", "")
    tasks_ds_id = notion_cfg.get("tasks_ds_id", "")
    meetings_ds_id = notion_cfg.get("meetings_ds_id", "")

    if not token:
        typer.echo(
            "No Notion token configured. Set notion.token in config.json first.",
            err=True,
        )
        raise typer.Exit(1)

    client = NotionSdkClient(auth=token)
    typer.echo("  Discovering schema...")

    tasks_props = notion_discovery.fetch_db_properties(client, tasks_ds_id)
    meetings_props = notion_discovery.fetch_db_properties(client, meetings_ds_id)
    all_props = {**tasks_props, **meetings_props}

    required_fields = ["task_name", "task_status", "meeting_title"]
    all_fields = [
        "task_name",
        "task_status",
        "task_priority",
        "task_due_date",
        "task_jira_key",
        "meeting_title",
        "meeting_category",
        "meeting_date",
        "meeting_url",
        "meeting_summary",
    ]

    matches = notion_discovery.match_properties(all_props, all_fields)

    for field in required_fields:
        if matches[field] is None:
            available_names = list(all_props.keys())
            typer.echo(f"Could not auto-match required field '{field}'.")
            typer.echo(f"Available properties: {', '.join(available_names)}")
            value = typer.prompt(
                f"Enter Notion property name for '{field}' (or press Enter to skip)"
            )
            if not value:
                raise ConfigurationError(f"Required field '{field}' must be mapped.")
            matches[field] = value

    schema = {k: v for k, v in matches.items() if v is not None}
    cfg.setdefault("notion", {})["notion_schema"] = schema
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    for k, v in schema.items():
        typer.echo(f"    {k:<20} → {v}")
    typer.echo("  Schema saved.")


def resolve_notion_page_id(url: str) -> str:
    """Extract 32-char hex page ID from a Notion URL and format as UUID.

    Handles:
      https://www.notion.so/workspace/My-Tasks-abc123def456789012345678901234ab
      https://www.notion.so/abc123def456789012345678901234ab
      https://www.notion.so/My-Tasks-abc123def456789012345678901234ab?v=...

    Query strings are stripped before matching. URL fragments (#...) are not
    stripped separately, but the hex-only regex ignores them in practice.
    """
    path = url.split("?")[0]
    matches = re.findall(r"[0-9a-f]{32}", path.lower())
    if not matches:
        raise ValueError(f"Could not extract page ID from URL: {url}")
    raw = matches[-1]
    return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"


def resolve_ds_id(client, page_id: str) -> str:
    """Confirm page_id is a valid data source ID and return it unchanged.

    In notion-client v3.0, the 32-char page ID extracted from a Notion database
    URL IS the data source ID — no translation or lookup is needed. This call
    confirms the ID is reachable before we persist it, and raises on 404 / auth
    errors so the caller's retry loop can re-prompt the user.
    """
    client.data_sources.retrieve(data_source_id=page_id)
    return page_id


def notion_is_configured(cfg: dict) -> bool:
    n = cfg.get("notion", {})
    return bool(n.get("token") and n.get("tasks_ds_id") and n.get("meetings_ds_id"))


def jira_is_configured(cfg: dict) -> bool:
    j = cfg.get("jira", {})
    return bool(j.get("token") and j.get("base_url") and j.get("project_key") and j.get("email"))


def configure_notion(cfg: dict, config_path: Path) -> None:
    """Prompt for all Notion credentials, save to config, run schema discovery."""
    typer.echo("\nNotion integration")
    token = typer.prompt(
        "  Notion integration token (notion.so/profile/integrations)", hide_input=True,
    )
    cfg.setdefault("notion", {})["token"] = token
    typer.echo("  token: set")

    page_id = typer.prompt("  Daily page parent ID (Enter to skip)", default="")
    cfg["notion"]["daily_page_parent_id"] = page_id
    typer.echo(f"  daily page ID: {'set' if page_id else 'skipped'}")

    client = NotionSdkClient(auth=token)

    while True:
        tasks_url = typer.prompt("  Tasks database URL")
        try:
            pid = resolve_notion_page_id(tasks_url)
        except ValueError as exc:
            typer.echo(f"  failed: {exc}")
            continue
        try:
            typer.echo("  → Resolving...", nl=False)
            tasks_ds_id = resolve_ds_id(client, pid)
            typer.echo("  ok")
            cfg["notion"]["tasks_ds_id"] = tasks_ds_id
            typer.echo("  tasks database: set")
            break
        except (APIResponseError, httpx.HTTPError) as exc:
            typer.echo(f"\n  failed: {exc}")

    while True:
        meetings_url = typer.prompt("  Meetings database URL")
        try:
            pid = resolve_notion_page_id(meetings_url)
        except ValueError as exc:
            typer.echo(f"  failed: {exc}")
            continue
        try:
            typer.echo("  → Resolving...", nl=False)
            meetings_ds_id = resolve_ds_id(client, pid)
            typer.echo("  ok")
            cfg["notion"]["meetings_ds_id"] = meetings_ds_id
            typer.echo("  meetings database: set")
            break
        except (APIResponseError, httpx.HTTPError) as exc:
            typer.echo(f"\n  failed: {exc}")

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    run_notion_discovery(config_path)


def configure_jira(cfg: dict, config_path: Path) -> None:
    """Prompt for all Jira credentials and save to config."""
    # Re-read to pick up any changes written by prior steps (e.g. notion_schema from discovery)
    if config_path.exists():
        with open(config_path) as f:
            cfg.update(json.load(f))
    typer.echo("\nJira integration")
    base_url = typer.prompt("  Base URL (e.g. https://yourorg.atlassian.net)")
    cfg.setdefault("jira", {})["base_url"] = base_url
    typer.echo(f"  base_url: {base_url}")

    project_key = typer.prompt("  Project key (e.g. ENG)")
    cfg["jira"]["project_key"] = project_key
    typer.echo(f"  project_key: {project_key}")

    email = typer.prompt("  Email")
    cfg["jira"]["email"] = email
    typer.echo("  email: set")

    token = typer.prompt(
        "  API token (id.atlassian.com/manage-profile/security/api-tokens)", hide_input=True,
    )
    cfg["jira"]["token"] = token
    typer.echo("  token: set")

    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)


def run_jira_configure(config_path: Path) -> None:
    if not config_path.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)
    with open(config_path) as f:
        cfg = json.load(f)
    configure_jira(cfg, config_path)
