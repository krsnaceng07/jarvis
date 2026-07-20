"""plugin_globals — module-level state for the memory_lancedb plugin.

Mirrors OpenClaw's pattern of module-level state for the
plugin's CLI handlers and runtime. Phase 4.1 uses this as a
single-active-slot for ``MemoryDB`` + ``Embeddings`` so:

  - The CLI handlers (``/ltm list|search|...``) can call the
    real store without each handler carrying the db around.
  - Tests can swap the active db/embeddings via
    ``set_active_db`` / ``set_active_embeddings`` and never
    touch plugin code.

The slot is single-active-slot by design — only one
memory_lancedb instance per process, matching OpenClaw.
"""

# ruff: noqa: PLW0603  # module-level state is intentional (mirrors OpenClaw's runtime)
from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .embeddings import Embeddings
    from .runtime import MemoryDB

_lock = threading.Lock()
_active_db: MemoryDB | None = None
_active_embeddings: Embeddings | None = None


def set_active_db(db: MemoryDB | None) -> None:
    """Set the active ``MemoryDB`` used by CLI + globals."""
    global _active_db
    with _lock:
        _active_db = db


def get_active_db() -> MemoryDB | None:
    """Return the active ``MemoryDB`` (or ``None`` if not configured)."""
    with _lock:
        return _active_db


def set_active_embeddings(embeddings: Embeddings | None) -> None:
    """Set the active ``Embeddings`` used by CLI + globals."""
    global _active_embeddings
    with _lock:
        _active_embeddings = embeddings


def get_active_embeddings() -> Embeddings | None:
    """Return the active ``Embeddings`` (or ``None`` if not configured)."""
    with _lock:
        return _active_embeddings


def reset_for_tests() -> None:
    """Clear all module state. Tests call this between cases."""
    global _active_db, _active_embeddings
    with _lock:
        _active_db = None
        _active_embeddings = None


__all__ = [
    "get_active_db",
    "get_active_embeddings",
    "reset_for_tests",
    "set_active_db",
    "set_active_embeddings",
]
