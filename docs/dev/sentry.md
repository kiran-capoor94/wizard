# Sentry Integration — Wizard Developer Reference

> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Sentry Integration

Wizard ships optional Sentry integration for distributed tracing and error capture.
It is disabled by default — no data is sent unless explicitly configured.

---

## Configuration fields

Sentry is configured under the `sentry` key in `~/.wizard/config.json`:

| Field                  | Type    | Default | Description                                         |
| ---------------------- | ------- | ------- | --------------------------------------------------- |
| `sentry.dsn`           | `str`   | `""`    | Sentry DSN. Required to enable reporting.           |
| `sentry.enabled`       | `bool`  | `false` | Master switch. Must be `true` to send any data.     |
| `sentry.traces_sample_rate` | `float` | `0.1` | Fraction of transactions to send as traces.    |
| `sentry.profiles_sample_rate` | `float` | `0.1` | Fraction of sampled transactions to profile. |

These map directly to `SentrySettings` in `src/wizard/config.py`.

**How to enable:**

```json
{
  "sentry": {
    "dsn": "https://...",
    "enabled": true,
    "traces_sample_rate": 0.1,
    "profiles_sample_rate": 0.1
  }
}
```

---

## What is traced

Every tool call receives a Sentry span via `ToolLoggingMiddleware` in
`src/wizard/middleware.py`:

```python
with sentry_sdk.start_span(op="mcp.tool", name=tool_name) as span:
    span.set_tag("tool.name", tool_name)
    span.set_tag("wizard.session_id", session_id)      # if available
    span.set_tag("wizard.agent_session_id", agent_id)  # if available
    ...
```

**Span attributes:**

| Attribute                 | Value                                    |
| ------------------------- | ---------------------------------------- |
| `op`                      | `"mcp.tool"`                             |
| `name`                    | Tool name (e.g. `"session_start"`)       |
| `tool.name` tag           | Tool name (duplicated for filtering)     |
| `wizard.session_id` tag   | Integer wizard session ID (if set in ctx.state) |
| `wizard.agent_session_id` tag | Agent UUID (if set in ctx.state)    |

---

## Exception capture

When a tool raises an unhandled exception, `ToolLoggingMiddleware` captures it in Sentry
before re-raising:

```python
except Exception as e:
    sentry_sdk.capture_exception(e)
    span.set_status("internal_error")
    raise
```

The exception is not swallowed — it propagates normally to FastMCP's error handler.
Sentry receives the full exception with stack trace and the span context (tool name,
session tags).

Some tools also call `sentry_sdk.capture_exception(e)` directly for unexpected errors
(e.g. `meeting_tools.py`, `session_tools.py`). These are belt-and-suspenders captures
for code paths outside the middleware span.

---

## Opt-in design

Sentry is initialised in `server.py` only when `settings.sentry.enabled is True` and
`settings.sentry.dsn` is non-empty. If either condition is false, `sentry_sdk` is never
initialised and all `sentry_sdk.*` calls in middleware and tools become no-ops (the
Sentry SDK ships a no-op client for this case).

This means no data is ever sent in a default installation. Users must explicitly add
the `sentry` block to `~/.wizard/config.json` to enable reporting.
