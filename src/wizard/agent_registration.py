import importlib.resources
import json
import logging
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import tomli_w

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)

_WIZARD_DIR = Path.home() / ".wizard"
_REGISTERED_AGENTS_PATH = _WIZARD_DIR / "registered_agents.json"
_WIZARD_HOOKS_DIR = _WIZARD_DIR / "hooks"


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
        config_path=Path.home() / ".claude.json",
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
    "copilot": AgentConfig(
        agent_id="copilot",
        config_path=Path.home() / ".copilot" / "mcp-config.json",
        format="json",
        mcp_key="mcpServers",
    ),
}


def _json_entry() -> dict:
    return {
        "command": "wizard-server",
        "args": [],
        "type": "stdio",
    }


def _opencode_entry() -> dict:
    return {
        "type": "local",
        "command": ["wizard-server"],
        "enabled": True,
    }


def _toml_entry() -> dict:
    return {
        "command": "wizard-server",
        "args": [],
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


_HOOK_CONFIGS: dict[str, tuple[Path, str]] = {
    # agent_id -> (config_path, hooks_key_path)
    "claude-code": (
        Path.home() / ".claude" / "settings.json",
        "hooks",
    ),
    "codex": (
        Path.home() / ".codex" / "hooks.json",
        "hooks",
    ),
    "gemini": (
        Path.home() / ".gemini" / "settings.json",
        "hooks",
    ),
    "copilot": (
        Path.home() / ".copilot" / "config.json",
        "hooks",
    ),
}

_HOOK_SCRIPTS: dict[str, dict[str, Path]] = {
    "claude-code": {
        "SessionEnd": _WIZARD_HOOKS_DIR / "session-end.sh",
        "SessionStart": _WIZARD_HOOKS_DIR / "session-start.sh",
    },
    "codex": {
        "Stop": _WIZARD_HOOKS_DIR / "session-end.sh",
        "SessionStart": _WIZARD_HOOKS_DIR / "session-start-minimal.sh",
    },
    "gemini": {
        "SessionEnd": _WIZARD_HOOKS_DIR / "session-end.sh",
        "SessionStart": _WIZARD_HOOKS_DIR / "session-start-minimal.sh",
    },
    "copilot": {
        "sessionEnd": _WIZARD_HOOKS_DIR / "session-end.sh",
        "sessionStart": _WIZARD_HOOKS_DIR / "session-start-minimal.sh",
    },
}


def refresh_hooks() -> None:
    """Copy hook scripts from the installed package into ~/.wizard/hooks/.

    Called by `wizard setup` and `wizard update` so the stable ~/.wizard/hooks/
    path always reflects the currently installed version. Performs a full sync
    by removing files in the destination that are not in the package.
    """
    pkg_hooks = importlib.resources.files("wizard").joinpath("hooks")
    _WIZARD_HOOKS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Identify what should be there
    pkg_hook_names = {f.name for f in pkg_hooks.iterdir() if not f.name.startswith("__")}

    # 2. Remove obsolete files from ~/.wizard/hooks/
    for existing in _WIZARD_HOOKS_DIR.iterdir():
        if existing.is_file() and existing.name not in pkg_hook_names:
            existing.unlink()

    # 3. Copy/overwrite from package
    for script_name in pkg_hook_names:
        src = pkg_hooks.joinpath(script_name)
        dest = _WIZARD_HOOKS_DIR / script_name
        dest.write_bytes(src.read_bytes())
        dest.chmod(0o755)


def register_hook(agent_id: str) -> bool:
    """Install wizard hook(s) into agent's hooks config. Idempotent.

    Returns True if agent is supported, False otherwise.
    """
    if agent_id not in _HOOK_CONFIGS or agent_id not in _HOOK_SCRIPTS:
        return False
    config_path, hooks_key = _HOOK_CONFIGS[agent_id]
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if config_path.exists():
        try:
            data = json.loads(config_path.read_text())
        except (json.JSONDecodeError, ValueError):
            data = {}
    else:
        data = {}

    hooks = data.setdefault(hooks_key, {})
    changed = False

    for event, script in _HOOK_SCRIPTS[agent_id].items():
        event_hooks = hooks.setdefault(event, [])
        name = script.name  # e.g. "session-end.sh" or "session-start.sh"
        expected_cmd = f"WIZARD_AGENT={agent_id} bash {script}"

        already_correct = any(
            h.get("command", "") == expected_cmd
            for entry in event_hooks
            for h in entry.get("hooks", [])
        )
        if already_correct:
            continue

        # Remove stale entry (present but wrong command — e.g. missing WIZARD_AGENT prefix).
        hooks[event] = [
            entry
            for entry in event_hooks
            if not any(name in h.get("command", "") for h in entry.get("hooks", []))
        ]
        hooks[event].append(
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": expected_cmd,
                        # Synthesis runs in a detached background process (disown);
                        # this timeout covers only hook script startup (~sub-second).
                        "timeout": 10,
                    }
                ],
            }
        )
        changed = True

    if changed:
        config_path.write_text(json.dumps(data, indent=2))
    return True


