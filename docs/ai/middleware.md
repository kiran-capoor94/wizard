# Middleware Reference

Source: `src/wizard/middleware.py`

Both middleware classes are registered in `src/wizard/mcp_instance.py`:
```python
mcp.add_middleware(ToolLoggingMiddleware())
mcp.add_middleware(SessionStateMiddleware())
```

---

## `ToolLoggingMiddleware`

Runs **before** calling `next` — wraps every tool call.

**DB write:** Creates a `ToolCall` row per invocation:
- `tool_name`: `context.message.name`
- `session_id`: read from FastMCP state key `current_session_id`

`agent_session_id` is also read from FastMCP state (key `agent_session_id`) but is not stored in `ToolCall` — used only for Sentry tagging.

**Sentry span:**
- `op="mcp.tool"`, `name=tool_name`, `description="MCP tool execution: <tool_name>"`
- Tags set: `tool.name`, `wizard.session_id` (if present), `wizard.agent_session_id` (if present)
- On success: `span.set_status("ok")`

**Exception handling:**
- Calls `sentry_sdk.capture_exception(e)`
- Sets `span.set_status("internal_error")`
- Sets `span.set_data("exception", str(e))` and `span.set_data("exception_type", type(e).__name__)`
- **Re-raises** the exception (does not swallow)

---

## `SessionStateMiddleware`

Runs **after** calling `next` — calls `call_next` first, then snapshots state.

**Skip list:** `_SKIP_TOOLS = frozenset({"session_start", "session_end"})`
Tools in this set are passed through without any state snapshot.

**Per-call behaviour (for non-skipped tools):**
1. Reads `current_session_id` from FastMCP state
2. If `session_id` is not None: calls `self.snapshot_session_state(db, session_id)`
3. Also calls `sentry_sdk.set_user({"id": str(session_id)})` to bind user context

**Failures:** silently logged via `logger.warning()`; **never raises**.

---

### `snapshot_session_state(db, session_id: int) -> None`

**Public method** — tests call this directly without the FastMCP middleware chain.

Steps:
1. `db.get(WizardSession, session_id)` — no-op if session not found
2. `session.last_active_at = datetime.datetime.now()`
3. Queries `Note.task_id` WHERE `Note.session_id == session_id AND Note.task_id IS NOT NULL`, DISTINCT → `working_set: list[int]`
4. Builds `SessionState(closure_status="interrupted", working_set=..., intent="", state_delta="", open_loops=[], next_actions=[])`
5. `session.session_state = state.model_dump_json()`
6. `db.add(session)` + `db.flush()`

**Effect:** Every non-excluded tool call incrementally stamps the session with `last_active_at` and a partial `SessionState` so abandoned sessions have recoverable working-set context.
