import json
import logging
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomli_w

from .integrations import ConfigurationError

logger = logging.getLogger(__name__)

_WIZARD_DIR = Path.home() / ".wizard"
_REGISTERED_AGENTS_PATH = _WIZARD_DIR / "registered_agents.json"

# Resolved at import time for the currently running project.
_PROJECT_DIR = Path(__file__).parent.parent.parent


@dataclass
class AgentConfig:
    agent_id: str
    config_path: Path
    format: Literal["json", "toml"]
    mcp_key: str


def _claude_desktop_config_path() -> Path:
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        )
    elif sys.platform == "win32":
        appdata = Path(
            os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        )
        return appdata / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


_AGENTS: dict[str, AgentConfig] = {
    "claude-code": AgentConfig(
        agent_id="claude-code",
        config_path=Path.home() / ".claude" / "settings.json",
        format="json",
        mcp_key="mcpServers",
    ),
    "claude-desktop": AgentConfig(
        agent_id="claude-desktop",
        config_path=_claude_desktop_config_path(),
        format="json",
        mcp_key="mcpServers",
    ),
    "gemini": AgentConfig(
        agent_id="gemini",
        config_path=Path.home() / ".gemini" / "settings.json",
        format="json",
        mcp_key="mcpServers",
    ),
    "opencode": AgentConfig(
        agent_id="opencode",
        config_path=Path.home() / ".config" / "opencode" / "opencode.json",
        format="json",
        mcp_key="mcp",
    ),
    "codex": AgentConfig(
        agent_id="codex",
        config_path=Path.home() / ".codex" / "config.toml",
        format="toml",
        mcp_key="mcp_servers",
    ),
}


def _json_entry() -> dict:
    return {
        "command": "uv",
        "args": ["--directory", str(_PROJECT_DIR), "run", "server.py"],
        "type": "stdio",
    }


def _opencode_entry() -> dict:
    return {
        "type": "local",
        "command": ["uv", "--directory", str(_PROJECT_DIR), "run", "server.py"],
        "enabled": True,
    }


def _toml_entry() -> dict:
    return {
        "command": "uv",
        "args": ["--directory", str(_PROJECT_DIR), "run", "server.py"],
    }


def _register_json(cfg: AgentConfig) -> None:
    cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.config_path.exists():
        try:
            data = json.loads(cfg.config_path.read_text())
        except (json.JSONDecodeError, ValueError) as exc:
            raise ConfigurationError(
                f"Malformed JSON in {cfg.config_path}: {exc}"
            ) from exc
    else:
        data = {}

    if cfg.mcp_key not in data:
        data[cfg.mcp_key] = {}

    entry = _opencode_entry() if cfg.agent_id == "opencode" else _json_entry()
    data[cfg.mcp_key]["wizard"] = entry
    cfg.config_path.write_text(json.dumps(data, indent=2))


def _deregister_json(cfg: AgentConfig) -> None:
    if not cfg.config_path.exists():
        return
    try:
        data = json.loads(cfg.config_path.read_text())
    except (json.JSONDecodeError, ValueError) as exc:
        raise ConfigurationError(f"Malformed JSON in {cfg.config_path}: {exc}") from exc
    mcp_section = data.get(cfg.mcp_key, {})
    mcp_section.pop("wizard", None)
    data[cfg.mcp_key] = mcp_section
    cfg.config_path.write_text(json.dumps(data, indent=2))


def _register_toml(cfg: AgentConfig) -> None:
    cfg.config_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg.config_path.exists():
        try:
            with open(cfg.config_path, "rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigurationError(
                f"Malformed TOML in {cfg.config_path}: {exc}"
            ) from exc
    else:
        data = {}

    if cfg.mcp_key not in data:
        data[cfg.mcp_key] = {}
    data[cfg.mcp_key]["wizard"] = _toml_entry()
    cfg.config_path.write_bytes(tomli_w.dumps(data).encode())


def _deregister_toml(cfg: AgentConfig) -> None:
    if not cfg.config_path.exists():
        return
    try:
        with open(cfg.config_path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(f"Malformed TOML in {cfg.config_path}: {exc}") from exc
    mcp_section = data.get(cfg.mcp_key, {})
    mcp_section.pop("wizard", None)
    data[cfg.mcp_key] = mcp_section
    cfg.config_path.write_bytes(tomli_w.dumps(data).encode())


def register(agent_id: str) -> None:
    """Write wizard MCP entry into agent config. Idempotent."""
    if agent_id not in _AGENTS:
        raise ConfigurationError(f"Unknown agent: {agent_id}")
    cfg = _AGENTS[agent_id]
    if cfg.format == "toml":
        _register_toml(cfg)
    else:
        _register_json(cfg)


def deregister(agent_id: str) -> None:
    """Remove wizard key from agent config. No-op if file absent."""
    if agent_id not in _AGENTS:
        return
    cfg = _AGENTS[agent_id]
    if cfg.format == "toml":
        _deregister_toml(cfg)
    else:
        _deregister_json(cfg)


def read_registered_agents() -> list[str]:
    """Read ~/.wizard/registered_agents.json. Returns empty list if absent."""
    if not _REGISTERED_AGENTS_PATH.exists():
        return []
    try:
        return json.loads(_REGISTERED_AGENTS_PATH.read_text())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not read registered_agents.json: %s", exc)
        return []


def write_registered_agents(agents: list[str]) -> None:
    """Write ~/.wizard/registered_agents.json."""
    _REGISTERED_AGENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTERED_AGENTS_PATH.write_text(json.dumps(agents, indent=2))


def scan_all_registered() -> list[str]:
    """Fallback: check all 5 known config paths, return agent IDs where wizard key present."""
    found = []
    for agent_id, cfg in _AGENTS.items():
        if not cfg.config_path.exists():
            continue
        try:
            if cfg.format == "toml":
                with open(cfg.config_path, "rb") as f:
                    data = tomllib.load(f)
            else:
                data = json.loads(cfg.config_path.read_text())
            if "wizard" in data.get(cfg.mcp_key, {}):
                found.append(agent_id)
        except Exception as exc:
            logger.debug(
                "scan_all_registered: could not check %s for agent %s: %s",
                cfg.config_path,
                agent_id,
                exc,
            )
    return found
