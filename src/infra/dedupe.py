"""src.infra.dedupe — process-local dedupe cache.

OpenClaw parity: mirrors ``src/infra/dedupe.ts``.

Provides bounded in-memory TTL/LRU-style dedupe caches for duplicate message
suppression and replay protection.
"""

from __future__ import annotations

import time


class DedupeCache:
    """Bounded in-memory dedupe cache with optional TTL expiry.

    Mirrors ``DedupeCache`` (``infra/dedupe.ts``).
    """

    def __init__(self, ttl_ms: int = 20 * 60 * 1000, max_size: int = 5000) -> None:
        self.ttl_ms = max(0, int(ttl_ms))
        self.max_size = max(0, int(max_size))
        self._cache: dict[str, float] = {}

    def _now_ms(self, now: float | None = None) -> float:
        return (now if now is not None else time.time()) * 1000.0

    def _prune(self, now_ms: float) -> None:
        if self.ttl_ms > 0:
            cutoff = now_ms - self.ttl_ms
            expired = [k for k, ts in self._cache.items() if ts < cutoff]
            for k in expired:
                del self._cache[k]

        if self.max_size <= 0:
            self._cache.clear()
            return

        while len(self._cache) > self.max_size:
            # Delete oldest entry (first key in insertion-ordered dict)
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    def check(self, key: str | None, now: float | None = None) -> bool:
        """Return True for a recent duplicate; record the key when not present.

        Mirrors ``cache.check``.
        """
        if not key or self.max_size <= 0:
            return False

        now_ms = self._now_ms(now)
        self._prune(now_ms)

        existing = self._cache.get(key)
        if existing is not None:
            if self.ttl_ms <= 0 or (now_ms - existing < self.ttl_ms):
                # Touch recency
                del self._cache[key]
                self._cache[key] = now_ms
                return True
            else:
                del self._cache[key]

        self._cache[key] = now_ms
        self._prune(now_ms)
        return False

    def peek(self, key: str | None, now: float | None = None) -> bool:
        """Return True for a recent duplicate without recording or refreshing.

        Mirrors ``cache.peek``.
        """
        if not key or self.max_size <= 0:
            return False

        now_ms = self._now_ms(now)
        existing = self._cache.get(key)
        if existing is None:
            return False

        if self.ttl_ms > 0 and (now_ms - existing >= self.ttl_ms):
            del self._cache[key]
            return False

        return True

    def delete(self, key: str | None) -> None:
        """Remove *key* from the cache if present."""
        if key and key in self._cache:
            del self._cache[key]

    def clear(self) -> None:
        """Clear all cached keys."""
        self._cache.clear()

    def size(self) -> int:
        """Return number of currently cached keys."""
        return len(self._cache)


def create_dedupe_cache(ttl_ms: int = 20 * 60 * 1000, max_size: int = 5000) -> DedupeCache:
    """Create a bounded in-memory dedupe cache.

    Mirrors ``createDedupeCache``.
    """
    return DedupeCache(ttl_ms=ttl_ms, max_size=max_size)


__all__ = [
    "DedupeCache",
    "create_dedupe_cache",
]
