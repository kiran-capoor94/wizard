"""Triage tools — on-demand work recommendation with scoring and LLM reasons."""

import logging
from typing import Literal

from fastmcp import Context
from fastmcp.dependencies import Depends
from sqlmodel import Session

from ..database import get_session
from ..deps import get_task_repo
from ..mcp_instance import mcp
from ..repositories import TaskRepository
from ..schemas import TaskContext, TaskRecommendation, WorkRecommendationResponse
from ..skills import SKILL_TRIAGE, load_skill

logger = logging.getLogger(__name__)

_PRIORITY_SCORES = {"high": 1.0, "medium": 0.5, "low": 0.2}

_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "focus": {"priority": 0.50, "recency": 0.30, "momentum": 0.20, "simplicity": 0.00},
    "quick-wins": {
        "priority": 0.20,
        "recency": 0.15,
        "momentum": 0.15,
        "simplicity": 0.50,
    },
    "unblock": {
        "priority": 0.40,
        "recency": 0.40,
        "momentum": 0.20,
        "simplicity": 0.00,
    },
}

_MAX_SAMPLE_COUNT = 4  # sample reasons for top N tasks only


def _classify_momentum(
    task: TaskContext,
) -> Literal["new", "active", "cooling", "cold"]:
    if task.note_count == 0:
        return "new"
    if task.stale_days <= 2:
        return "active"
    if task.stale_days <= 7:
        return "cooling"
    return "cold"


def _score_task(
    task: TaskContext,
    mode: str = "focus",
    time_budget: str | None = None,
) -> float:
    weights = _MODE_WEIGHTS.get(mode, _MODE_WEIGHTS["focus"])

    priority_score = _PRIORITY_SCORES.get(task.priority.value, 0.2)
    recency_score = 1.0 / (1.0 + task.stale_days)
    momentum_score = min(task.note_count / 10.0, 1.0)  # saturates at 10 notes

    # simplicity: inverse of note_count (more notes = more complex)
    max_notes = 20
    simplicity_score = 1.0 - min(task.note_count / max_notes, 1.0)

    score = (
        weights["priority"] * priority_score
        + weights["recency"] * recency_score
        + weights["momentum"] * momentum_score
        + weights["simplicity"] * simplicity_score
    )

    # time_budget adjustments
    if time_budget == "30m":
        if task.status.value == "in_progress":
            score += 0.1
        if task.note_count == 0:
            score -= 0.1

    return round(score, 4)


def _dominant_signal(task: TaskContext, mode: str, time_budget: str | None) -> str:
    weights = _MODE_WEIGHTS.get(mode, _MODE_WEIGHTS["focus"])
    priority_score = _PRIORITY_SCORES.get(task.priority.value, 0.2)
    recency_score = 1.0 / (1.0 + task.stale_days)
    momentum_score = min(task.note_count / 10.0, 1.0)

    contributions = {
        "priority": weights["priority"] * priority_score,
        "recency": weights["recency"] * recency_score,
        "momentum": weights["momentum"] * momentum_score,
    }
    return max(contributions, key=lambda k: contributions[k])


def _fallback_reason(task: TaskContext, dominant_signal: str) -> str:
    stale = task.stale_days
    if dominant_signal == "priority":
        return f"High priority task — worth addressing soon (last touched {stale}d ago)"
    if dominant_signal == "recency":
        return f"Active {stale}d ago — good time to resume where you left off"
    return f"Building momentum ({task.note_count} notes) — context is warm"


async def _sample_reason(
    ctx: Context,
    task: TaskContext,
    mode: str,
    time_budget: str | None,
) -> str:
    dominant = _dominant_signal(task, mode, time_budget)
    momentum = _classify_momentum(task)
    prompt = (
        f"Task: {task.name!r}\n"
        f"Priority: {task.priority.value}\n"
        f"Status: {task.status.value}\n"
        f"Momentum: {momentum} ({task.stale_days}d since last note,"
        f" {task.note_count} notes total)\n"
        f"Dominant scoring signal: {dominant}\n"
        f"Last note preview: {task.last_note_preview or 'none'}\n\n"
        "Write one sentence (max 25 words) explaining why this task should be worked on now. "
        "Ground the reason in the note context if available. Be specific, not generic."
    )
    try:
        result = await ctx.sample(prompt, max_tokens=60)
        return result.result.strip()
    except Exception:
        logger.warning("Reason sampling failed for task %d, using fallback", task.id)
        return _fallback_reason(task, dominant)


@mcp.tool()
async def what_should_i_work_on(
    session_id: int,
    ctx: Context,
    mode: Literal["focus", "quick-wins", "unblock"] = "focus",
    time_budget: str | None = None,
    t_repo: TaskRepository = Depends(get_task_repo),
    db: Session = Depends(get_session),
) -> WorkRecommendationResponse:
    """Return a scored, justified recommendation for what to work on next.

    Args:
        session_id: Active session ID (from session_start).
        mode: Scoring mode — 'focus' (default), 'quick-wins', or 'unblock'.
        time_budget: Available time — '30m', '2h', 'half-day', 'full-day'.
    """
    # Always fetch all workable tasks including blocked so we can count skipped ones
    # without a second query. Filter post-fetch based on mode.
    all_workable = t_repo.get_workable_task_contexts(db, include_blocked=True)

    if mode == "unblock":
        tasks = [t for t in all_workable if t.status.value == "blocked"]
    else:
        tasks = [t for t in all_workable if t.status.value != "blocked"]

    if not tasks:
        return WorkRecommendationResponse(
            recommended_task=None,
            alternatives=[],
            skipped_blocked=0,
            message=(
                "No open tasks — use session_start to check task list"
                " or create_task to add one."
            ),
        )

    skipped_blocked = 0
    if mode != "unblock":
        skipped_blocked = sum(1 for t in all_workable if t.status.value == "blocked")

    # Score and rank
    scored = sorted(
        tasks,
        key=lambda t: (
            -_score_task(t, mode=mode, time_budget=time_budget),
            {"high": 0, "medium": 1, "low": 2}.get(t.priority.value, 2),
            t.stale_days,
        ),
    )

    shortlist = scored[:_MAX_SAMPLE_COUNT]

    # Build recommendations with LLM-sampled reasons
    recs: list[TaskRecommendation] = []
    for task in shortlist:
        reason = await _sample_reason(ctx, task, mode, time_budget)
        recs.append(
            TaskRecommendation(
                task_id=task.id,
                name=task.name,
                priority=task.priority.value,
                status=task.status.value,
                score=_score_task(task, mode=mode, time_budget=time_budget),
                reason=reason,
                momentum=_classify_momentum(task),
                last_note_preview=task.last_note_preview,
            )
        )

    skill_content = load_skill(SKILL_TRIAGE)
    if skill_content:
        await ctx.info(f"[wizard skill]\n{skill_content}")

    return WorkRecommendationResponse(
        recommended_task=recs[0],
        alternatives=recs[1:],
        skipped_blocked=skipped_blocked,
    )
