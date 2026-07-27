"""Verify the `search` tool routes through GraphMemoryService while staying
behavior-identical to the legacy hybrid_search path when Graphiti is disabled
(the default)."""

import pytest
from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from wizard.deps import get_graph_memory_service, get_search_repo
from wizard.models import Note, NoteType
from wizard.schemas import SearchResponse
from wizard.tools.query_tools import search


@pytest.fixture
def fts_engine():
    """In-memory SQLite engine with FTS5 tables created from scratch."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS note_fts USING fts5("
            "content, note_type UNINDEXED,"
            "content='note', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS session_fts USING fts5("
            "summary,"
            "content='wizardsession', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS meeting_fts USING fts5("
            "content, title,"
            "content='meeting', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE VIRTUAL TABLE IF NOT EXISTS task_fts USING fts5("
            "name,"
            "content='task', content_rowid='id')"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS note_fts_ai AFTER INSERT ON note BEGIN "
            "INSERT INTO note_fts(rowid, content, note_type) "
            "VALUES (new.id, new.content, new.note_type); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS meeting_fts_ai AFTER INSERT ON meeting BEGIN "
            "INSERT INTO meeting_fts(rowid, content, title) "
            "VALUES (new.id, new.content, new.title); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS task_fts_ai AFTER INSERT ON task BEGIN "
            "INSERT INTO task_fts(rowid, name) "
            "VALUES (new.id, new.name); END"
        ))
        conn.execute(text(
            "CREATE TRIGGER IF NOT EXISTS session_fts_ai AFTER INSERT ON wizardsession BEGIN "
            "INSERT INTO session_fts(rowid, summary) "
            "VALUES (new.id, new.summary); END"
        ))
        conn.commit()
    return engine


@pytest.fixture
def fts_db(fts_engine):
    with Session(fts_engine) as session:
        yield session


@pytest.mark.asyncio
async def test_search_still_returns_searchresponse_when_graphiti_disabled(fts_db):
    # graphiti disabled by default -> gms.search must delegate to
    # s_repo.hybrid_search, i.e. behave exactly like the legacy path.
    note = Note(
        note_type=NoteType.INVESTIGATION,
        content="distinctivegraphititoken appears in this note body",
    )
    fts_db.add(note)
    fts_db.flush()

    resp = await search(
        query="distinctivegraphititoken",
        limit=5,
        entity_type=None,
        gms=get_graph_memory_service(),
        s_repo=get_search_repo(),
        db=fts_db,
    )

    assert isinstance(resp, SearchResponse)
    assert any(r.entity_type == "note" and r.entity_id == note.id for r in resp.results)
