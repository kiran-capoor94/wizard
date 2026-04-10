from fastmcp import FastMCP

from .config import settings

mcp = FastMCP(
    name=settings.name,
    instructions=(
        "Wizard is Kiran's local memory layer. It syncs Jira and Notion, scrubs PII, "
        "and surfaces structured context across sessions. Meetings can be ingested "
        "via ingest_meeting. Start every session with session_start. End with session_end."
    ),
    version=settings.version,
    mask_error_details=True,
)
