"""Analytics repository — read-only queries for session/note/task statistics."""

import datetime
import logging

from sqlmodel import Session, select

from ..models import Note, NoteType, TaskState, ToolCall, WizardSession

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    def get_session_stats(
        self, db: Session, start: datetime.date, end: datetime.date
    ) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        sessions = db.exec(
            select(WizardSession).where(
                WizardSession.created_at >= start_dt,
                WizardSession.created_at <= end_dt,
            )
        ).all()

        session_count = len(sessions)
        abandoned_count = sum(1 for s in sessions if s.closed_by == "auto")
        abandoned_rate = round(abandoned_count / session_count, 2) if session_count else 0.0

        durations: list[float] = []
        for s in sessions:
            if s.closed_by in ("user", "hook"):
                delta = (s.updated_at - s.created_at).total_seconds() / 60
                durations.append(delta)
            elif s.closed_by == "auto" and s.last_active_at is not None:
                delta = (s.last_active_at - s.created_at).total_seconds() / 60
                durations.append(delta)
            # open sessions (closed_by is None) excluded from average

        avg_duration = round(sum(durations) / len(durations), 1) if durations else 0.0

        tool_calls = db.exec(
            select(ToolCall).where(
                ToolCall.called_at >= start_dt,
                ToolCall.called_at <= end_dt,
            )
        ).all()
        total_tool_calls = len(tool_calls)

        synthesis_failures = sum(
            1 for s in sessions if s.synthesis_status == "partial_failure"
        )
        pending_synthesis = sum(
            1 for s in sessions if s.synthesis_status == "pending" and s.closed_by is not None
        )

        return {
            "session_count": session_count,
            "avg_duration_minutes": avg_duration,
            "total_tool_calls": total_tool_calls,
            "abandoned_count": abandoned_count,
            "abandoned_rate": abandoned_rate,
            "synthesis_failures": synthesis_failures,
            "pending_synthesis": pending_synthesis,
        }

    def get_note_stats(
        self, db: Session, start: datetime.date, end: datetime.date
    ) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        notes = db.exec(
            select(Note).where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
            )
        ).all()

        total = len(notes)
        by_type: dict[str, int] = {}
        session_summaries = 0
        unclassified = 0
        superseded = 0
        mental_models = 0
        manual_notes = 0

        for note in notes:
            type_name = (
                note.note_type.value
                if hasattr(note.note_type, "value")
                else str(note.note_type)
            )
            by_type[type_name] = by_type.get(type_name, 0) + 1

            if note.note_type == NoteType.SESSION_SUMMARY:
                session_summaries += 1
            else:
                manual_notes += 1
                if note.mental_model:
                    mental_models += 1

            status = getattr(note, "status", "active")
            if status == "unclassified":
                unclassified += 1
            elif status == "superseded":
                superseded += 1

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

    def get_task_stats(
        self, db: Session, start: datetime.date, end: datetime.date
    ) -> dict:
        start_dt = datetime.datetime.combine(start, datetime.time.min)
        end_dt = datetime.datetime.combine(end, datetime.time.max)

        notes = db.exec(
            select(Note).where(
                Note.created_at >= start_dt,
                Note.created_at <= end_dt,
            )
        ).all()

        task_note_counts: dict[int, int] = {}
        for note in notes:
            if note.task_id is not None:
                task_note_counts[note.task_id] = task_note_counts.get(note.task_id, 0) + 1

        worked = len(task_note_counts)
        total_notes = sum(task_note_counts.values())
        avg_notes = round(total_notes / worked, 1) if worked > 0 else 0.0

        stale = db.exec(select(TaskState).where(TaskState.stale_days > 3)).all()

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

        compounding_count = 0
        for tc in task_start_calls:
            session = session_map.get(tc.session_id)
            if session is None:
                continue
            # Prior context exists if any note predates this session's start.
            prior = db.exec(
                select(Note).where(Note.created_at < session.created_at)
            ).first()
            if prior is not None:
                compounding_count += 1

        return round(compounding_count / len(task_start_calls), 2)
