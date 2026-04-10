from contextlib import contextmanager


def mock_session(db_session):
    """Context manager that yields the test db_session instead of creating a new one."""

    @contextmanager
    def _inner():
        yield db_session
        db_session.flush()

    return _inner
