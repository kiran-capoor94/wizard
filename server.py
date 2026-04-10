from src.mcp_instance import mcp
import src.tools  # noqa: F401 — registers all @mcp.tool decorators

if __name__ == "__main__":
    mcp.run()
