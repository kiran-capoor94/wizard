import logging
import re
from pathlib import Path

import yaml
from fastmcp.exceptions import ToolError

from ..config import ModesSettings, settings
from ..database import get_session
from ..mcp_instance import mcp
from ..models import WizardSession
from ..schemas import GetModesResponse, ModeInfo, SetModeResponse

logger = logging.getLogger(__name__)

_INSTALLED_SKILLS = Path.home() / ".wizard" / "skills"
_PACKAGE_SKILLS = Path(__file__).resolve().parent.parent / "skills"

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---", re.DOTALL)


def build_available_modes(
    modes: ModesSettings,
    roots: list[Path] | None = None,
) -> list[ModeInfo]:
    """Return ModeInfo for each skill name in modes.allowed, reading frontmatter.

    Skips skills not found in any root. Checks installed dir first, then package.
    """
    if not modes.allowed:
        return []

    if roots is None:
        roots = [_INSTALLED_SKILLS, _PACKAGE_SKILLS]

    result: list[ModeInfo] = []
    for name in modes.allowed:
        info = _load_mode_info(name, roots)
        if info is not None:
            result.append(info)
    return result


def _load_mode_info(name: str, roots: list[Path]) -> ModeInfo | None:
    """Read SKILL.md frontmatter for a named skill. Returns None if not found."""
    for root in roots:
        path = root / name / "SKILL.md"
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                m = _FRONTMATTER_RE.match(content)
                if m:
                    fm = yaml.safe_load(m.group(1))
                    description = fm.get("description", "")
                    if isinstance(description, str):
                        description = description.strip()
                    return ModeInfo(name=name, description=str(description))
            except (OSError, yaml.YAMLError) as e:
                logger.warning("Failed to read skill frontmatter %s: %s", name, e)
                return None
    logger.debug("Mode skill %s not found in any root", name)
    return None


async def get_modes(
    session_id: int | None = None,
    _roots: list[Path] | None = None,
) -> GetModesResponse:
    """List available modes and the active mode for the given session (if any)."""
    available = build_available_modes(settings.modes, roots=_roots)

    active_mode: str | None = None
    if session_id is not None:
        with get_session() as db:
            session = db.get(WizardSession, session_id)
            if session is not None:
                active_mode = session.active_mode

    return GetModesResponse(available_modes=available, active_mode=active_mode)


mcp.tool()(get_modes)


async def set_mode(
    session_id: int,
    mode_name: str | None,
    _roots: list[Path] | None = None,
) -> SetModeResponse:
    """Activate or clear the mode for the given session.

    mode_name: skill name to activate (must be in settings.modes.allowed),
               or None to clear the active mode.
    """
    if mode_name is not None and mode_name not in settings.modes.allowed:
        raise ToolError(
            f"'{mode_name}' is not in allowed modes: {settings.modes.allowed}"
        )

    with get_session() as db:
        session = db.get(WizardSession, session_id)
        if session is None:
            raise ToolError(f"Session {session_id} not found")

        session.active_mode = mode_name
        db.add(session)

    if mode_name is None:
        return SetModeResponse(active_mode=None, description=None, instruction=None)

    info = _load_mode_info(mode_name, roots=_roots or [_INSTALLED_SKILLS, _PACKAGE_SKILLS])
    description = info.description if info else None
    return SetModeResponse(
        active_mode=mode_name,
        description=description,
        instruction=f"Invoke skill: {mode_name} now to load this mode's behavior.",
    )


mcp.tool()(set_mode)
