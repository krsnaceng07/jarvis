"""JARVIS desktop app (PyQt6 HUD).

Entry point: `uv run jarvis_desktop` or `python -m jarvis_desktop`.

This package hosts the desktop app + the host-side glue around
plugin extensions. The legacy `memory/`, `agent/`, `or_client.py`
modules at the workspace root were removed in Phase 3.5; the
host now reads from `extensions/memory_core/` (the OpenClaw
memory capability) and uses the `save_memory` LLM tool inline
instead of a background extraction pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Force stdout/stderr to UTF-8 to support emojis on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# ── Workspace-root import shim ──────────────────────────────────────
# The desktop app needs the workspace root on sys.path so it can
# resolve `extensions.<id>`, `src.<module>`, and `packages.<sdk>`.
# This mirrors the desktop host's bootstrap path.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))
_SRC_DIR = _WORKSPACE_ROOT / "src"
if _SRC_DIR.exists() and str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

__version__ = "0.1.0-rc1"
