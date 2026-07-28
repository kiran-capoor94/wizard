"""Scenario: save_note dual-writes a note episode to Graphiti on the same
spawn_background fire-and-forget seam used for write_embedding.

save_note is called directly (not via mcp_client) so a MagicMock
GraphMemoryService can be injected and asserted on -- the MCP pipeline has no
way to substitute Depends() providers per-call.
"""
import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from wizard.models import NoteType, Task
from wizard.repositories import NoteRepository, TaskRepository, TaskStateRepository
from wizard.security import SecurityService
from wizard.tools.task_tools import save_note


@contextmanager
def _yield_session(db):
    yield db


@pytest.mark.asyncio
async def test_save_note_dual_writes_episode_to_graphiti(db_session):
    """A non-duplicate save_note spawns gms.push_episode with the note body."""
    t_repo = TaskRepository()
    n_repo = NoteRepository()
    t_state_repo = TaskStateRepository()
    sec = SecurityService(allowlist=[], enabled=True)

    task = Task(name="Graphiti dual-write task")
    t_repo.save(db_session, task)
    t_state_repo.create_for_task(db_session, task)
    assert task.id is not None

    gms = MagicMock()
    gms.push_episode = MagicMock()

    ctx = MagicMock()
    ctx.get_state = AsyncMock(return_value=None)
    ctx.report_progress = AsyncMock()
    ctx.info = AsyncMock()
    ctx.debug = AsyncMock()

    with patch("wizard.tools.task_tools.get_session", lambda: _yield_session(db_session)):
        result = await save_note(
            ctx=ctx,
            task_id=task.id,
            note_type=NoteType.DECISION,
            content="Use WAL mode for the sqlite connection pool.",
            mental_model="WAL avoids writer starvation under concurrent readers.",
            t_repo=t_repo,
            sec=sec,
            n_repo=n_repo,
            t_state_repo=t_state_repo,
            gms=gms,
        )

    assert not result.was_duplicate

    # spawn_background schedules the coroutine on the running loop -- it does
    # not execute synchronously. Let the loop drain before asserting.
    for _ in range(5):
        await asyncio.sleep(0.01)

    assert gms.push_episode.called
    call = gms.push_episode.call_args
    assert call.kwargs["entity_type"] == "note"
    assert call.kwargs["entity_id"] == result.note_id
    assert '"note_type": "DECISION"' in call.kwargs["body"]
