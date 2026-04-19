"""Triage tools — on-demand work recommendation with scoring and LLM reasons."""

import logging
from typing import Literal

from ..schemas import TaskContext

logger = logging.getLogger(__name__)

_PRIORITY_SCORES = {"high": 1.0, "medium": 0.5, "low": 0.2}

_MODE_WEIGHTS: dict[str, dict[str, float]] = {
    "focus":      {"priority": 0.50, "recency": 0.30, "momentum": 0.20, "simplicity": 0.00},
    "quick-wins": {"priority": 0.20, "recency": 0.15, "momentum": 0.15, "simplicity": 0.50},
    "unblock":    {"priority": 0.40, "recency": 0.40, "momentum": 0.20, "simplicity": 0.00},
}

_MAX_SAMPLE_COUNT = 4  # sample reasons for top N tasks only


def _classify_momentum(task: TaskContext) -> Literal["new", "active", "cooling", "cold"]:
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

    priority_val = task.priority.value if hasattr(task.priority, "value") else task.priority
    priority_score = _PRIORITY_SCORES.get(priority_val, 0.2)
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
    status_val = task.status.value if hasattr(task.status, "value") else task.status
    if time_budget == "30m":
        if status_val == "in_progress":
            score += 0.1
        if task.note_count == 0:
            score -= 0.1

    return round(score, 4)


def _dominant_signal(
    task: TaskContext, mode: str, time_budget: str | None
) -> str:
    weights = _MODE_WEIGHTS.get(mode, _MODE_WEIGHTS["focus"])
    priority_val = task.priority.value if hasattr(task.priority, "value") else task.priority
    priority_score = _PRIORITY_SCORES.get(priority_val, 0.2)
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
