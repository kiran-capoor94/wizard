import json
import logging
from pathlib import Path
from typing import Optional

import httpx
import typer
from notion_client import Client as NotionSdkClient
from notion_client.errors import APIResponseError
from rich import print as rprint
from rich.table import Table

from wizard.llm_adapters import probe_backend_health

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
    results = response.get("results", [])  # type: ignore[union-attr]

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


synthesis_app = typer.Typer(help="Manage LLM backends for transcript synthesis.")

_CONFIG_PATH = Path.home() / ".wizard" / "config.json"


def _load_config() -> tuple[dict, list[dict]]:
    if not _CONFIG_PATH.exists():
        typer.echo("Config not found. Run 'wizard setup' first.", err=True)
        raise typer.Exit(1)
    cfg = json.loads(_CONFIG_PATH.read_text())
    backends: list[dict] = cfg.setdefault("synthesis", {}).setdefault("backends", [])
    return cfg, backends


def _save_config(cfg: dict) -> None:
    _CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _backends_table(backends: list[dict]) -> Table:
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="dim", width=3)
    table.add_column("Description")
    table.add_column("Model")
    table.add_column("Base URL")
    for i, b in enumerate(backends, 1):
        table.add_row(
            str(i),
            b.get("description", ""),
            b.get("model", ""),
            b.get("base_url", "") or "[dim](cloud)[/dim]",
        )
    return table


def _validate_index(index: int, backends: list[dict]) -> None:
    if not 1 <= index <= len(backends):
        typer.echo(f"Invalid index {index}. Have {len(backends)} backend(s).", err=True)
        raise typer.Exit(1)


@synthesis_app.callback(invoke_without_command=True)
def synthesis_list(ctx: typer.Context) -> None:
    """List configured backends (tried in order — first healthy wins)."""
    if ctx.invoked_subcommand is not None:
        return
    _, backends = _load_config()
    if not backends:
        typer.echo("No backends configured. Run: wizard configure synthesis add")
        return
    rprint(_backends_table(backends))


@synthesis_app.command("add")
def synthesis_add(
    model: str = typer.Option(..., prompt="Model (e.g. ollama/gemma4:latest-64k)"),
    base_url: str = typer.Option("", prompt="Base URL (blank for cloud APIs)"),
    api_key: str = typer.Option("", prompt="API key", hide_input=True),
    description: str = typer.Option("", prompt="Description"),
) -> None:
    """Add a backend. Prompts interactively if options are omitted."""
    cfg, backends = _load_config()
    backends.append(
        {"model": model, "base_url": base_url, "api_key": api_key, "description": description}
    )
    _save_config(cfg)
    typer.echo(f"Added backend #{len(backends)}: {model}")


@synthesis_app.command("remove")
def synthesis_remove(
    index: int = typer.Argument(..., help="Backend number to remove (see list)."),
) -> None:
    """Remove a backend by number."""
    cfg, backends = _load_config()
    _validate_index(index, backends)
    removed = backends.pop(index - 1)
    _save_config(cfg)
    typer.echo(f"Removed #{index}: {removed.get('model', '')}")


@synthesis_app.command("move")
def synthesis_move(
    from_pos: int = typer.Argument(..., help="Current position."),
    to_pos: int = typer.Argument(..., help="Target position (1 = highest priority)."),
) -> None:
    """Reorder backends. Position 1 has highest priority."""
    cfg, backends = _load_config()
    _validate_index(from_pos, backends)
    _validate_index(to_pos, backends)
    entry = backends.pop(from_pos - 1)
    backends.insert(to_pos - 1, entry)
    _save_config(cfg)
    typer.echo(f"Moved '{entry.get('model', '')}' to position {to_pos}.")


@synthesis_app.command("test")
def synthesis_test(
    index: Optional[int] = typer.Argument(None, help="Backend number to test. Omit to test all."),
) -> None:
    """Probe backend reachability. Local servers are probed; cloud APIs always pass."""
    _, backends = _load_config()
    if not backends:
        typer.echo("No backends configured.")
        return
    if index is not None:
        _validate_index(index, backends)
        targets = [(index, backends[index - 1])]
    else:
        targets = list(enumerate(backends, 1))
    for i, b in targets:
        model = b.get("model", "")
        base_url = b.get("base_url") or None
        typer.echo(f"  #{i} {model} ...", nl=False)
        ok = probe_backend_health(base_url)
        typer.echo(" reachable" if ok else " unreachable")

