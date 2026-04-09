from fastmcp import FastMCP

from src.config import Settings

settings = Settings()

mcp = FastMCP(
    name=settings.name,
    instructions="Wizard is a set of tools used by Kiran Capoor to enhance his workflows and build contexts before doing any engineering workflows. This is significantly helpful for Kiran since he has ADHD.",
    version=settings.version,
)


@mcp.tool
def greet(name: str) -> str:
    return f"Hello, {name}"


if __name__ == "__main__":
    mcp.run()
