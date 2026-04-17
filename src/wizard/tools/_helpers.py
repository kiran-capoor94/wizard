from ..database import get_session  # noqa: F401 — re-exported so tests patch one target

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
