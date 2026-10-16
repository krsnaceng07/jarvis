"""JARVIS Thread Ownership infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import ThreadOwnershipPlugin, thread_ownership_plugin, entry

__all__ = [
    "ThreadOwnershipPlugin",
    "thread_ownership_plugin",
    "entry",
]
