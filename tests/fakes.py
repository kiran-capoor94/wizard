"""Fake implementations for behavioural testing.

Fakes implement the same public interface as real clients but store
data in memory. They are not mocks -- they have real behaviour (store,
retrieve, update), just without network I/O.
"""

from wizard.models import (  # noqa: F401 (used by tests that import from here)
    Meeting,
    Task,
    WizardSession,
)


class FakeContext:
    """Minimal stand-in for fastmcp.Context used by tool functions."""

    def __init__(self):
        self._state: dict = {}
        self.sample_result = None
        self.sample_error: Exception | None = None

    async def get_state(self, key: str):
        return self._state.get(key)

    async def set_state(self, key: str, value):
        self._state[key] = value

    async def delete_state(self, key: str):
        self._state.pop(key, None)

    async def report_progress(self, current, total, message=""):
        pass

    async def info(self, msg: str):
        pass

    async def error(self, msg: str):
        pass

    async def elicit(self, prompt: str, response_type=None):
        raise NotImplementedError("elicit not available in tests")

    async def sample(self, messages, **kwargs):
        """Configurable fake for ctx.sample().

        Set ``self.sample_result`` to control the return value.
        Set ``self.sample_error`` to make it raise.
        """
        if self.sample_error is not None:
            raise self.sample_error
        return self.sample_result


class FakeSessionCloser:
    """Fake SessionCloser that does nothing."""

    async def close_recent_abandoned(self, db, ctx, current_session_id: int) -> list:
        return []

    async def close_abandoned_background(self, current_session_id: int) -> None:
        pass

    async def close_one(self, db, session, ctx=None):
        from wizard.schemas import ClosedSessionSummary
        return ClosedSessionSummary(
            session_id=session.id, summary="fake", closed_via="synthetic",
            task_ids=[], note_count=0,
        )


