"""Pytest configuration for JARVIS.

Currently a no-op stub. Used to live here for transitional warning filters
during PR 0.4; the filter now lives in the root `pyproject.toml`
(`[tool.pytest.ini_options].filterwarnings`), which is the canonical location.

This file is kept so that future per-test setup (fixtures, markers, plugins)
has an obvious home. See `tests/README.md` for the test layout.
"""

from __future__ import annotations

from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parent.parent
_tools_dir = str(_repo_root / "tools")
if _tools_dir not in sys.path:
    sys.path.append(str(_repo_root))

try:
    import tools
    if hasattr(tools, "__path__") and _tools_dir not in tools.__path__:
        tools.__path__.append(_tools_dir)
except ImportError:
    pass

