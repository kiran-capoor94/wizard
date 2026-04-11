from wizard.mcp_instance import mcp

import wizard.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.prompt decorators
import wizard.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators
import wizard.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.tool decorators

if __name__ == "__main__":
    mcp.run()
