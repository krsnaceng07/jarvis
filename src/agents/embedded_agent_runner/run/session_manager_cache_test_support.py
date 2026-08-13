"""Session-manager-cache test-support helpers.

Provides a small in-memory session-manager cache used by tests to
seed, lookup, and reset session-manager related cached entries.

API:
- `seed_session_manager_cache_for_test(key, value)` — insert an entry
- `get_session_manager_cache_snapshot()` — shallow copy of cache
- `reset_session_manager_cache_for_test()` — clear cache
"""
from __future__ import annotations

from typing import Any, Dict


_SESSION_MANAGER_CACHE: Dict[str, Any] = {}


def seed_session_manager_cache_for_test(key: str, value: Any) -> None:
    """Seed an entry into the in-memory session-manager cache."""
    _SESSION_MANAGER_CACHE[key] = value


def get_session_manager_cache_snapshot() -> Dict[str, Any]:
    """Return a shallow copy of the session-manager cache."""
    return dict(_SESSION_MANAGER_CACHE)


def reset_session_manager_cache_for_test() -> None:
    """Clear the session-manager cache."""
    _SESSION_MANAGER_CACHE.clear()


__all__ = [
    "seed_session_manager_cache_for_test",
    "get_session_manager_cache_snapshot",
    "reset_session_manager_cache_for_test",
]

