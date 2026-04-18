import json
import logging
from pathlib import Path

import httpx
import typer
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError

logger = logging.getLogger(__name__)

# Pass 1: exact names to wizard field mapping (lowercase)
_EXACT_NAMES: dict[str, str] = {
    "task": "task_name",
    "status": "task_status",
    "priority": "task_priority",
    "due date": "task_due_date",
    "jira": "task_jira_key",
    "meeting name": "meeting_title",
    "category": "meeting_category",
    "date": "meeting_date",
    "krisp url": "meeting_url",
    "summary": "meeting_summary",
}

# Pass 2: property type hints — first property of matching type wins
_TYPE_HINTS: dict[str, str] = {
    "task_name": "title",
    "meeting_title": "title",
    "task_due_date": "date",
    "meeting_date": "date",
}

# Pass 3: synonyms
_SYNONYMS: dict[str, list[str]] = {
    "task_status": ["state", "workflow", "stage"],
    "meeting_category": ["type", "meeting type", "kind"],
    "meeting_url": [
        "recording", "transcript", "krisp", "fathom", "video",
        "transcript url", "fathom url", "krisp url",
    ],
}


def fetch_db_properties(notion_client, db_id: str) -> dict[str, str]:
    """Return {property_name: property_type} for the given data source ID."""
    try:
        response = notion_client.data_sources.retrieve(data_source_id=db_id)
        return {
            name: prop["type"]
            for name, prop in response.get("properties", {}).items()
        }
    except (APIResponseError, httpx.HTTPError, KeyError, TypeError) as exc:
        logger.warning("fetch_db_properties failed for %s: %s", db_id, exc)
        return {}


def match_properties(
    available: dict[str, str],
    fields: list[str],
) -> dict[str, str | None]:
    """Map wizard field names to Notion property names using 3-pass matching.

    Returns {wizard_field: matched_property_name_or_None}
    """
    result: dict[str, str | None] = {}
    available_lower = {k.lower(): k for k in available}

    for field in fields:
        matched = None

        # Pass 1: exact name match (case-insensitive)
        for prop_lower, prop_original in available_lower.items():
            if _EXACT_NAMES.get(prop_lower) == field:
                matched = prop_original
                break

        # Pass 2: type match
        if matched is None and field in _TYPE_HINTS:
            target_type = _TYPE_HINTS[field]
            for prop_name, prop_type in available.items():
                if prop_type == target_type:
                    matched = prop_name
                    break

        # Pass 3: synonym match
        if matched is None and field in _SYNONYMS:
            synonyms = _SYNONYMS[field]
            for synonym in synonyms:
                if synonym in available_lower:
                    matched = available_lower[synonym]
                    break

        result[field] = matched

    return result


def discover_data_sources(
    client: NotionSdkClient,
) -> list[tuple[str, str]]:
    """Enumerate all data sources visible to the integration.

    Uses the v3 search API with filter value "data_source" to get all
    data sources directly. Returns a flat list of (ds_id, ds_name) tuples.
    """
    response = client.search(
        filter={"property": "object", "value": "data_source"},
    )
    results = response.get("results", [])

    return [
        (ds["id"], ds.get("title", [{}])[0].get("plain_text", "(untitled)"))
        for ds in results
    ]


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

    tasks_props = fetch_db_properties(client, tasks_ds_id)
    meetings_props = fetch_db_properties(client, meetings_ds_id)
    all_props = {**tasks_props, **meetings_props}

    if not all_props:
        typer.echo(
            "  Could not fetch properties from Notion — check token and database IDs.",
            err=True,
        )
        raise typer.Exit(1)

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
    required_fields = ["task_name", "task_status", "meeting_title"]

    matches = match_properties(all_props, all_fields)

    unmatched = [f for f in required_fields if matches[f] is None]
    if unmatched:
        typer.echo("  Auto-match failed for required fields:")
        for field in unmatched:
            typer.echo(f"    {field} — no match found")
        typer.echo(f"  Available properties: {', '.join(all_props.keys())}")
        typer.echo("  Re-check your Notion database and re-run 'wizard configure --notion'.")
        raise typer.Exit(1)

    schema = {k: v for k, v in matches.items() if v is not None}
    cfg.setdefault("notion", {})["notion_schema"] = schema
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)

    for k, v in schema.items():
        typer.echo(f"    {k:<20} -> {v}")
    typer.echo("  Schema saved.")



def notion_is_configured(cfg: dict) -> bool:
    n = cfg.get("notion", {})
    return bool(n.get("token") and n.get("tasks_ds_id") and n.get("meetings_ds_id"))


def jira_is_configured(cfg: dict) -> bool:
    j = cfg.get("jira", {})
    return bool(j.get("token") and j.get("base_url") and j.get("project_key") and j.get("email"))


def configure_notion(cfg: dict, config_path: Path) -> None:  # noqa: C901
    """Prompt for Notion token, discover data sources, let user pick, run schema discovery."""
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

    typer.echo("\n  Looking up data sources in Notion...")
    all_ds = discover_data_sources(client)

    if not all_ds:
        typer.echo("  No data sources found — check integration has access to a database.")
        raise typer.Exit(1)

    typer.echo(f"  Found {len(all_ds)} data sources.")

    slots = [
        ("tasks", "tasks_ds_id", "task"),
        ("meetings", "meetings_ds_id", "meeting"),
    ]

    for label, config_key, search_term in slots:
        matches = [(ds_id, ds_name) for ds_id, ds_name in all_ds
                    if search_term in ds_name.lower()]

        if matches:
            typer.echo(f"\n  Finding data sources for {label} (matching \"{search_term}\")...")
            typer.echo(f"  Found {len(matches)} match{'es' if len(matches) != 1 else ''}:")
            options = matches
        else:
            typer.echo(f"\n  Finding data sources for {label} (matching \"{search_term}\")...")
            typer.echo("  Found 0 matches — showing all:")
            options = all_ds

        for i, (_ds_id, ds_name) in enumerate(options, 1):
            typer.echo(f"    {i}. {ds_name}")

        while True:
            choice = typer.prompt("  Which one?", default="1")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    break
            except ValueError:
                pass
            typer.echo(f"  Invalid selection — enter 1-{len(options)}")

        chosen_ds_id, chosen_name = options[idx]
        cfg["notion"][config_key] = chosen_ds_id
        typer.echo(f"  {label} data source: set ({chosen_name})")

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
