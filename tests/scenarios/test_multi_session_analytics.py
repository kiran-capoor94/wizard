"""Scenario: run multiple sessions, verify state across them via query tools."""

import pytest

from wizard.models import NoteType
from wizard.tools.query_tools import get_session, get_sessions
from wizard.tools.session_tools import session_end, session_start
from wizard.tools.task_tools import save_note


@pytest.mark.asyncio
async def test_multi_session_analytics(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, security,
    seed_task, session_closer, session_repo,
):
    task1 = await seed_task(name="Task A")
    task2 = await seed_task(name="Task B", source_id="unique-b")

    session_ids = []
    note_counts = [3, 2, 1]  # notes per session

    for i, count in enumerate(note_counts):
        ctx = type(fake_ctx)()
        start = await session_start(
            ctx=ctx,
            t_repo=task_repo,
            m_repo=meeting_repo,
            ts_repo=task_state_repo,
            session_closer=session_closer,
        )
        session_ids.append(start.session_id)

        target_task = task1 if i % 2 == 0 else task2
        for j in range(count):
            await save_note(
                ctx=ctx, task_id=target_task.id,
                note_type=NoteType.INVESTIGATION,
                content=f"Session {i+1} note {j+1}",
                t_repo=task_repo, sec=security, n_repo=note_repo,
                t_state_repo=task_state_repo,
            )

        await session_end(
            ctx=ctx, session_id=start.session_id,
            summary=f"Session {i+1} done", intent="test",
            working_set=[target_task.id], state_delta="done",
            open_loops=[], next_actions=[],
            closure_status="clean",
            sec=security, n_repo=note_repo,
        )

    # Verify: 3 sessions visible via query tool
    sessions_resp = await get_sessions(s_repo=session_repo, n_repo=note_repo, db=db_session)
    assert sessions_resp.total_returned == 3

    # Verify: notes per session (task notes + session_summary note from session_end)
    for sid, expected_task_notes in zip(session_ids, note_counts, strict=True):
        s_detail = await get_session(session_id=sid, s_repo=session_repo, n_repo=note_repo, db=db_session)
        task_notes = [n for n in s_detail.notes if n.note_type != NoteType.SESSION_SUMMARY]
        summary_notes = [n for n in s_detail.notes if n.note_type == NoteType.SESSION_SUMMARY]
        assert len(task_notes) == expected_task_notes
        assert len(summary_notes) == 1