def deregister_hook(agent_id: str) -> bool:
    """Remove all wizard hook(s) from agent's hooks config.

    Scans the agent's hooks config and removes any command that contains the
    ~/.wizard/hooks/ directory path. Returns True if any hook was removed.
    """
    if agent_id not in _HOOK_CONFIGS:
        return False
    config_path, hooks_key = _HOOK_CONFIGS[agent_id]

    if not config_path.exists():
        return False

    try:
        data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return False

    hooks = data.get(hooks_key, {})
    if not hooks:
        return False

    removed_any = False
    hooks_dir_str = str(_WIZARD_HOOKS_DIR)

    # We iterate over all events in the agent's config, not just those in _HOOK_SCRIPTS,
    # to ensure we clean up obsolete hooks that might have changed names or events.
    for event in list(hooks.keys()):
        event_hooks = hooks.get(event, [])
        if not isinstance(event_hooks, list):
            continue

        filtered = [
            entry
            for entry in event_hooks
            if not any(
                hooks_dir_str in h.get("command", "")
                for h in entry.get("hooks", [])
                if isinstance(h, dict)
            )
        ]
        if len(filtered) < len(event_hooks):
            if not filtered:
                hooks.pop(event)
            else:
                hooks[event] = filtered
            removed_any = True

    if removed_any:
        data[hooks_key] = hooks
        config_path.write_text(json.dumps(data, indent=2))
    return removed_any


_AGENT_SKILLS_DIRS: dict[str, Path] = {
    "claude-code": Path.home() / ".claude" / "skills",
    "claude-desktop": Path.home() / ".claude" / "skills",
    "gemini": Path.home() / ".gemini" / "skills",
    "codex": Path.home() / ".agents" / "skills",
    "opencode": Path.home() / ".config" / "opencode" / "skills",
    "copilot": Path.home() / ".copilot" / "skills",
}


def install_skills(agent_id: str, source_dir: Path) -> bool:
    """Copy skills from source_dir into the agent's native skills directory.

    Merges — existing skills not in source_dir are left untouched.
    Returns True if agent has a known skills dir, False otherwise.
    """
    if agent_id not in _AGENT_SKILLS_DIRS or not source_dir.exists():
        return False
    dest = _AGENT_SKILLS_DIRS[agent_id]
    dest.mkdir(parents=True, exist_ok=True)
    for skill_dir in source_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_dest = dest / skill_dir.name
        if skill_dest.exists():
            shutil.rmtree(skill_dest)
        shutil.copytree(skill_dir, skill_dest,
                        ignore=shutil.ignore_patterns("SKILL-POST.md"))
    return True


def uninstall_skills(agent_id: str, source_dir: Path) -> bool:
    """Remove wizard-managed skills from the agent's native skills directory.

    Only removes skill subdirectories that exist in source_dir — never touches
    skills the user added manually.
    Returns True if any skills were removed.
    """
    if agent_id not in _AGENT_SKILLS_DIRS or not source_dir.exists():
        return False
    dest = _AGENT_SKILLS_DIRS[agent_id]
    if not dest.exists():
        return False
    removed = False
    for skill_dir in source_dir.iterdir():
        if not skill_dir.is_dir():
            continue
        skill_dest = dest / skill_dir.name
        if skill_dest.exists():
            shutil.rmtree(skill_dest)
            removed = True
    return removed


def scan_all_registered() -> list[str]:
    """Fallback: check all known config paths, return agent IDs where wizard key present."""
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
