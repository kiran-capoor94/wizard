from pathlib import Path

from fastmcp import FastMCP
from fastmcp.server.providers.skills import SkillsDirectoryProvider

from .config import settings
from .middleware import SessionStateMiddleware, ToolLoggingMiddleware

mcp = FastMCP(
    name=settings.name,
    instructions=(
        "Wizard is Kiran's local memory layer. It syncs Jira and Notion, scrubs PII, "
        "and surfaces structured context across sessions. Meetings can be ingested "
        "via ingest_meeting. Start every session with session_start. End with session_end.\n\n"
        "NOTE-TAKING: Save notes throughout the session using save_note — not just at the end. "
        "Types: investigation (findings), decision (choices made), docs (how things work), "
        "learnings (surprises). Every note needs a task_id and concrete details (file paths, "
        "function names, error messages). After 2+ notes on a task, include a mental_model — "
        "a 2-3 sentence snapshot of your current understanding. "
        "Use the note_guidance prompt for full templates and decision tree."
    ),
    version=settings.version,
    mask_error_details=True,
)

# Skills are served from ~/.wizard/skills/ (copied there by `wizard setup`).
# The package ships skill sources in src/wizard/skills/ but the MCP server
# reads from the installed location so users can customise without touching
# the package.
_installed_skills = Path.home() / ".wizard" / "skills"
_package_skills = Path(__file__).resolve().parent / "skills"

_roots = [p for p in [_installed_skills, _package_skills] if p.exists()]
if _roots:
    mcp.add_provider(SkillsDirectoryProvider(roots=_roots))

mcp.add_middleware(ToolLoggingMiddleware())
mcp.add_middleware(SessionStateMiddleware())
