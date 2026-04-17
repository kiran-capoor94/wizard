from contextlib import contextmanager
from typing import cast

from fastmcp import Context


def mock_session(db_session):
    """Context manager that yields the test db_session instead of creating a new one."""

    @contextmanager
    def _inner():
        yield db_session
        db_session.flush()

    return _inner


class _MockContextImpl:
    """Minimal FastMCP Context double for async tool tests.

    Records all ctx.* calls so tests can assert on them.
    Elicit response is configurable: None → DeclinedElicitation,
    a string → AcceptedElicitation(data=<string>).
    Set supports_elicit=False to simulate a client that raises on elicit.
    """

    def __init__(
        self,
        elicit_response: str | None = None,
        supports_elicit: bool = True,
    ):
        self.info_calls: list[str] = []
        self.warning_calls: list[str] = []
        self.error_calls: list[str] = []
        self.progress_calls: list[tuple[int, int, str | None]] = []
        self._state: dict[str, object] = {}
        self._elicit_response = elicit_response
        self._supports_elicit = supports_elicit

    async def info(self, msg: str) -> None:
        self.info_calls.append(msg)

    async def warning(self, msg: str) -> None:
        self.warning_calls.append(msg)

    async def error(self, msg: str) -> None:
        self.error_calls.append(msg)

    async def report_progress(
        self, current: int, total: int, message: str | None = None
    ) -> None:
        self.progress_calls.append((current, total, message))

    async def set_state(self, key: str, value: object) -> None:
        self._state[key] = value

    async def get_state(self, key: str, default: object = None) -> object:
        return self._state.get(key, default)

    async def delete_state(self, key: str) -> None:
        self._state.pop(key, None)

    async def elicit(self, _message: str, response_type=None, **kwargs):
        from fastmcp.server.elicitation import AcceptedElicitation
        from mcp.server.elicitation import DeclinedElicitation

        if not self._supports_elicit:
            raise NotImplementedError("Client does not support elicitation")
        if self._elicit_response is None:
            return DeclinedElicitation()
        return AcceptedElicitation(data=self._elicit_response)


def MockContext(
    elicit_response: str | None = None,
    supports_elicit: bool = True,
) -> Context:
    """Factory that returns a MockContext cast to Context for use in async tool tests.

    When you need to assert on recorded calls (progress_calls, info_calls, etc.),
    create the impl first and cast separately:

        impl = _MockContextImpl()
        ctx = mock_ctx(impl)
        ...
        assert impl.progress_calls == [(0, 3, "Syncing Jira...")]
    """
    impl = _MockContextImpl(
        elicit_response=elicit_response,
        supports_elicit=supports_elicit,
    )
    return cast(Context, impl)


def mock_ctx(impl: _MockContextImpl) -> Context:
    """Cast a _MockContextImpl to Context. Use when you need both the tool-compatible
    ctx and access to recorded calls (progress_calls, info_calls, etc.)."""
    return cast(Context, impl)
