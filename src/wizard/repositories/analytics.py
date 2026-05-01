"""Analytics repository — read-only queries for session/note/task statistics."""

import datetime
import logging

from sqlalchemy import case
from sqlmodel import Session, col, func, select

from ..models import Note, NoteType, Task, TaskState, ToolCall, WizardSession

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    def get_session_stats(
        self, db: Session, start: datetime.date, end: datetime.date
    ) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)
        window = (WizardSession.created_at >= start_dt, WizardSession.created_at <= end_dt)

        # Aggregate counts in the DB — no full-table scan in Python.
        closed_by_rows = db.exec(
            select(WizardSession.closed_by, func.count().label("cnt"))
            .where(*window)
            .group_by(WizardSession.closed_by)
        ).all()
        counts_by_closed: dict[str | None, int] = {cb: cnt for cb, cnt in closed_by_rows}
        session_count = sum(counts_by_closed.values())
        abandoned_count = counts_by_closed.get("auto", 0)
        abandoned_rate = round(abandoned_count / session_count, 2) if session_count else 0.0

        # Duration: user/hook sessions use updated_at; auto sessions use last_active_at.
        # Open sessions (closed_by IS NULL) are excluded. JULIANDAY diff × 1440 = minutes.
        closed_at_expr = case(
            (col(WizardSession.closed_by).in_(["user", "hook"]), WizardSession.updated_at),
            (
                WizardSession.closed_by == "auto",
                WizardSession.last_active_at,
            ),
        )
        avg_duration_row = db.exec(
            select(
                func.avg(
                    (func.julianday(closed_at_expr) - func.julianday(WizardSession.created_at))
                    * 1440
                )
            ).where(
                *window,
                col(WizardSession.closed_by).in_(["user", "hook", "auto"]),
                closed_at_expr.is_not(None),
            )
        ).one()
        avg_duration = round(avg_duration_row or 0.0, 1)

        total_tool_calls = db.exec(
            select(func.count()).select_from(ToolCall).where(
                ToolCall.called_at >= start_dt,
                ToolCall.called_at <= end_dt,
            )
        ).one()

        synthesis_status_rows = db.exec(
            select(WizardSession.id, WizardSession.synthesis_status, WizardSession.closed_by)
            .where(*window)
            .where(
                col(WizardSession.synthesis_status).in_(["partial_failure", "pending"])
            )
        ).all()
        synthesis_failure_ids = [
            sid for sid, status, _ in synthesis_status_rows
            if status == "partial_failure" and sid is not None
        ]
        pending_synthesis = sum(
            1 for _, status, closed_by in synthesis_status_rows
            if status == "pending" and closed_by is not None
        )

        return {
            "session_count": session_count,
            "avg_duration_minutes": avg_duration,
            "total_tool_calls": total_tool_calls,
            "abandoned_count": abandoned_count,
            "abandoned_rate": abandoned_rate,
            "synthesis_failures": len(synthesis_failure_ids),
            "synthesis_failure_ids": synthesis_failure_ids,
            "pending_synthesis": pending_synthesis,
        }

    def get_note_stats(self, db: Session, start: datetime.date, end: datetime.date) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        type_counts = db.exec(
            select(Note.note_type, func.count().label("cnt"))
            .where(Note.created_at >= start_dt, Note.created_at <= end_dt)
            .group_by(Note.note_type)
        ).all()

        total = 0
        by_type: dict[str, int] = {}
        session_summaries = 0
        manual_notes = 0
        for note_type, cnt in type_counts:
            type_name = note_type.value if hasattr(note_type, "value") else str(note_type)
            by_type[type_name] = cnt
            total += cnt
            if note_type == NoteType.SESSION_SUMMARY:
                session_summaries += cnt
            else:
                manual_notes += cnt

        mental_models = db.exec(
            select(func.count()).select_from(Note).where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
                Note.note_type != NoteType.SESSION_SUMMARY,
                Note.mental_model.is_not(None),  # type: ignore[union-attr]
            )
        ).one()

        unclassified = db.exec(
            select(func.count()).select_from(Note).where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
                Note.status == "unclassified",
            )
        ).one()

        superseded = db.exec(
            select(func.count()).select_from(Note).where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
                Note.status == "superseded",
            )
        ).one()

        coverage = round(mental_models / manual_notes, 2) if manual_notes > 0 else 0.0
        return {
            "total": total,
            "manual_notes": manual_notes,
            "session_summaries": session_summaries,
            "by_type": by_type,
            "mental_models_captured": mental_models,
            "mental_model_coverage": coverage,
            "unclassified": unclassified,
            "superseded": superseded,
        }

    def get_task_stats(self, db: Session, start: datetime.date, end: datetime.date) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        task_note_rows = db.exec(
            select(Note.task_id, func.count().label("cnt"))
            .where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
                Note.task_id.is_not(None),  # type: ignore[union-attr]
            )
            .group_by(Note.task_id)
        ).all()

        worked = len(task_note_rows)
        total_notes = sum(cnt for _, cnt in task_note_rows)
        avg_notes = round(total_notes / worked, 1) if worked > 0 else 0.0

        stale = db.exec(
            select(TaskState)
            .join(Task, TaskState.task_id == Task.id)
            .where(TaskState.stale_days > 3, col(Task.status).in_(["todo", "in_progress"]))
        ).all()

        return {
            "worked": worked,
            "avg_notes_per_task": avg_notes,
            "stale_count": len(stale),
        }

    def get_compounding_score(
        self, db: Session, start: datetime.date, end: datetime.date
    ) -> float:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        sessions_in_window = db.exec(
            select(WizardSession).where(
                WizardSession.created_at >= start_dt,
                WizardSession.created_at <= end_dt,
            )
        ).all()

        task_start_calls = db.exec(
            select(ToolCall).where(
                ToolCall.tool_name == "task_start",
                ToolCall.called_at >= start_dt,
                ToolCall.called_at <= end_dt,
            )
        ).all()

        if not task_start_calls:
            return 0.0

        # Index sessions by id for O(1) lookup.
        session_map = {s.id: s for s in sessions_in_window}

        # Single query: earliest note ever written. If any note predates a session's
        # start, prior context existed for that task_start — same answer for every
        # session after the first note, so there is no need to query per iteration.
        earliest_note_at = db.exec(
            select(Note.created_at).order_by(col(Note.created_at).asc()).limit(1)
        ).first()

        compounding_count = 0
        for tc in task_start_calls:
            session = session_map.get(tc.session_id)
            if session is None:
                continue
            if earliest_note_at is not None and earliest_note_at < session.created_at:
                compounding_count += 1

        return round(compounding_count / len(task_start_calls), 2)

    def get_tool_call_frequency(self, db: Session, days: int) -> dict[str, int]:
        """Return {tool_name: call_count} for the last `days` days."""
        cutoff = datetime.datetime.combine(
            datetime.date.today() - datetime.timedelta(days=days), datetime.time.min
        )
        rows = db.exec(
            select(ToolCall.tool_name, func.count().label("cnt"))
            .where(ToolCall.called_at >= cutoff)
            .group_by(ToolCall.tool_name)
            .order_by(func.count().desc())
        ).all()
        return {tool_name: cnt for tool_name, cnt in rows}
