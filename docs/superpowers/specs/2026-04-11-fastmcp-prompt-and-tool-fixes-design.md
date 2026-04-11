# FastMCP Prompt Rendering & Tool Validation Fixes

## Context

The wizard MCP server (FastMCP 3.2.0) has two runtime bugs:

1. **Prompt rendering crashes** — `session_triage`, `task_investigation`, and
   `meeting_summarisation` all fail with `TypeError: messages[0] must be
   Message or str, got Message`. The prompts return a custom `Message(BaseModel)`
   defined in `src/prompts.py`, but FastMCP's `convert_result` only accepts its
   own `fastmcp.prompts.Message` or plain `str`.

2. **Tool validation errors** — `task_start` and `get_meeting` are called by
   the MCP client with `{}` (no arguments), triggering Pydantic
   `missing_argument` errors. The tool signatures are correct (required params),
   but the docstrings don't tell the caller where to obtain the IDs.

## Fix 1: Prompt Message Type

### What changes

**File:** `src/prompts.py`

- Replace `from pydantic import BaseModel` with `from fastmcp.prompts import Message`
- Delete the custom `Message(BaseModel)` class (lines 6–13)
- No changes to prompt function bodies — they already construct
  `Message(role="user", content=...)` which matches FastMCP's `Message` constructor

### Why this works

FastMCP's `Message.__init__` accepts `content: Any` (auto-normalises to
`TextContent`) and `role: Literal["user", "assistant"]` with default `"user"`.
The existing constructor calls are compatible as-is.

### Tests

`tests/test_prompts.py` checks `result[1].content` — this attribute exists on
FastMCP's `Message` too, so existing tests pass without modification.

### Blast radius

- Only `src/prompts.py` changes
- Nothing else imports the custom `Message` class
- Prompt function signatures and return shapes are unchanged

## Fix 2: Tool Docstrings

### What changes

**File:** `src/tools.py`

Expand docstrings for two tools:

- **`task_start`**: Clarify that `task_id` is the integer ID from the
  `open_tasks` or `blocked_tasks` list returned by `session_start`.
- **`get_meeting`**: Clarify that `meeting_id` is the integer ID from the
  `unsummarised_meetings` list returned by `session_start`.

### Why this works

MCP clients (including Claude) use the tool description to decide how to call
tools. Explicit guidance on where to get the required parameter reduces
mis-invocations.

### Blast radius

- Docstring-only changes — zero behavior change
- No test changes needed

## Files Modified

| File | Change |
|------|--------|
| `src/prompts.py` | Import FastMCP `Message`, delete custom class |
| `src/tools.py` | Expand `task_start` and `get_meeting` docstrings |

## Verification

1. Run `pytest tests/test_prompts.py` — all 5 prompt tests pass
2. Run `pytest tests/test_tools.py` — all tool tests pass
3. Start the server (`python server.py`) and invoke each of the three
   previously-broken prompts via an MCP client to confirm rendering succeeds
