# Wizard Modernization — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement this plan step-by-step.

**Goal:** Modernize Wizard codebase using library best practices:
1. FastMCP middleware for auto-logging
2. FastMCP dependency injection for DB sessions
3. Pydantic SecretStr for sensitive config
4. Tool annotations for better LLM optimization

**Timeline:** Incremental — one phase at a time, tests must pass after each.

---

## Phase 0: ToolLoggingMiddleware

### Current State
Every tool has `logger.info("tool_name ...")`: 14 places

### Target State
Middleware auto-logs all tool invocations:
```python
# mcp_instance.py
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import ToolResult

class ToolLoggingMiddleware(Middleware):
    async def on_call_tool(
        self, context: MiddlewareContext, call_next
    ) -> ToolResult:
        tool_name = context.params.name
        args = context.params.arguments
        logger.info(f"{tool_name} called with args={args}")
        return await call_next(context)
```

### Steps

0.1: [ ] Create `src/wizard/middleware.py`:
```python
import logging
from typing import Any

from fastmcp.server.middleware import Middleware, MiddlewareContext
from mcp.types import ToolResult

logger = logging.getLogger(__name__)


class ToolLoggingMiddleware(Middleware):
    async def on_call_tool(
        self, context: MiddlewareContext, call_next
    ) -> ToolResult:
        tool_name = context.params.name
        args = context.params.arguments
        logger.info(f"{tool_name} ...")
        return await call_next(context)
```

0.2: [ ] Add middleware to `mcp_instance.py`:
```python
from .middleware import ToolLoggingMiddleware

mcp = FastMCP("Wizard")
mcp.add_middleware(ToolLoggingMiddleware())
```

0.3: [ ] Remove `logger.info("tool_name ...") from all 14 tools

0.4: [ ] Run tests — should pass

---

## Phase 1: FastMCP Depends() Refactor

### Current State
```python
async def some_tool(ctx: Context, param: str) -> Response:
    try:
        with get_session() as db:  # 14 places
            session_id = await ctx.get_state("current_session_id")
            await _log_tool_call(db, "some_tool", session_id=session_id)
            return Response(...)
    except ValueError as e:
        logger.warning("some_tool failed: %s", e)
        raise ToolError(str(e)) from e
```

### Target State
```python
async def some_tool(
    param: str,
    db: Session = Depends(get_db_session),
    session_id: int | None = Depends(get_current_session_id),
) -> Response:
    await _log_tool_call(db, "some_tool", session_id=session_id)
    return Response(...)
```

### Step 1.1: Add Dependencies to `deps.py`

```python
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastmcp.dependencies import Depends, CurrentContext
from fastmcp.server.context import Context
from sqlmodel import Session

from .database import engine


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[Session, None]:
    with Session(engine) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


async def get_current_session_id(ctx: Context = Depends(CurrentContext)) -> int | None:
    return await ctx.get_state("current_session_id")


async def set_session_id(session_id: int, ctx: Context = Depends(CurrentContext)) -> None:
    await ctx.set_state("current_session_id", session_id)


async def clear_session_id(ctx: Context = Depends(CurrentContext)) -> None:
    await ctx.delete_state("current_session_id")
```

### Step 1.2: Migrate Tools (migrate after Phase 0)

**Batch A — Read-only tools:**
- [ ] `get_meeting`
- [ ] `rewind_task`
- [ ] `what_am_i_missing`

**Batch B — Write tools:**
- [ ] `save_note`
- [ ] `save_meeting_summary`

**Batch C — Update tools:**
- [ ] `update_task`
- [ ] `update_task_status`

**Batch D — Session lifecycle:**
- [ ] `session_start`
- [ ] `session_end`

**Batch E — Standalone tools:**
- [ ] `task_start`
- [ ] `ingest_meeting`
- [ ] `create_task`
- [ ] `resume_session`

### Step 1.3: Update Tests

```python
def _patch_tools(db_session, sync=None, wb=None, notion=None):
    async def mock_get_db_session():
        yield db_session
        db_session.flush()
    
    return {
        "get_db_session": mock_get_db_session,
        # ... existing patches ...
    }
```

---

## Phase 2: Pydantic SecretStr for Config

### Current State (`config.py`)
```python
class JiraSettings(BaseModel):
    token: str = ""      # Plain text!
    email: str = ""

class NotionSettings(BaseModel):
    token: str = ""      # Plain text!
```

### Target State
```python
from pydantic import SecretStr

class JiraSettings(BaseModel):
    token: SecretStr = SecretStr("")
    email: str = ""

class NotionSettings(BaseModel):
    token: SecretStr = SecretStr("")
```

### Steps

2.1: [ ] Update `config.py` with SecretStr

2.2: [ ] Update integration clients to use `.get_secret_value()`:
```python
# integrations.py
self._token = token.get_secret_value() if isinstance(token, SecretStr) else token
```

2.3: [ ] Run tests

2.4: [ ] Optional: Add `secrets_dir` for k8s/docker:
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(secrets_dir="/run/secrets")
```

---

## Phase 3: Tool Annotations

### Tool Mapping

| Tool | `readOnlyHint` | `destructiveHint` | `idempotentHint` |
|------|----------------|-------------------|------------------|
| `session_start` | - | - | - |
| `task_start` | True | - | - |
| `save_note` | - | - | - |
| `update_task` | - | False | True |
| `update_task_status` | - | False | - |
| `get_meeting` | True | - | - |
| `save_meeting_summary` | - | - | - |
| `session_end` | - | - | - |
| `ingest_meeting` | - | - | - |
| `create_task` | - | - | - |
| `rewind_task` | True | - | - |
| `what_am_i_missing` | True | - | - |
| `resume_session` | - | - | - |

### Steps

3.1: [ ] Add imports:
```python
from mcp.types import ToolAnnotations
```

3.2: [ ] Add annotations to each tool

---

## Files Changed

| File | Phase 0 | Phase 1 | Phase 2 | Phase 3 |
|------|---------|---------|---------|---------|
| `src/wizard/middleware.py` | New | - | - | - |
| `src/wizard/mcp_instance.py` | Add middleware | - | - | - |
| `src/wizard/deps.py` | - | Add deps | - | - |
| `src/wizard/config.py` | - | - | SecretStr | - |
| `src/wizard/integrations.py` | - | - | .get_secret_value() | - |
| `src/wizard/tools.py` | Remove logger | Depends() | - | ToolAnnotations |
| `tests/helpers.py` | - | Update patches | - | - |
| `tests/test_*.py` | - | Fix if needed | Fix if needed | - |

---

## Testing

- [ ] Phase 0: Middleware logs, all tests pass
- [ ] Phase 1: All 14 tools migrated, 400+ tests pass
- [ ] Phase 2: Config loads correctly, tests pass
- [ ] Phase 3: No functional changes, tests pass

---

## Success Criteria

- [ ] ~140 lines of boilerplate removed (14 logger + 100 session + 14 try/except)
- [ ] Middleware auto-logs all tool invocations
- [ ] All tools use `Depends()` for session injection
- [ ] Sensitive config uses `SecretStr`
- [ ] All tools have appropriate annotations
- [ ] All 400+ tests pass

---

## Risks

1. **Middleware logging** — May be too verbose; can tune log level
2. **SecretStr** — May break tests that compare token strings
3. **Depends()** — External MCP clients use names, should be fine
4. **Incremental** — Can be done in small steps with tests passing
