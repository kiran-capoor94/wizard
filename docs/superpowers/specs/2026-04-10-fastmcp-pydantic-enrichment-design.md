# Wizard v1.1.0 — FastMCP & Pydantic Enrichment

**Date:** 2026-04-10  
**Status:** Approved  
**Approach:** Interleaved (Type Safety + Features Together)

---

## Problem

Wizard v1.1.0 uses FastMCP 3.2.0+ but only leverages Tools and Instructions.
The integration layer returns raw `list[dict]` with string-key access throughout
services. ~50 lines of hardcoded mapping dicts sit in `services.py`. Every tool
function converts Pydantic models back to dicts via `.model_dump(mode="json")`.

FastMCP offers Resources, Prompts, Context, and more — none of which are used.
Claude Code is the sole consumer and supports all of these features natively.

## Consumer

Claude Code only. No multi-client considerations.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Integration models | Pydantic for outputs only | Notion property helpers stay as-is — isolated, not worth wrapping |
| Mapping dicts | Dedicated `src/mappers.py` module | SRP, testable in isolation, no layer coupling |
| Tool return types | Return Pydantic models directly | FastMCP 3.2.0+ handles serialization; spike test to verify |
| Resources | Full layer — session, tasks, config | Claude Code can pull context on demand without tool invocation |
| Prompts | 5 prompts for reasoning scaffolding | Critical for directing Claude Code's behaviour with Wizard data |
| Context | Logging + progress only | No session state (WizardSession handles it), no lifespan (future iteration) |

## Implementation Order

Approach C — Interleaved: type safety foundation first, then FastMCP features
built on typed data. No rework.

1. Integration response models
2. Mapper module
3. Resources (on typed data)
4. Tool return types
5. Prompts
6. Context integration

---

## Section 1: Integration Response Models

New Pydantic models in `src/schemas.py`:

```python
class JiraTaskData(BaseModel):
    key: str
    summary: str
    status: str
    priority: str
    issue_type: str
    url: str = ""

class NotionTaskData(BaseModel):
    notion_id: str
    name: str
    status: str
    priority: str
    due_date: str | None = None
    jira_url: str | None = None
    jira_key: str | None = None

class NotionMeetingData(BaseModel):
    notion_id: str
    title: str
    categories: list[str]
    summary: str
    krisp_url: str | None = None
    date: str | None = None
```

### Changes

- `JiraClient.fetch_open_tasks()` returns `list[JiraTaskData]` instead of `list[dict]`
- `NotionClient.fetch_tasks()` returns `list[NotionTaskData]`
- `NotionClient.fetch_meetings()` returns `list[NotionMeetingData]`
- Services access `.key`, `.summary` instead of `["key"]`, `["summary"]`

### Unchanged

- Internal parsing logic inside each client method
- Notion property extraction helpers (`_get_title`, `_get_select`, etc.)
- SQLModel domain models

---

## Section 2: Mapper Module

New file `src/mappers.py` with dedicated mapper classes.

```python
class StatusMapper:
    @staticmethod
    def jira_to_local(jira_status: str) -> TaskStatus: ...

    @staticmethod
    def notion_to_local(notion_status: str) -> TaskStatus: ...

    @staticmethod
    def local_to_jira(status: TaskStatus) -> str: ...

    @staticmethod
    def local_to_notion(status: TaskStatus) -> str: ...

class PriorityMapper:
    # Same pattern: jira_to_local, notion_to_local, local_to_jira, local_to_notion

class MeetingCategoryMapper:
    # Bidirectional meeting category translation for Notion
```

### Changes

- All 6 mapping dicts move from `services.py` to `mappers.py`
- `SyncService` and `WriteBackService` call mapper methods instead of indexing dicts
- New `tests/test_mappers.py` verifies bidirectional correctness

### Unknown value handling

When an unrecognised status/priority string arrives, fall back to a sensible
default (`TaskStatus.TODO`, `TaskPriority.MEDIUM`) and log a warning. No
exceptions for data mapping.

### Unchanged

- Mapping values themselves — same translations, relocated
- Services still own sync/write-back orchestration

---

## Section 3: Tool Return Types

Remove `.model_dump(mode="json")` from all tool functions. Return Pydantic
models directly and let FastMCP handle serialization.

### Before

```python
@_mcp.tool()
def session_start() -> dict:
    return SessionStartResponse(...).model_dump(mode="json")
```

### After

```python
@_mcp.tool()
def session_start() -> SessionStartResponse:
    return SessionStartResponse(...)
```

### Changes

- All ~8 tool functions change return type from `dict` to their Pydantic model
- All `.model_dump(mode="json")` calls removed

### Risk mitigation

A spike test runs first to confirm FastMCP 3.2.0+ correctly serializes our
response models (nested models, enums, datetimes, Optional fields). If edge
cases are found, we keep `.model_dump()` and file upstream.

### Unchanged

- Response schema models themselves
- Business logic inside tool functions
- Tool input parameters

---

## Section 4: Resources

Three resource groups, all read-only, in a new `src/resources.py` file.

### Session state

```python
@mcp.resource("wizard://session/current")
def current_session() -> SessionResource:
    """Active session with open/blocked task counts and sync status."""
```

### Task context

```python
@mcp.resource("wizard://tasks/{task_id}/context")
def task_context(task_id: int) -> TaskContextResource:
    """Full task detail — metadata, notes, history."""

@mcp.resource("wizard://tasks/open")
def open_tasks() -> OpenTasksResource:
    """All open tasks with status and priority."""

@mcp.resource("wizard://tasks/blocked")
def blocked_tasks() -> BlockedTasksResource:
    """All blocked tasks with blocking reasons."""
```

