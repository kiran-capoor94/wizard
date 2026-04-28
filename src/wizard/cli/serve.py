def serve() -> None:
    """MCP server entry point for the wizard-server console script.

    Registered in pyproject.toml [project.scripts] as wizard-server.
    Used by agent configs installed via `wizard setup`.
    """
    import atexit
    import sys

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.litellm import LiteLLMIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.mcp import MCPIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    import wizard.prompts  # noqa: F401 — registers @mcp.prompt decorators
    import wizard.resources  # noqa: F401 — registers @mcp.resource decorators
    import wizard.tools  # noqa: F401 — registers MCP tools via submodule imports
    from wizard.config import settings
    from wizard.mcp_instance import mcp

    if settings.sentry.dsn and settings.sentry.enabled:
        sentry_sdk.init(
            dsn=settings.sentry.dsn,
            traces_sample_rate=settings.sentry.traces_sample_rate,
            profiles_sample_rate=settings.sentry.profiles_sample_rate,
            release=f"wizard@{settings.version}",
            enable_logs=True,
            integrations=[
                AsyncioIntegration(),
                LiteLLMIntegration(),
                MCPIntegration(),
                SqlalchemyIntegration(),
                LoggingIntegration(level=None, event_level=None),
            ],
        )
        atexit.register(sentry_sdk.flush, timeout=5)

    try:
        mcp.run()
    except BaseExceptionGroup as eg:
        # Rich's on_broken_pipe() raises SystemExit(1) when stderr is closed,
        # which anyio wraps into a BaseExceptionGroup. Exit cleanly in that case.
        exits = [e for e in eg.exceptions if isinstance(e, SystemExit)]
        others = [e for e in eg.exceptions if not isinstance(e, SystemExit)]
        if others:
            sentry_sdk.capture_exception(eg)
            sentry_sdk.flush(timeout=5)
            raise
        code = max((e.code for e in exits if isinstance(e.code, int)), default=1)
        sys.exit(code)
    except BaseException as e:
        sentry_sdk.capture_exception(e)
        sentry_sdk.flush(timeout=5)
        raise
