"""Scenario: tiered task_start context delivery.

Verifies that:
1. task_start returns key notes (decisions first, then mental-model notes, then recent)
   rather than a blind recency slice.
2. Decisions are always included even when buried deep in history.
3. older_notes_available is set when notes were excluded from the selection.
4. rolling_summary is populated once mental_models are recorded.
5. Full counts in notes_by_type reflect all notes, not just the returned subset.
6. rewind_task still returns the full history.
"""

import pytest

from wizard.models import NoteType
from wizard.tools.task_tools import rewind_task, save_note, task_start


@pytest.mark.asyncio
async def test_decisions_always_included_over_recency(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo, task_state_repo, security,
):
    """Decisions saved early must appear in prior_notes even when newer junk notes exist."""
    task = await seed_task(name="Prioritised context task")

    # Save 1 decision early, then 5 low-value investigation notes
    await save_note(
        ctx=fake_ctx,
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="Chose approach X after reviewing options",
        t_repo=task_repo,
        sec=security,
        n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    for i in range(5):
        await save_note(
            ctx=fake_ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content=f"Junk investigation note {i}",
            t_repo=task_repo,
            sec=security,
            n_repo=note_repo,
            t_state_repo=task_state_repo,
        )

    resp = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)

    returned_types = {n.note_type for n in resp.prior_notes}
    assert NoteType.DECISION in returned_types, "Decision must be returned despite being oldest"
    assert resp.total_notes == 6
    assert resp.older_notes_available is True
    # Full counts still present
    assert resp.notes_by_type.get("investigation", 0) == 5
    assert resp.notes_by_type.get("decision", 0) == 1


@pytest.mark.asyncio
async def test_mental_model_notes_included_before_recency_fill(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo, task_state_repo, security,
):
    """Notes with mental_models rank above plain recent notes."""
    task = await seed_task(name="Mental model priority task")

    # Save 1 note with mental_model, then 5 plain investigation notes
    await save_note(
        ctx=fake_ctx,
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="Root cause is in the auth layer",
        mental_model="OAuth token expiry not refreshed — interceptor missing the 401 path.",
        t_repo=task_repo,
        sec=security,
        n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    for i in range(5):
        await save_note(
            ctx=fake_ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content=f"Plain note {i} with no mental model",
            t_repo=task_repo,
            sec=security,
            n_repo=note_repo,
            t_state_repo=task_state_repo,
        )

    resp = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)

    mm_notes = [n for n in resp.prior_notes if n.mental_model is not None]
    assert len(mm_notes) >= 1, "Note with mental_model must be included"
    assert any("interceptor" in (n.mental_model or "") for n in resp.prior_notes)


@pytest.mark.asyncio
async def test_no_cap_when_all_notes_are_key(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo, task_state_repo, security,
):
    """With 2 notes total, all are returned and older_notes_available is False."""
    task = await seed_task(name="Small task")

    for i in range(2):
        await save_note(
            ctx=fake_ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content=f"Finding {i}",
            t_repo=task_repo,
            sec=security,
            n_repo=note_repo,
            t_state_repo=task_state_repo,
        )

    resp = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)

    assert resp.total_notes == 2
    assert len(resp.prior_notes) == 2
    assert resp.older_notes_available is False


@pytest.mark.asyncio
async def test_rolling_summary_populated_from_mental_models(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo, task_state_repo, security,
):
    task = await seed_task(name="Mental model task")

    # First note without mental_model — no summary yet
    await save_note(
        ctx=fake_ctx,
        task_id=task.id,
        note_type=NoteType.INVESTIGATION,
        content="Root cause investigation",
        mental_model=None,
        t_repo=task_repo,
        sec=security,
        n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    resp = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)
    assert resp.rolling_summary is None

    # Second note with mental_model — summary should now be present
    await save_note(
        ctx=fake_ctx,
        task_id=task.id,
        note_type=NoteType.DECISION,
        content="Chose approach X",
        mental_model="The bug is in the auth middleware — approach X fixes it cleanly.",
        t_repo=task_repo,
        sec=security,
        n_repo=note_repo,
        t_state_repo=task_state_repo,
    )
    resp2 = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)
    assert resp2.rolling_summary is not None
    assert "approach X fixes it cleanly" in resp2.rolling_summary
    assert "decision" in resp2.rolling_summary


@pytest.mark.asyncio
async def test_rewind_task_returns_full_history(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo, task_state_repo, security,
):
    task = await seed_task(name="Rewind history task")

    for i in range(7):
        await save_note(
            ctx=fake_ctx,
            task_id=task.id,
            note_type=NoteType.INVESTIGATION,
            content=f"Note {i}",
            t_repo=task_repo,
            sec=security,
            n_repo=note_repo,
            t_state_repo=task_state_repo,
        )

    rewind_resp = await rewind_task(task_id=task.id, n_repo=note_repo)
    ts_resp = await task_start(ctx=fake_ctx, task_id=task.id, t_repo=task_repo, n_repo=note_repo)

    assert rewind_resp.summary.total_notes == 7
    assert len(rewind_resp.timeline) == 7
    # task_start should have capped the notes
    assert len(ts_resp.prior_notes) < 7
    assert ts_resp.older_notes_available is True


@pytest.mark.asyncio
async def test_task_start_skill_instructions_sent_once_per_session(
    db_session, fake_ctx, seed_task,
    task_repo, note_repo,
):
    """skill_instructions must be included on the first task_start call only.

    On subsequent calls within the same session, the agent already has the
    instructions in context — re-sending is pure token waste.
    """
    task_a = await seed_task(name="Task A")
    task_b = await seed_task(name="Task B")

    resp1 = await task_start(ctx=fake_ctx, task_id=task_a.id, t_repo=task_repo, n_repo=note_repo)
    resp2 = await task_start(ctx=fake_ctx, task_id=task_b.id, t_repo=task_repo, n_repo=note_repo)

    assert resp1.skill_instructions is not None, "First call must include skill_instructions"
    assert resp2.skill_instructions is None, "Second call must omit skill_instructions"
