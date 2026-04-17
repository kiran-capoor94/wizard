import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_INSTALLED_SKILLS = Path.home() / ".wizard" / "skills"
_PACKAGE_SKILLS = Path(__file__).resolve().parent / "skills"


def load_skill(name: str) -> str | None:
    """Read SKILL.md for the named skill. Checks installed dir first, then package.

    Returns the file content as a string, or None if not found in either location.
    """
    for root in (_INSTALLED_SKILLS, _PACKAGE_SKILLS):
        path = root / name / "SKILL.md"
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to read skill %s from %s: %s", name, path, e)
                return None
    logger.debug("Skill %s not found in installed or package paths", name)
    return None
