# Middleware — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Middleware

Wizard uses FastMCP middleware to handle cross-cutting concerns — logging, telemetry,
and session state snapshots — without polluting individual tool functions with
infrastructure code. Both middleware classes live in `src/wizard/middleware.py`.

**Why middleware:** Tool functions follow SLAP (single layer of abstraction) and must
not contain logging boilerplate or DB-update plumbing. Middleware intercepts every
`on_call_tool` event and runs concern-specific logic before and after the tool call,
keeping tool code focused on domain logic.

---

## `ToolLoggingMiddleware`

Logs every tool invocation and writes a `ToolCall` row to SQLite.

**What it does:**

1. Extracts `tool_name` from `context.message.name`.
2. Reads `current_session_id` and `agent_session_id` from `ctx.state` (if available).
3. Opens a Sentry span for the tool execution:
   - `op="mcp.tool"`, `name=tool_name`
   - Tags: `tool.name`, `wizard.session_id` (if set), `wizard.agent_session_id` (if set)
4. Writes a `ToolCall` row (`tool_name`, `session_id`, `called_at`) in its own DB transaction.
5. Calls the next middleware/tool via `call_next(context)`.
6. On exception: calls `sentry_sdk.capture_exception(e)`, sets span status to
   `"internal_error"`, then re-raises. The exception is not swallowed — tool error
   propagation continues normally.
7. On success: sets span status to `"ok"` and returns the result.

**Sentry span structure:**

```python
with sentry_sdk.start_span(op="mcp.tool", name=tool_name) as span:
    span.set_tag("tool.name", tool_name)
    span.set_tag("wizard.session_id", session_id)      # only if set
    span.set_tag("wizard.agent_session_id", agent_id)  # only if set
    ...
    sentry_sdk.capture_exception(e)  # on error, then re-raise
```

---

## `SessionStateMiddleware`

Snapshots partial session state after every tool call so that abandoned sessions have
recoverable working sets.

**Why it exists:** `session_end` writes the definitive `SessionState`. If a session is
abandoned (agent crashes, conversation ends without `session_end`), the session row has
no `session_state`. `SessionCloser` uses `snapshot_session_state` data to generate a
meaningful synthetic summary instead of an empty one.

**What `snapshot_session_state` writes:**

1. Sets `WizardSession.last_active_at = datetime.now()`.
2. Queries all distinct `Note.task_id` values for the current session (non-null only).
3. Builds a `SessionState` with `closure_status="interrupted"`, `working_set=[task_ids]`,
   and empty `intent`/`state_delta`/`open_loops`/`next_actions`.
4. Serialises and writes it to `WizardSession.session_state`.

**Skipped tools:** `session_start` and `session_end` are in `_SKIP_TOOLS`. The snapshot
runs *after* `call_next`, so skipping these avoids double-writing state that `session_start`
and `session_end` manage explicitly.

**Silent failure:** All snapshot logic is wrapped in a `try/except`. If the DB write
fails for any reason, a warning is logged and the tool result is returned unchanged.
Snapshot failures never bubble up to the caller.

**`snapshot_session_state` is public:** Tests bypass the FastMCP middleware chain and
call `SessionStateMiddleware().snapshot_session_state(db, session_id)` directly to assert
state transitions without needing a running server.

---

## Registration order in `mcp_instance.py`

```python
mcp.add_middleware(ToolLoggingMiddleware())
mcp.add_middleware(SessionStateMiddleware())
```

FastMCP executes middleware in registration order (outermost first):

1. `ToolLoggingMiddleware` opens the Sentry span, writes `ToolCall`, wraps the call.
2. `SessionStateMiddleware` calls the tool, then snapshots state on return.

This means the Sentry span covers the full duration including the state snapshot.
