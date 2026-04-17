import os
import stat
import sys
from pathlib import Path

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

from wizard.mcp_instance import mcp

import wizard.prompts  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.prompt decorators
import wizard.resources  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers @mcp.resource decorators
import wizard.tools  # noqa: F401  # pyright: ignore[reportUnusedImport] — registers MCP tools via submodule imports

if __name__ == "__main__":
    mcp.run()
