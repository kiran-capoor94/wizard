"""Thin wrapper — delegates MCP registration to agent_registration.

CLAUDE_CODE_CONFIG and CLAUDE_DESKTOP_CONFIG are kept for backward
compatibility with any tests that patch them.
"""
import logging
from pathlib import Path

from . import agent_registration

logger = logging.getLogger(__name__)

# Backward-compat constants (tests may patch these)
CLAUDE_CODE_CONFIG = Path.home() / ".claude" / "claude_code_config.json"
CLAUDE_DESKTOP_CONFIG = agent_registration._claude_desktop_config_path()


def get_mcp_server_entry() -> dict:
    """Return the wizard MCP server definition (standard JSON entry)."""
    return agent_registration._json_entry()


def register_wizard_mcp() -> None:
    """Register wizard MCP entry for Claude Code. Idempotent."""
    agent_registration.register("claude-code")


def deregister_wizard_mcp() -> None:
    """Remove wizard MCP entry for Claude Code."""
    agent_registration.deregister("claude-code")


def find_wizard_mcp_targets() -> list[Path]:
    """Return config file paths where wizard is currently registered."""
    registered = agent_registration.scan_all_registered()
    return [
        agent_registration._AGENTS[aid].config_path
        for aid in registered
        if aid in agent_registration._AGENTS
    ]
