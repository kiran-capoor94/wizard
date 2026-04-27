"""wizard verify — confirm MCP installation is working."""

import json
import shutil
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



def _validate_mcp_responses(responses: dict[int, dict]) -> tuple[bool, str]:
    """Validate initialize (id=1) and tools/list (id=2) responses. Returns (passed, message)."""
    if 1 not in responses or "result" not in responses.get(1, {}):
        return False, "MCP server did not respond to initialize"
    server_name = responses[1]["result"].get("serverInfo", {}).get("name", "")
    if server_name != "wizard":
        return False, f"MCP server name mismatch: expected 'wizard', got {server_name!r}"
    if 2 not in responses or "result" not in responses.get(2, {}):
        return False, "MCP server did not respond to tools/list"
    tools = responses[2]["result"].get("tools", [])
    return True, f"MCP server starts ({len(tools)} tools registered)"


def _mcp_server_command() -> list[str]:
    """Return the command to start the MCP server.

    Prefers the installed `wizard-server` entry point (works for both `uv tool install`
    and pip installs). Falls back to `uv run server.py` when running from a dev checkout
    and the entry point is not on PATH.
    """
    if shutil.which("wizard-server"):
        return ["wizard-server"]
    # Dev checkout fallback: server.py lives at the repo root, 4 levels above this file.
    repo_root = Path(__file__).resolve().parents[3]
    server_py = repo_root / "server.py"
    if server_py.exists():
        return ["uv", "--directory", str(repo_root), "run", "server.py"]
    return ["wizard-server"]  # will fail with a clear FileNotFoundError


def _check_mcp_server() -> tuple[bool, str]:
    """Start MCP server, perform MCP handshake, return (passed, message).

    Uses interactive pipes: reads the initialize response before sending tools/list
    so FastMCP flushes each response before the next request is sent. No DB writes
    occur — tools/list does not invoke any tool function.
    """
    def _send(proc: subprocess.Popen, msg: dict) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    def _recv(proc: subprocess.Popen) -> dict:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        return json.loads(line.decode(errors="replace").strip())

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            _mcp_server_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        try:
            _send(proc, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "wizard-verify", "version": "1.0"},
                },
            })
            init_resp = _recv(proc)

            _send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
            tools_resp = _recv(proc)

            _send(proc, {"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
        finally:
            proc.stdin.close()  # type: ignore[union-attr]
            proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if proc is not None:
            proc.kill()
        return False, "MCP server timed out after 15s"
    except FileNotFoundError:
        return False, "MCP server failed to start (wizard-server not found in PATH)"
    except Exception as exc:
        return False, f"MCP server check failed: {exc}"

    responses: dict[int, dict] = {}
    for resp in (init_resp, tools_resp):
        rid = resp.get("id")
        if isinstance(rid, int):
            responses[rid] = resp
    return _validate_mcp_responses(responses)