### Configuration

```python
@mcp.resource("wizard://config")
def wizard_config() -> ConfigResource:
    """Current config — enabled integrations, active sources, database path."""
```

### Changes

- New resource response models in `src/schemas.py`
- New `src/resources.py` with resource handler functions
- Resources reuse existing repositories and `get_session()` pattern

### Key distinction from tools

Resources are stateless reads. They don't create sessions, trigger syncs, or
mutate anything. Claude Code pulls them for context without side effects. Tools
remain the action layer.

### Unchanged

- Tool functions
- Repositories
- Database schema

---

## Section 5: Prompts

Five prompts in a new `src/prompts.py` file that guide Claude Code's reasoning.

### Session triage

```python
@mcp.prompt()
def session_triage(session_data: str) -> str:
    """Guides prioritisation after session_start. Blocked items first,
    then unsummarised meetings, then open tasks by priority."""
```

### Task investigation

```python
@mcp.prompt()
def task_investigation(task_data: str) -> str:
    """Directs Claude Code on how to work a task. Build on prior notes,
    don't repeat work. If code-related, use Serena to investigate."""
```

### Meeting summarisation

```python
@mcp.prompt()
def meeting_summarisation(meeting_data: str) -> str:
    """Template for processing meeting transcripts. Extract action items,
    decisions, open questions. Link to relevant tasks if mentioned."""
```

### Session wrap-up

```python
@mcp.prompt()
def session_wrapup() -> str:
    """Guides session end. Summarise accomplishments, open items,
    what changed. Save notes for continuity."""
```

### User elicitation

```python
@mcp.prompt()
def user_elicitation() -> str:
    """Meta-prompt: when and how to ask the user for direction.
    If priority is ambiguous or multiple tasks compete, ask — don't assume."""
```

### Changes

- New `src/prompts.py` with prompt handler functions
- Prompts return structured multi-turn `Message` lists where appropriate
- Prompt content encodes Kiran's workflow preferences

### Return format

- **Single string:** `user_elicitation`, `session_wrapup` — these are
  standalone instructions, no conversation scaffolding needed.
- **Multi-turn Message list:** `session_triage`, `task_investigation`,
  `meeting_summarisation` — these set up a system message with instructions
  followed by a user message containing the data to reason on.

### Parameter design

Prompts that operate on data (session triage, task investigation, meeting
summarisation) accept data as a string parameter. Parameterless prompts
(wrap-up, elicitation) have no inputs. Claude Code orchestrates: pull data
via tool/resource, then invoke prompt to reason on it.

### Unchanged

- Tools and Resources — Prompts don't call them

---

## Section 6: Context Integration

Inject FastMCP `Context` into tools that do multi-step work. Logging and
progress reporting only.

### Tools that get Context

- `session_start` — 3 phases: create session, sync, build response
- `session_end` — write-back, close session
- `ingest_meeting` — parse, scrub, store
- `create_task` — validate, create, optional write-back

```python
@mcp.tool()
def session_start(ctx: Context = CurrentContext()) -> SessionStartResponse:
    ctx.info("Starting new session")
    ctx.report_progress(0, 3)
    # ... create session ...
    ctx.report_progress(1, 3)
    # ... sync integrations ...
    ctx.info("Sync complete", extra={"jira": count, "notion": count})
    ctx.report_progress(2, 3)
    # ... build response ...
    ctx.report_progress(3, 3)
    return SessionStartResponse(...)
```

### Tools that don't need Context

`task_start`, `task_end`, `add_note`, `fetch_open_tasks` — single-step
reads/writes where Context would be noise.

### Changes

- 4 tool functions gain `ctx: Context = CurrentContext()` parameter
- Structured log calls replace any existing logging
- Progress reporting on sync and ingest operations
- `Context` is a hidden dependency — not in the LLM's tool schema

### Unchanged

- Lazy singletons (lifespan refactor is a future iteration)
- No `ctx.get_state()`/`ctx.set_state()` — WizardSession handles session state
- No `ctx.sample()` — Wizard doesn't call back to the LLM

---

## New Files

| File | Purpose |
|------|---------|
| `src/mappers.py` | Bidirectional status/priority/category mappers |
| `src/resources.py` | FastMCP resource handlers |
| `src/prompts.py` | FastMCP prompt definitions |
| `tests/test_mappers.py` | Mapper bidirectional correctness tests |

## Modified Files

| File | Changes |
|------|---------|
| `src/schemas.py` | Add integration response models + resource response models |
| `src/integrations.py` | Return Pydantic models from `fetch_*()` methods |
| `src/services.py` | Remove mapping dicts, use mappers, access typed attributes |
| `src/tools.py` | Return Pydantic models, inject Context into 4 tools |
| `src/mcp_instance.py` | Import and register resources + prompts |
| `tests/test_services.py` | Update for typed integration responses and mapper usage |
| `tests/test_tools.py` | Update for Pydantic return types |
| `tests/test_integrations.py` | Verify Pydantic model returns |

## Out of Scope

- Lifespan / dependency injection (future iteration)
- `ctx.get_state()` / `ctx.set_state()` (WizardSession handles this)
- `ctx.sample()` (Wizard doesn't call back to the LLM)
- Pydantic models for Notion property extraction internals
- Additional prompts beyond the initial 5 (future iteration)
- Tags (low-stakes organisational concern, defer)
