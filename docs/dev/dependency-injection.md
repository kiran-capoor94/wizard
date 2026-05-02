# Dependency Injection — Wizard Developer Reference
> Full reference: part of the Wizard developer docs. See CLAUDE.md for the navigational index.

## Dependency Injection

`deps.py` provides plain provider functions wired into tools and resources
via FastMCP's `Depends()` system (identical in spirit to FastAPI's):

```python
get_db_session()           → Generator[Session, None, None]   # centralised; tests patch wizard.deps.get_db_session
get_security()             → SecurityService
get_task_repo()            → TaskRepository
get_meeting_repo()         → MeetingRepository
get_note_repo()            → NoteRepository
get_task_state_repo()      → TaskStateRepository
get_session_repo()         → SessionRepository
get_search_repo()          → SearchRepository
get_session_closer()       → SessionCloser
get_wizard_paths()         → WizardPaths
get_skill_roots()          → list[Path]   # skill search roots for mode tools
```

Tools and resources declare deps as typed default params:

```python
from fastmcp.dependencies import Depends
from .deps import get_task_repo
from .repositories import TaskRepository

async def my_tool(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
) -> ...:
    ...
```

FastMCP resolves and caches providers per-request; injected params are
hidden from the LLM-visible tool schema. Provider functions are plain
callables — no `Depends()` in their own signatures — so CLI code can call
them directly without FastMCP.

In tests: call tool/resource functions with deps as explicit kwargs
(FastMCP is not involved when calling directly):

```python
result = await my_tool(task_id=1, t_repo=TaskRepository())
```
