"""Scenario: session_start returns prior_summaries from recently closed sessions."""

import pytest

from wizard.tools.session_tools import session_end, session_start


@pytest.mark.asyncio
async def test_prior_summaries_empty_on_first_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer,
):
    response = await session_start(
        ctx=fake_ctx,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    assert response.prior_summaries == []


@pytest.mark.asyncio
async def test_prior_summaries_contains_most_recent_closed_session(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer, security,
):
    ctx1 = type(fake_ctx)()
    start1 = await session_start(
        ctx=ctx1,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    await session_end(
        ctx=ctx1,
        session_id=start1.session_id,
        summary="Investigated the auth token expiry bug and found the root cause",
        intent="debug",
        working_set=[],
        state_delta="found root cause",
        open_loops=[],
        next_actions=[],
        closure_status="clean",
        sec=security,
        n_repo=note_repo,
    )

    ctx2 = type(fake_ctx)()
    start2 = await session_start(
        ctx=ctx2,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    assert len(start2.prior_summaries) == 1
    assert start2.prior_summaries[0].session_id == start1.session_id
    assert "auth token" in start2.prior_summaries[0].summary


@pytest.mark.asyncio
async def test_prior_summaries_capped_at_three(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer, security,
):
    for i in range(5):
        ctx = type(fake_ctx)()
        resp = await session_start(
            ctx=ctx,
            t_repo=task_repo,
            m_repo=meeting_repo,
            ts_repo=task_state_repo,
            session_closer=session_closer,
        )
        await session_end(
            ctx=ctx,
            session_id=resp.session_id,
            summary=f"Session {i + 1} completed work on the feature",
            intent="work",
            working_set=[],
            state_delta="",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=security,
            n_repo=note_repo,
        )

    ctx_final = type(fake_ctx)()
    response = await session_start(
        ctx=ctx_final,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    assert len(response.prior_summaries) == 3


@pytest.mark.asyncio
async def test_prior_summaries_task_ids_from_working_set(
    db_session, fake_ctx,
    task_repo, note_repo, meeting_repo, task_state_repo, session_closer, security,
    seed_task,
):
    task = await seed_task(name="Auth bug fix")

    ctx1 = type(fake_ctx)()
    start1 = await session_start(
        ctx=ctx1,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )
    await session_end(
        ctx=ctx1,
        session_id=start1.session_id,
        summary="Fixed the auth bug",
        intent="fix",
        working_set=[task.id],
        state_delta="done",
        open_loops=[],
        next_actions=[],
        closure_status="clean",
        sec=security,
        n_repo=note_repo,
    )

    ctx2 = type(fake_ctx)()
    start2 = await session_start(
        ctx=ctx2,
        t_repo=task_repo,
        m_repo=meeting_repo,
        ts_repo=task_state_repo,
        session_closer=session_closer,
    )

    assert start2.prior_summaries[0].task_ids == [task.id]
