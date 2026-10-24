"""jarvis.tools — OpenClaw ``src/tools/`` parity stub.

The Python port mirrors the OpenClaw ``src/tools/``
subdir; the module bodies land incrementally per the V2
plan as the corresponding subsystem is ported.
"""

from __future__ import annotations

from pathlib import Path

_root_tools = Path(__file__).resolve().parent.parent.parent / "tools"
if _root_tools.is_dir() and str(_root_tools) not in __path__:
    __path__.append(str(_root_tools))

