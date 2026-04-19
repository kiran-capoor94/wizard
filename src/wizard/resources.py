from fastmcp.dependencies import Depends
from fastmcp.resources import ResourceContent, ResourceResult
from sqlmodel import col, select

from .config import settings
from .database import get_session
from .deps import get_note_repo, get_task_repo
from .mcp_instance import mcp
from .models import WizardSession
from .repositories import NoteRepository, TaskRepository
from .schemas import (
    BlockedTasksResource,
    ConfigResource,
    NoteDetail,
    OpenTasksResource,
    SessionResource,
    TaskContextResource,
)


def current_session(t_repo: TaskRepository = Depends(get_task_repo)):
    """Active session with open/blocked task counts."""
    with get_session() as db:
        stmt = (
            select(WizardSession)
            .where(WizardSession.summary == None)  # noqa: E711
            .order_by(col(WizardSession.created_at).desc())
            .limit(1)
        )
        session = db.exec(stmt).first()
        if session is None:
            return ResourceResult(
                contents=[
                    ResourceContent(
                        content=SessionResource(
                            session_id=None, open_task_count=0, blocked_task_count=0
                        ).model_dump_json(),
                        mime_type="application/json",
                    )
                ]
            )
        return ResourceResult(
            contents=[
                ResourceContent(
                    content=SessionResource(
                        session_id=session.id,
                        open_task_count=len(t_repo.get_open_task_contexts(db)),
                        blocked_task_count=len(
                            t_repo.get_blocked_task_contexts(db)
                        ),
                    ).model_dump_json(),
                    mime_type="application/json",
                )
            ]
        )


def open_tasks(t_repo: TaskRepository = Depends(get_task_repo)):
    """All open tasks with status and priority."""
    with get_session() as db:
        return ResourceResult(
            contents=[
                ResourceContent(
                    content=OpenTasksResource(
                        tasks=t_repo.get_open_task_contexts(db)
                    ).model_dump_json(),
                    mime_type="application/json",
                )
            ]
        )


def blocked_tasks(t_repo: TaskRepository = Depends(get_task_repo)):
    """All blocked tasks."""
    with get_session() as db:
        return ResourceResult(
            contents=[
                ResourceContent(
                    content=BlockedTasksResource(
                        tasks=t_repo.get_blocked_task_contexts(db)
                    ).model_dump_json(),
                    mime_type="application/json",
                )
            ]
        )


def task_context(
    task_id: int,
    t_repo: TaskRepository = Depends(get_task_repo),
    n_repo: NoteRepository = Depends(get_note_repo),
):
    """Full task detail — metadata, notes, history."""
    with get_session() as db:
        task = t_repo.get_by_id(db, task_id)
        task_ctx = t_repo.get_task_context(db, task)
        notes = n_repo.get_for_task(db, task_id=task.id)
        note_details = [NoteDetail.from_model(n) for n in notes if n.id is not None]
        return ResourceResult(
            contents=[
                ResourceContent(
                    content=TaskContextResource(
                        task=task_ctx, notes=note_details
                    ).model_dump_json(),
                    mime_type="application/json",
                )
            ]
        )


def wizard_config():
    """Current config — enabled integrations, active sources, database path."""
    return ResourceResult(
        contents=[
            ResourceContent(
                content=ConfigResource(
                    knowledge_store_type=settings.knowledge_store.type,
                    scrubbing_enabled=settings.scrubbing.enabled,
                    database_path=settings.db,
                ).model_dump_json(),
                mime_type="application/json",
            )
        ]
    )


mcp.resource("wizard://session/current")(current_session)
mcp.resource("wizard://tasks/open")(open_tasks)
mcp.resource("wizard://tasks/blocked")(blocked_tasks)
mcp.resource("wizard://tasks/{task_id}/context")(task_context)
mcp.resource("wizard://config")(wizard_config)
