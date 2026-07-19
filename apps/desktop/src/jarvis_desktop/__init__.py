"""JARVIS desktop app (PyQt6 HUD).

Entry point: `uv run jarvis_desktop` or `python -m jarvis_desktop`.

This package wraps the legacy MARK XXXIX-OR main.py and ui.py. The legacy
JARVIS modules (`ui`, `memory`, `actions`, `agent`) still live at the workspace
root during the migration; they are imported as siblings. We add the workspace
root to ``sys.path`` here so those imports work without modifying the legacy
code yet.

**Phase 0.4 transitional shim** — to be removed in Phase 1 when the legacy
modules are split into proper packages.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Legacy workspace-root import shim ───────────────────────────────
# `apps/desktop/src/jarvis_desktop/app.py` uses imports like
# `from memory.memory_manager import ...` that resolve to
# `<workspace-root>/memory/memory_manager.py`. When run as
# `python -m jarvis_desktop`, the workspace root is NOT on sys.path.
# We add it here so the legacy imports keep working during the
# migration. Removed in Phase 1 when the legacy modules are split.
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
if str(_WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE_ROOT))

__version__ = "0.1.0-rc1"
