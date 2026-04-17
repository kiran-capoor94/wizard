from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import MockContext, _MockContextImpl, mock_ctx, mock_session


def _make_notion_mock(notion=None):
    """Build a notion_client mock. Default: ensure_daily_page raises (non-fatal path)."""
    import httpx
    if notion is not None:
        return notion
    mock = MagicMock()
    mock.ensure_daily_page.side_effect = httpx.HTTPError("notion not configured in tests")
    return mock


def _patch_tools(db_session):
    """Patch get_session in wizard.tools to use the test database."""
    return {"get_session": mock_session(db_session)}


# ---------------------------------------------------------------------------
# session_end
# ---------------------------------------------------------------------------


async def test_session_end_saves_summary_note(db_session):
    from wizard.models import Note, NoteType, WizardSession
    from wizard.repositories import NoteRepository
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import session_end

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession(daily_page_id="test-daily-page")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None
    session_id = session.id

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_end(
            ctx,
            session_id=session_id,
            summary="wrapped up today's work",
            intent="wrapped up",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.note_id is not None
    assert result.notion_write_back.ok is True

    saved = db_session.get(Note, result.note_id)
    assert saved.note_type == NoteType.SESSION_SUMMARY
    assert saved.session_id == session_id

    wb_mock.push_session_summary.assert_called_once()
    called_session = wb_mock.push_session_summary.call_args[0][0]
    assert called_session.daily_page_id == "test-daily-page"


async def test_session_end_session_state_saved_true_on_happy_path(db_session):
    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import session_end

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="wrapped up",
            intent="finish auth refactor",
            working_set=[1, 2],
            state_delta="Completed token refresh logic",
            open_loops=["rate limiting"],
            next_actions=["write tests"],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.session_state_saved is True


async def test_session_end_session_state_saved_false_when_write_fails(db_session):
    from unittest.mock import patch as _patch

    from wizard.models import WizardSession
    from wizard.repositories import NoteRepository
    from wizard.schemas import WriteBackStatus
    from wizard.security import SecurityService
    from wizard.tools import session_end

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        with _patch(
            "wizard.schemas.SessionState.model_dump_json",
            side_effect=ValueError("serialization failed"),
        ):
            result = await session_end(
                ctx,
                session_id=session.id,
                summary="wrapped up",
                intent="test",
                working_set=[],
                state_delta="none",
                open_loops=[],
                next_actions=[],
                closure_status="clean",
                sec=SecurityService(),
                n_repo=NoteRepository(),
                wb=wb_mock,
            )

    assert result.session_state_saved is False


async def test_session_end_clears_current_session_id_from_ctx_state(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    await ctx.set_state("current_session_id", session.id)

    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    wb_mock = MagicMock()
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="done",
            working_set=[],
            state_delta="no changes",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert await ctx.get_state("current_session_id") is None


# --- session_end expansion ---


async def test_session_end_persists_session_state(db_session):

    from wizard.models import WizardSession
    from wizard.schemas import SessionState, WriteBackStatus
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    wb_mock = MagicMock()
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="good session",
            intent="shipped the auth fix",
            working_set=[1, 2],
            state_delta="ENG-42 now done",
            open_loops=["follow up with team"],
            next_actions=["write tests for ENG-50"],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    db_session.refresh(session)
    assert session.session_state is not None
    state = SessionState.model_validate_json(session.session_state)
    assert state.intent == "shipped the auth fix"
    assert state.working_set == [1, 2]
    assert state.closure_status == "clean"
    assert state.open_loops == ["follow up with team"]
    assert state.next_actions == ["write tests for ENG-50"]

    assert result.closure_status == "clean"
    assert result.open_loops_count == 1
    assert result.next_actions_count == 1
    assert result.intent == "shipped the auth fix"


async def test_session_end_emits_confirmation_via_ctx_info(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import WriteBackStatus
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    impl = _MockContextImpl()
    ctx = mock_ctx(impl)
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    wb_mock = MagicMock()
    wb_mock.push_session_summary = MagicMock(return_value=WriteBackStatus(ok=True))

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="intent",
            working_set=[],
            state_delta="nothing",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert any("clean" in msg for msg in impl.info_calls)


async def test_session_end_rejects_invalid_closure_status(db_session):
    from fastmcp.exceptions import ToolError

    from wizard.models import WizardSession
    from wizard.tools import session_end

    session = WizardSession()
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    assert session.id is not None

    ctx = MockContext()
    from wizard.repositories import NoteRepository
    from wizard.security import SecurityService
    wb_mock = MagicMock()
    wb_mock.push_session_summary = MagicMock()

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        with pytest.raises(ToolError):
            await session_end(
                ctx,
                session_id=session.id,
                summary="done",
                intent="intent",
                working_set=[],
                state_delta="nothing",
                open_loops=[],
                next_actions=[],
                closure_status="invalid_value",  # type: ignore[arg-type]
                sec=SecurityService(),
                n_repo=NoteRepository(),
                wb=wb_mock,
            )


async def test_session_end_persists_tool_registry(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import SessionState, WriteBackStatus
    from wizard.tools import session_end

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.flush()
    assert session.id is not None

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository
        from wizard.security import SecurityService
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="test registry persistence",
            working_set=[],
            state_delta="none",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            tool_registry="context7: library docs\nserena: code symbols",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.session_state_saved is True
    db_session.refresh(session)
    state = SessionState.model_validate_json(session.session_state)
    assert state.tool_registry == "context7: library docs\nserena: code symbols"


async def test_session_end_tool_registry_defaults_to_none(db_session):
    from wizard.models import WizardSession
    from wizard.schemas import SessionState, WriteBackStatus
    from wizard.tools import session_end

    wb_mock = MagicMock()
    wb_mock.push_session_summary.return_value = WriteBackStatus(ok=True)

    session = WizardSession()
    db_session.add(session)
    db_session.flush()

    ctx = MockContext()
    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        from wizard.repositories import NoteRepository
        from wizard.security import SecurityService
        result = await session_end(
            ctx,
            session_id=session.id,
            summary="done",
            intent="test",
            working_set=[],
            state_delta="none",
            open_loops=[],
            next_actions=[],
            closure_status="clean",
            sec=SecurityService(),
            n_repo=NoteRepository(),
            wb=wb_mock,
        )

    assert result.session_state_saved is True
    db_session.refresh(session)
    state = SessionState.model_validate_json(session.session_state)
    assert state.tool_registry is None


# ---------------------------------------------------------------------------
# resume_session
# ---------------------------------------------------------------------------


async def test_resume_session_creates_new_session(db_session):
    from wizard.models import Note, NoteType, WizardSession
    from wizard.tools import resume_session

    prior = WizardSession()
    db_session.add(prior)
    db_session.flush()
    db_session.refresh(prior)
    note = Note(note_type=NoteType.DOCS, content="prior note", session_id=prior.id)
    db_session.add(note)
    db_session.flush()

    ctx = MockContext()
    sync_mock = MagicMock()
    sync_mock.sync_all = MagicMock(return_value=[])

    with patch.multiple("wizard.tools.session_tools", **_patch_tools(db_session)):
        from wizard.repositories import MeetingRepository, NoteRepository, TaskRepository
        result = await resume_session(
            ctx,
            sync_svc=sync_mock,
            notion=_make_notion_mock(),
            t_repo=TaskRepository(),
            n_repo=NoteRepository(),
            m_repo=MeetingRepository(),
        )

    # New session must be distinct from prior
    assert result.session_id != prior.id
    assert result.resumed_from_session_id == prior.id
