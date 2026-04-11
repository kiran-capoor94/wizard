import wizard.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport]
import wizard.resources  # noqa: F401  # pyright: ignore[reportUnusedImport]
import wizard.tools  # noqa: F401  # pyright: ignore[reportUnusedImport]
from wizard.mcp_instance import mcp

if __name__ == "__main__":
    mcp.run()
