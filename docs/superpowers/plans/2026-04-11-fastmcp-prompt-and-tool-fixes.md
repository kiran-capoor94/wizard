# FastMCP Prompt & Tool Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix prompt rendering crashes (wrong Message type) and improve tool discoverability (better docstrings) so the wizard MCP server works correctly with FastMCP 3.2.0.

**Architecture:** Replace the custom `Message(BaseModel)` in `src/prompts.py` with FastMCP's own `Message` class. Expand tool docstrings in `src/tools.py` to guide MCP clients on required parameters.

**Tech Stack:** Python 3.14, FastMCP 3.2.0, pytest

---

## File Structure

| File                    | Action              | Responsibility                                       |
| ----------------------- | ------------------- | ---------------------------------------------------- |
| `src/prompts.py`        | Modify              | Replace custom Message import with FastMCP's Message |
| `src/tools.py`          | Modify              | Expand `task_start` and `get_meeting` docstrings     |
| `tests/test_prompts.py` | Verify (no changes) | Existing tests validate prompt return shape          |

---

### Task 1: Fix prompt Message type

**Files:**

- Modify: `src/prompts.py:1-14`
- Test: `tests/test_prompts.py`

- [ ] **Step 1: Run existing prompt tests to confirm current failure mode**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_prompts.py -v`

Expected: All 5 tests PASS (the unit tests don't go through FastMCP's `convert_result`, so they pass even with the wrong Message type — the bug only manifests at runtime through the MCP server).

- [ ] **Step 2: Replace the import and delete the custom Message class**

In `src/prompts.py`, replace lines 1–14:

```python
from pydantic import BaseModel

from .mcp_instance import mcp


class Message(BaseModel):
    """Lightweight prompt message.

    FastMCP accepts any object with ``role`` and ``content`` attributes.
    """

    role: str
    content: str
```

With:

```python
from fastmcp.prompts import Message

from .mcp_instance import mcp
```

No other changes needed — the three prompt functions already call `Message(role="user", content=...)` which matches FastMCP's `Message.__init__(content, role)` via keyword args.

- [ ] **Step 3: Run prompt tests to verify nothing broke**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_prompts.py -v`

Expected: All 5 tests PASS. The tests check `result[1].content` which exists on FastMCP's `Message` too.

- [ ] **Step 4: Run the full test suite to check for collateral**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/prompts.py
git commit -m "fix: use FastMCP Message instead of custom class

The custom Message(BaseModel) in src/prompts.py was not recognised by
FastMCP's convert_result, which only accepts fastmcp.prompts.Message
or str. This caused TypeError on all three multi-message prompts."
```

---

### Task 2: Improve tool docstrings

**Files:**

- Modify: `src/tools.py:63-64` (task_start docstring)
- Modify: `src/tools.py:139-140` (get_meeting docstring)

- [ ] **Step 1: Update `task_start` docstring**

In `src/tools.py`, replace line 64:

```python
    """Returns full task context + all prior notes for compounding context."""
```

With:

```python
    """Returns full task context + all prior notes for compounding context.

    task_id: integer task ID from the open_tasks or blocked_tasks list
    returned by session_start. Call session_start first to get available IDs.
    """
```

- [ ] **Step 2: Update `get_meeting` docstring**

In `src/tools.py`, replace line 140:

```python
    """Returns meeting transcript and linked open tasks."""
```

With:

```python
    """Returns meeting transcript and linked open tasks.

    meeting_id: integer meeting ID from the unsummarised_meetings list
    returned by session_start. Call session_start first to get available IDs.
    """
```

- [ ] **Step 3: Run tool tests to verify nothing broke**

Run: `cd /home/agntx/Documents/repos/personal/wizard && python -m pytest tests/test_tools.py -v`

Expected: All tool tests PASS (docstring-only changes).

- [ ] **Step 4: Commit**

```bash
git add src/tools.py
git commit -m "docs: clarify task_start and get_meeting param sources

Guide MCP clients to call session_start first to obtain the required
task_id and meeting_id values."
```

---

## Verification

After both tasks, run the full suite and do a manual smoke test:

```bash
# Full test suite
cd /home/agntx/Documents/repos/personal/wizard && python -m pytest -v

# Smoke test: start server and invoke a prompt
# (manual — start the server and call session_triage via an MCP client)
```
