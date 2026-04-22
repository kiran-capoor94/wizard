def serve() -> None:
    """MCP server entry point for the wizard-server console script.

    Registered in pyproject.toml [project.scripts] as wizard-server.
    Used by agent configs installed via `wizard setup`.
    """
    import wizard.prompts  # noqa: F401 — registers @mcp.prompt decorators
    import wizard.resources  # noqa: F401 — registers @mcp.resource decorators
    import wizard.tools  # noqa: F401 — registers MCP tools via submodule imports

    import sentry_sdk
    from sentry_sdk.integrations.litellm import LiteLLMIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration
    from sentry_sdk.integrations.mcp import MCPIntegration

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
                LiteLLMIntegration(),
                MCPIntegration(),
                LoggingIntegration(level=None, event_level=None),
            ],
        )

    mcp.run()
