"""jarvis.shared.scoped_expiring_id_cache — per-scope TTL cache.

OpenClaw parity: mirrors
``openclaw-main/src/shared/scoped-expiring-id-cache.ts``.

Public surface:

- :func:`create_scoped_expiring_id_cache`
- :class:`ScopedExpiringIdCache`
"""
from __future__ import annotations

from typing import Any, Dict, Generic, Optional, TypeVar, Union


_ScopeT = TypeVar("_ScopeT", bound=Union[str, int])
_IdT = TypeVar("_IdT", bound=Union[str, int])


class ScopedExpiringIdCache(Generic[_ScopeT, _IdT]):
    """Per-scope TTL cache for ids that should expire independently per scope."""

    def __init__(
        self,
        store: Dict[str, Dict[str, int]],
        ttl_ms: int = 0,
        cleanup_threshold: int = 1,
    ) -> None:
        self._store = store
        self._ttl_ms = max(0, int(ttl_ms or 0))
        self._cleanup_threshold = max(1, int(cleanup_threshold or 1))

    def _cleanup_expired(self, scope_key: str, entry: Dict[str, int], now: int) -> None:
        expired = [
            id_key
            for id_key, ts in list(entry.items())
            if now - ts > self._ttl_ms
        ]
        for id_key in expired:
            entry.pop(id_key, None)
        if not entry:
            self._store.pop(scope_key, None)

    def record(self, scope: _ScopeT, id: _IdT, now: Optional[int] = None) -> None:
        ts = int(now) if now is not None else _now_ms()
        scope_key = str(scope)
        id_key = str(id)
        entry = self._store.get(scope_key)
        if entry is None:
            entry = {}
            self._store[scope_key] = entry
        entry[id_key] = ts
        if len(entry) > self._cleanup_threshold:
            self._cleanup_expired(scope_key, entry, ts)

    def has(self, scope: _ScopeT, id: _IdT, now: Optional[int] = None) -> bool:
        ts = int(now) if now is not None else _now_ms()
        scope_key = str(scope)
        id_key = str(id)
        entry = self._store.get(scope_key)
        if entry is None:
            return False
        self._cleanup_expired(scope_key, entry, ts)
        return id_key in entry

    def clear(self) -> None:
        self._store.clear()


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


def create_scoped_expiring_id_cache(options: Dict[str, Any]) -> ScopedExpiringIdCache:
    """Create a scoped TTL cache for ids.

    Mirrors :func:`createScopedExpiringIdCache` (``shared/scoped-expiring-id-cache.ts``).
    """
    store = options.get("store")
    if not isinstance(store, dict):
        store = {}
    return ScopedExpiringIdCache(
        store=store,
        ttl_ms=options.get("ttlMs", 0),
        cleanup_threshold=options.get("cleanupThreshold", 1),
    )


__all__ = [
    "ScopedExpiringIdCache",
    "create_scoped_expiring_id_cache",
]
