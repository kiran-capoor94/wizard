import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_INSTALLED_SKILLS = Path.home() / ".wizard" / "skills"
_PACKAGE_SKILLS = Path(__file__).resolve().parent / "skills"

# Canonical skill names — use these instead of magic strings.
SKILL_SESSION_START = "session-start"
SKILL_SESSION_RESUME = "session-resume"
SKILL_SESSION_END = "session-end"
SKILL_TASK_START = "task-start"
SKILL_MEETING = "meeting"
SKILL_ARCHITECTURE_DEBATE = "architecture-debate"
SKILL_CODE_REVIEW = "code-review"
SKILL_NOTE = "note"
SKILL_TRIAGE = "what-should-i-work-on"


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


def load_skill_post(name: str) -> str | None:
    """Read SKILL-POST.md for the named skill. Internal only — never registered.

    Checks installed dir first, then package. Returns None if not found.
    Post-call content (schema reference, hard gates, presentation rules)
    is injected in tool responses; it is NOT copied to agent skill dirs.
    """
    for root in (_INSTALLED_SKILLS, _PACKAGE_SKILLS):
        path = root / name / "SKILL-POST.md"
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8")
            except OSError as e:
                logger.warning("Failed to read skill-post %s from %s: %s", name, path, e)
                return None
    logger.debug("Skill-post %s not found in installed or package paths", name)
    return None
