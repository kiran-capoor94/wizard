import logging
import os
import stat
import sys
from pathlib import Path

import sentry_sdk
from pythonjsonlogger import json as jsonlogger
from sentry_sdk.integrations.asyncio import AsyncioIntegration
from sentry_sdk.integrations.litellm import LiteLLMIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.mcp import MCPIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

import wizard.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.prompt decorators
import wizard.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators
import wizard.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers MCP tools via submodule imports
from wizard.config import settings
from wizard.mcp_instance import mcp

# uv sets UF_HIDDEN on .pth files it creates inside .venv; Python 3.14+
# respects that flag and silently skips them, so the editable install
# breaks on every fresh venv.  Fix: ensure src/ is on sys.path before
# any wizard imports, and clear UF_HIDDEN so subsequent tools (pyright,
# etc.) also see the package.
_repo = Path(__file__).parent
_src = _repo / "src"
if _src.exists() and str(_src) not in sys.path:
    sys.path.insert(0, str(_src))
if hasattr(os, "chflags"):
    _ver = f"python{sys.version_info.major}.{sys.version_info.minor}"
    _site = _repo / ".venv" / "lib" / _ver / "site-packages"
    if _site.exists():
        for _pth in _site.glob("*.pth"):
            _st = os.lstat(_pth)
            if getattr(_st, "st_flags", 0) & stat.UF_HIDDEN:
                os.chflags(_pth, _st.st_flags & ~stat.UF_HIDDEN)


if __name__ == "__main__":
    import atexit

    # Configure structured JSON logging
    log_handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    log_handler.setFormatter(formatter)
    # Using force=True to override any default handlers already configured by dependencies
    logging.basicConfig(level=logging.INFO, handlers=[log_handler], force=True)

    # Initialize Sentry if DSN is provided
    if settings.sentry.dsn and settings.sentry.enabled:
        sentry_sdk.init(
            dsn=settings.sentry.dsn,
            traces_sample_rate=settings.sentry.traces_sample_rate,
            profiles_sample_rate=settings.sentry.profiles_sample_rate,
            # Add wizard-specific context
            release=f"wizard@{settings.version}",
            enable_logs=True,
            integrations=[
                AsyncioIntegration(),
                LiteLLMIntegration(),
                MCPIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(
                    level=None,  # Capture all logs as breadcrumbs
                    event_level=None,  # Don't send logs as events
                ),
            ],
        )
        atexit.register(sentry_sdk.flush, timeout=5)

    try:
        mcp.run()
    except BaseException as e:
        sentry_sdk.capture_exception(e)
        sentry_sdk.flush(timeout=5)
        raise
