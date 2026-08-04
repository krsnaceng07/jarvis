"""jarvis.config.cache_utils — TTL cache and file-stat helpers.

OpenClaw parity: mirrors ``openclaw-main/src/config/cache-utils.ts``.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Generic, List, Optional, TypeVar

TKey = TypeVar("TKey")
TValue = TypeVar("TValue")

#: Sentinel for parsed non-negative integers.
_STRICT_NON_NEGATIVE_INT_RE = None  # inlined below to avoid module-level re import


def _parse_strict_non_negative_int(value: str) -> Optional[int]:
    try:
        i = int(value)
    except ValueError:
        return None
    if i < 0:
        return None
    return i


def resolve_cache_ttl_ms(*, env_value: Optional[str], default_ttl_ms: int) -> int:
    """Resolve a cache TTL from an env override, falling back unless exact.

    Mirrors :func:`resolveCacheTtlMs` (``shared/config/cache-utils.ts``).
    """
    if env_value:
        parsed = _parse_strict_non_negative_int(env_value)
        if parsed is not None:
            return parsed
    return default_ttl_ms


def is_cache_enabled(ttl_ms: int) -> bool:
    return ttl_ms > 0


class ExpiringMapCache(Generic[TKey, TValue]):
    """Synchronous map cache with dynamic TTL and explicit pruning hooks.

    Mirrors :class:`ExpiringMapCache` (``shared/config/cache-utils.ts``).
    """

    def __init__(
        self,
        *,
        ttl_ms,
        prune_interval_ms=None,
        clock: Optional[Callable[[], int]] = None,
    ) -> None:
        self._cache: Dict[Any, dict] = {}
        self._ttl_ms = ttl_ms
        self._prune_interval_ms = prune_interval_ms
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._last_prune_at = 0

    def _get_ttl_ms(self) -> int:
        v = self._ttl_ms() if callable(self._ttl_ms) else self._ttl_ms
        return max(0, int(v))

    def _resolve_prune_interval_ms(self, ttl_ms: int) -> int:
        v = self._prune_interval_ms
        if callable(v):
            return max(0, int(v(ttl_ms)))
        if isinstance(v, (int, float)):
            return max(0, int(v))
        return ttl_ms

    def _is_expired(self, stored_at: int, now: int, ttl_ms: int) -> bool:
        return now - stored_at > ttl_ms

    def _maybe_prune(self, now: int, ttl_ms: int) -> None:
        if not is_cache_enabled(ttl_ms):
            return
        if now - self._last_prune_at < self._resolve_prune_interval_ms(ttl_ms):
            return
        for key, entry in list(self._cache.items()):
            if self._is_expired(entry["storedAt"], now, ttl_ms):
                del self._cache[key]
        self._last_prune_at = now

    def get(self, key) -> Optional[TValue]:
        ttl_ms = self._get_ttl_ms()
        if not is_cache_enabled(ttl_ms):
            return None
        now = self._clock()
        self._maybe_prune(now, ttl_ms)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if self._is_expired(entry["storedAt"], now, ttl_ms):
            del self._cache[key]
            return None
        return entry["value"]

    def set(self, key, value) -> None:
        ttl_ms = self._get_ttl_ms()
        if not is_cache_enabled(ttl_ms):
            return
        now = self._clock()
        self._maybe_prune(now, ttl_ms)
        self._cache[key] = {"storedAt": now, "value": value}

    def delete(self, key) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()
        self._last_prune_at = 0

    def keys(self) -> List:
        return list(self._cache.keys())

    def size(self) -> int:
        return len(self._cache)

    def prune_expired(self) -> None:
        ttl_ms = self._get_ttl_ms()
        if not is_cache_enabled(ttl_ms):
            return
        now = self._clock()
        for key, entry in list(self._cache.items()):
            if self._is_expired(entry["storedAt"], now, ttl_ms):
                del self._cache[key]
        self._last_prune_at = now


def create_expiring_map_cache(**kwargs):
    """Convenience factory mirroring OpenClaw's :func:`createExpiringMapCache`."""
    return ExpiringMapCache(**kwargs)


class FileStatSnapshot(dict):
    """File attributes used by cache invalidation without exposing ``os.stat``."""

    def __init__(self, ctime_ns: int, mtime_ns: int, size_bytes: int) -> None:
        super().__init__(ctime_ns=ctime_ns, mtime_ns=mtime_ns, size_bytes=size_bytes)
        self.ctime_ns = ctime_ns
        self.mtime_ns = mtime_ns
        self.size_bytes = size_bytes


def get_file_stat_snapshot(file_path: str) -> Optional[FileStatSnapshot]:
    """Capture file attributes used by cache invalidation.

    Mirrors :func:`getFileStatSnapshot`
    (``shared/config/cache-utils.ts``).
    """
    try:
        st = os.stat(file_path)
    except OSError:
        return None
    # Python's os.stat doesn't expose ctime_ns/mtime_ns attributes directly
    # until 3.8+. Use stat().st_ctime_ns when available.
    ctime_ns = getattr(st, "st_ctime_ns", int(st.st_ctime * 1_000_000_000))
    mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1_000_000_000))
    return FileStatSnapshot(ctime_ns=ctime_ns, mtime_ns=mtime_ns, size_bytes=st.st_size)


__all__ = [
    "ExpiringMapCache",
    "create_expiring_map_cache",
    "FileStatSnapshot",
    "resolve_cache_ttl_ms",
    "is_cache_enabled",
    "get_file_stat_snapshot",
]
