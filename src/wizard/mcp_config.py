import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Walk from src/wizard/mcp_config.py -> project root
_PROJECT_DIR = Path(__file__).resolve().parents[2]

CLAUDE_CODE_CONFIG = Path.home() / ".claude.json"
CLAUDE_DESKTOP_CONFIG = Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_mcp_server_entry() -> dict:
    """Return the wizard MCP server definition for Claude config files."""
    return {
        "command": "uv",
        "args": ["--directory", str(_PROJECT_DIR), "run", "server.py"],
    }


def _config_targets() -> dict[str, Path]:
    """Build config targets at call time so tests can patch the constants."""
    return {
        "Claude Code": CLAUDE_CODE_CONFIG,
        "Claude Desktop": CLAUDE_DESKTOP_CONFIG,
    }


def register_wizard_mcp() -> list[str]:
    """Register the wizard MCP server in all existing Claude config files.

    Returns the list of target names where registration succeeded.
    """
    registered: list[str] = []
    entry = get_mcp_server_entry()

    for name, path in _config_targets().items():
        if not path.exists():
            continue

        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, ValueError):
            logger.warning("%s is not valid JSON — skipping", path)
            continue

        data.setdefault("mcpServers", {})
        data["mcpServers"]["wizard"] = entry
        path.write_text(json.dumps(data, indent=2) + "\n")
        registered.append(name)

    return registered
