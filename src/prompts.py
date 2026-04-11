from fastmcp.prompts import Message

from .mcp_instance import mcp


def session_triage(session_data: str) -> list[Message]:
    """Guides prioritisation after session_start."""
    return [
        Message(
            role="user",
            content=(
                "You just started a Wizard session. The data below contains your open tasks, "
                "blocked tasks, unsummarised meetings, and sync results.\n\n"
                "Triage priority:\n"
                "1. Check sync results for failures — if Jira or Notion failed to sync, note it and move on\n"
                "2. Blocked tasks first — identify what's blocking and whether you can unblock anything\n"
                "3. Unsummarised meetings — these need summaries before context is lost\n"
                "4. Open tasks by priority — high priority first, then medium, then low\n\n"
                "For each item, decide: act now, defer, or skip. Present your triage to the user "
                "and ask which item to start with."
            ),
        ),
        Message(
            role="user",
            content=f"Session data:\n\n{session_data}",
        ),
    ]


def task_investigation(task_data: str) -> list[Message]:
    """Directs Claude Code on how to work a task."""
    return [
        Message(
            role="user",
            content=(
                "You're starting work on a task. The data below contains the task details "
                "and all prior notes from previous sessions.\n\n"
                "Investigation guidelines:\n"
                "1. Read all prior notes first — understand what's already been done\n"
                "2. If compounding is true, build on existing investigation — don't repeat work\n"
                "3. If the task is code-related, use Serena to explore the codebase\n"
                "4. Record your findings as notes (investigation, decision, docs, learnings)\n"
                "5. If you need clarification from the user, ask — don't assume\n\n"
                "Your goal is to make progress on this task and leave clear notes for the next session."
            ),
        ),
        Message(
            role="user",
            content=f"Task data:\n\n{task_data}",
        ),
    ]


def meeting_summarisation(meeting_data: str) -> list[Message]:
    """Template for processing meeting transcripts."""
    return [
        Message(
            role="user",
            content=(
                "You're summarising a meeting. The data below contains the meeting transcript "
                "and any linked tasks.\n\n"
                "Summarisation template:\n"
                "1. Key decisions — what was decided and by whom\n"
                "2. Action items — concrete next steps with owners if mentioned\n"
                "3. Open questions — unresolved topics that need follow-up\n"
                "4. Relevant tasks — if any open tasks were discussed, note what was said\n\n"
                "Keep the summary concise but complete. Link to relevant tasks by ID if they "
                "were mentioned. The summary will be stored and written back to Notion."
            ),
        ),
        Message(
            role="user",
            content=f"Meeting data:\n\n{meeting_data}",
        ),
    ]


def session_wrapup() -> str:
    """Guides session end."""
    return (
        "You're ending a Wizard session. Before closing:\n\n"
        "1. Summarise what was accomplished this session\n"
        "2. List what's still open or in progress\n"
        "3. Note any status changes made to tasks\n"
        "4. Highlight anything that needs attention next session\n\n"
        "Keep it brief — this summary is for continuity between sessions. "
        "Focus on what changed and what matters next."
    )


def user_elicitation() -> str:
    """Meta-prompt: when and how to ask the user for direction."""
    return (
        "When working with Wizard session data, follow these rules for user interaction:\n\n"
        "Ask the user when:\n"
        "- Multiple tasks have similar priority and you need to choose which to work on\n"
        "- A blocked task's blocker is ambiguous and you need context\n"
        "- A meeting summary needs domain-specific interpretation\n"
        "- You're unsure whether to change a task's status\n"
        "- The triage order isn't obvious from priority alone\n\n"
        "Don't ask when:\n"
        "- There's one clear highest-priority item\n"
        "- The next step is obvious from prior notes\n"
        "- You're just recording findings as notes\n\n"
        "Prefer giving the user a concrete recommendation with your reasoning, "
        "then asking for confirmation, over open-ended questions."
    )


# ---------------------------------------------------------------------------
# Register prompts with MCP
# ---------------------------------------------------------------------------

mcp.prompt()(session_triage)
mcp.prompt()(task_investigation)
mcp.prompt()(meeting_summarisation)
mcp.prompt()(session_wrapup)
mcp.prompt()(user_elicitation)
