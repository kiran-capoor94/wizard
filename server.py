from src.mcp_instance import mcp
import src.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.tool decorators
import src.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators
import src.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.prompt decorators

if __name__ == "__main__":
    mcp.run()
