# Elicitation — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Elicitation

Wizard uses `ctx.elicit()` — a FastMCP mechanism for requesting structured user input
during a tool call — to get confirmation before irreversible or ambiguous actions.

---

## What `ctx.elicit()` is

`ctx.elicit()` pauses the tool call and sends a structured prompt to the MCP client,
which surfaces it to the user as an interactive form. The response is typed (Pydantic
model or a primitive like `str`), so the tool receives a validated value directly.

Not all MCP transports support elicitation. When the transport does not support it (or
when running in a test harness without a real client), `ctx.elicit()` raises an exception.
All wizard elicitation calls catch this exception and fall back to a safe default.

---

## Tools that use elicitation

### `check_duplicate_name()` — `tools/task_fields.py`

Checks whether a new task name fuzzy-matches an existing task. If a match is found,
elicits user confirmation before proceeding.

```python
result = await ctx.elicit(
    f"A task named {matching!r} already exists. Create anyway?",
    response_type=_ConfirmCreate,  # field: create_anyway: bool
)
```

**Safe default when elicitation unavailable:** returns `None`, which means the tool
proceeds with creating the new task (optimistic — don't block the user).

**Return value:** the matched existing task name (to use instead of creating) if the
user declines, or `None` to proceed with creation.

---

### `elicit_done_confirmation()` — `tools/task_fields.py`

Prompts the engineer to confirm before marking a task as done, since doing so closes it.

```python
result = await ctx.elicit(
    f"Mark {task_name!r} as done? This closes the task.",
    response_type=_ConfirmDone,  # field: confirmed: bool
)
```

**Safe default when elicitation unavailable:** returns `True` (proceed with marking done).
Rationale: the engineer explicitly requested the status change; blocking it silently
would be worse than allowing it.

---

### `_elicit_task_link_confirmation()` — `tools/meeting_tools.py`

Before linking tasks to a meeting summary via `save_meeting_summary`, asks the engineer
to confirm the link.

```python
result = await ctx.elicit(
    f"Link {len(task_ids)} task(s) to this meeting summary? ({names_str})",
    response_type=_ConfirmLink,  # field: confirmed: bool
)
```

**Safe default when elicitation unavailable:** returns `None` (skip linking). Rationale:
task linking is additive but non-critical — skipping it is safer than silently linking
the wrong tasks.

---

## When to add elicitation

Add `ctx.elicit()` only for:

- **Irreversible actions** — closing a task, overwriting data, permanent deletes.
- **Ambiguous identity** — duplicate names, fuzzy matches where the wrong choice
  has a real cost.

Do not add elicitation for:

- Reads or searches (no side effects).
- Actions that are easily undone.
- Mechanical formatting or slug generation (use direct logic, not `ctx.sample()` either).

---

## Testing elicitation

Tests cannot use a real FastMCP context. Inject a fake `ctx` that returns the desired
elicitation response:

```python
class FakeCtx:
    async def elicit(self, message, response_type):
        from fastmcp.server.elicitation import AcceptedElicitation
        return AcceptedElicitation(data=response_type(confirmed=True))

result = await elicit_done_confirmation(FakeCtx(), "My Task")
assert result is True
```

To test the unavailable-transport path, raise an exception from `elicit`:

```python
class UnavailableCtx:
    async def elicit(self, message, response_type):
        raise RuntimeError("elicitation not supported")

result = await elicit_done_confirmation(UnavailableCtx(), "My Task")
assert result is True  # safe default
```
