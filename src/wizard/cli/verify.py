"""wizard verify — confirm MCP installation is working."""

import json
import subprocess
from pathlib import Path

import typer

from wizard.cli.doctor import (
    check_config_file,
    check_db_file,
    check_db_tables,
    check_skills_installed,
)


def verify() -> None:
    """Confirm Wizard is installed and the MCP server is reachable."""
    typer.echo("Checking Wizard installation...")

    for check_fn in (
        check_config_file,
        check_db_file,
        check_db_tables,
        check_skills_installed,
    ):
        passed, message = check_fn()
        typer.echo(f"  {'✓' if passed else '✗'} {message}")
        if not passed:
            typer.echo("\n  Fix: run  wizard doctor  for a detailed diagnosis.")
            raise typer.Exit(code=1)

    passed, message = _check_mcp_server()
    typer.echo(f"  {'✓' if passed else '✗'} {message}")
    if not passed:
        typer.echo("\n  Fix: run  wizard doctor  for a detailed diagnosis.")
        raise typer.Exit(code=1)

    typer.echo(
        "\nAll checks passed. Wizard is ready.\n"
        "\nWhat to do next:\n"
        "  Open Claude Code — the wizard: tools are available automatically via MCP.\n"
        "  The SessionStart hook calls wizard:session_start at the start of every\n"
        "  conversation. Just start working.\n"
        "\n"
        "  Run  wizard analytics  anytime to review your session history."
    )


def _check_mcp_server() -> tuple[bool, str]:  # noqa: C901
    """Start MCP server, send initialize + tools/list, return (passed, message).

    Sends all JSON-RPC messages then closes stdin (EOF). FastMCP's stdio
    transport processes queued messages and exits on EOF. No DB writes occur —
    initialize and tools/list do not invoke any tool function.
    """
    repo_root = Path(__file__).resolve().parents[3]

    stdin_data = (
        json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "wizard-verify", "version": "1.0"},
            },
        })
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )

    try:
        result = subprocess.run(
            ["uv", "--directory", str(repo_root), "run", "server.py"],
            input=stdin_data.encode(),
            capture_output=True,
            timeout=15,
        )
    except subprocess.TimeoutExpired:
        return False, "MCP server timed out after 15s"
    except FileNotFoundError:
        return False, "MCP server failed to start (uv not found in PATH)"
    except Exception as exc:
        return False, f"MCP server check failed: {exc}"

    responses: dict[int, dict] = {}
    for line in result.stdout.decode(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
            if isinstance(msg, dict) and "id" in msg:
                responses[msg["id"]] = msg
        except json.JSONDecodeError:
            continue

    if 1 not in responses or "result" not in responses.get(1, {}):
        return False, "MCP server did not respond to initialize"

    server_name = responses[1]["result"].get("serverInfo", {}).get("name", "")
    if server_name != "wizard":
        return False, f"MCP server name mismatch: expected 'wizard', got {server_name!r}"

    if 2 not in responses or "result" not in responses.get(2, {}):
        return False, "MCP server did not respond to tools/list"

    tools = responses[2]["result"].get("tools", [])
    return True, f"MCP server starts ({len(tools)} tools registered)"
