"""jarvis.agents.embedded_agent_runner.session_manager_cache — session-manager cache.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/session-manager-cache.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`track_session_manager_access` — record a session manager
  access (extends the cache TTL).
- :func:`prewarm_session_file` — read a small chunk of the session
  file to encourage OS page-cache warmup.
- :func:`is_session_manager_cached` — return True if the session
  file is currently in the cache.
- :func:`clear_session_manager_cache` — clear the cache.
- :func:`create_session_manager_cache` — factory for tests to
  create a fresh cache with custom TTL / clock / fsModule.

Phase 7.5a — focused minimal port.

The OpenClaw source uses
:func:`createExpiringMapCache` and
:func:`isCacheEnabled` from
``config/cache-utils.js`` and
:func:`parseSqliteSessionFileMarker` from
``config/sessions/sqlite-marker.js``. The Python port keeps the
public surface and implements a simple in-memory LRU cache
backed by the host's ``read_session_file_chunk`` installable
hook so the prewarm flow works without a real expiring-map
cache.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Awaitable, Callable, Optional


#: Default TTL for the session manager cache (45 seconds).
#: Mirrors :data:`DEFAULT_SESSION_MANAGER_TTL_MS``
#: (``session-manager-cache.ts:9``).
DEFAULT_SESSION_MANAGER_TTL_MS: int = 45_000

#: Min prune interval (1 second). Mirrors
#: :data:`MIN_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS``.
MIN_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS: int = 1_000

#: Max prune interval (30 seconds). Mirrors
#: :data:`MAX_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS``.
MAX_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS: int = 30_000


def _resolve_session_manager_cache_prune_interval(
    ttl_ms: int,
) -> int:
    """Resolve the prune interval from the cache TTL.

    Mirrors :func:`resolveSessionManagerCachePruneInterval``
    (``session-manager-cache.ts:13-18``).
    """
    return min(
        max(ttl_ms, MIN_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS),
        MAX_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS,
    )


#: Sqlite session-file-marker parser. The host installs the real
#: :func:`parseSqliteSessionFileMarker`` when the
#: session-marker layer lands. The default returns ``None``
#: (file is not a sqlite marker).
_PARSE_SQLITE_SESSION_FILE_MARKER: Callable[[str], Optional[Dict[str, Any]]] = (
    lambda _path: None
)


def set_parse_sqlite_session_file_marker(
    parser: Callable[[str], Optional[Dict[str, Any]]],
) -> None:
    """Install a custom sqlite session-file-marker parser."""
    global _PARSE_SQLITE_SESSION_FILE_MARKER
    _PARSE_SQLITE_SESSION_FILE_MARKER = parser


#: Async read-file-chunk hook. The host installs the real
#: ``fs.open`` + ``fs.read`` when the filesystem layer lands.
#: The default returns ``False`` (file doesn't exist).
_READ_SESSION_FILE_CHUNK: Callable[[str], Awaitable[bool]] = (
    lambda _path: _default_read_returns_false()
)


async def _default_read_returns_false() -> bool:
    return False


def set_read_session_file_chunk_hook(
    hook: Callable[[str], Awaitable[bool]],
) -> None:
    """Install a custom read-session-file-chunk hook."""
    global _READ_SESSION_FILE_CHUNK
    _READ_SESSION_FILE_CHUNK = hook


#: Process-local session-manager cache. Mirrors the OpenClaw
#: ``Map<sessionFile, true>``.
_SESSION_MANAGER_CACHE: "OrderedDict[str, float]" = OrderedDict()
_SESSION_MANAGER_CACHE_LOCK = threading.Lock()


def _touch(
    cache: "OrderedDict[str, float]",
    session_file: str,
    ttl_ms: int,
    clock: Callable[[], float],
) -> None:
    cache[session_file] = clock() + ttl_ms / 1000.0
    cache.move_to_end(session_file)


def _is_cached(
    cache: "OrderedDict[str, float]",
    session_file: str,
    clock: Callable[[], float],
) -> bool:
    expires_at = cache.get(session_file)
    if expires_at is None:
        return False
    if expires_at < clock():
        cache.pop(session_file, None)
        return False
    return True


def create_session_manager_cache(
    *,
    clock: Optional[Callable[[], float]] = None,
    ttl_ms: Optional[int] = None,
) -> "SessionManagerCache":
    """Create a fresh session manager cache.

    Mirrors :func:`createSessionManagerCache``
    (``session-manager-cache.ts:28-79``).

    Returns a small struct exposing the public surface.
    """
    cache: "OrderedDict[str, float]" = OrderedDict()
    get_clock = clock or time.time
    get_ttl = ttl_ms or DEFAULT_SESSION_MANAGER_TTL_MS

    def _prune() -> None:
        if len(cache) <= _resolve_session_manager_cache_prune_interval(get_ttl):
            return
        target_size = max(1, _resolve_session_manager_cache_prune_interval(get_ttl) // 1000)
        while len(cache) > target_size:
            cache.popitem(last=False)

    async def _prewarm(session_file: str) -> None:
        if get_ttl <= 0:
            return
        if _PARSE_SQLITE_SESSION_FILE_MARKER(session_file):
            return
        with _SESSION_MANAGER_CACHE_LOCK:
            if _is_cached(cache, session_file, get_clock):
                return
        try:
            ok = await _READ_SESSION_FILE_CHUNK(session_file)
            if not ok:
                return
        except Exception:
            return
        with _SESSION_MANAGER_CACHE_LOCK:
            _touch(cache, session_file, get_ttl, get_clock)
            _prune()

    def _track(session_file: str) -> None:
        with _SESSION_MANAGER_CACHE_LOCK:
            _touch(cache, session_file, get_ttl, get_clock)
            _prune()

    return {
        "clear": lambda: cache.clear(),
        "isSessionManagerCached": lambda sf: _is_cached(cache, sf, get_clock),
        "keys": lambda: list(cache.keys()),
        "prewarmSessionFile": _prewarm,
        "trackSessionManagerAccess": _track,
    }


# Type alias for the cache shape returned by
# :func:`create_session_manager_cache`.
SessionManagerCache = Dict[str, Any]


#: Process-wide default session manager cache.
_session_manager_cache: SessionManagerCache = create_session_manager_cache()


def _get_default_cache() -> SessionManagerCache:
    return _session_manager_cache


def track_session_manager_access(session_file: str) -> None:
    """Record a session manager access (extends the cache TTL).

    Mirrors :func:`trackSessionManagerAccess``
    (``session-manager-cache.ts:83-85``).
    """
    _get_default_cache()["trackSessionManagerAccess"](session_file)


async def prewarm_session_file(session_file: str) -> None:
    """Read a small chunk of ``session_file`` to warm up the page cache.

    Mirrors :func:`prewarmSessionFile``
    (``session-manager-cache.ts:87-89``).
    """
    await _get_default_cache()["prewarmSessionFile"](session_file)


def is_session_manager_cached(session_file: str) -> bool:
    """Return True if the session file is in the cache.

    Mirrors :func:`isSessionManagerCached``
    (mirrors the internal ``isSessionManagerCached`` method on
    the cache).
    """
    return _get_default_cache()["isSessionManagerCached"](session_file)


def clear_session_manager_cache() -> None:
    """Clear the process-wide default session manager cache.

    Mirrors the OpenClaw test hook
    ``globalThis[Symbol.for(\"openclaw.sessionManagerCacheTestApi\")].createSessionManagerCache``.
    """
    _get_default_cache()["clear"]()


__all__ = [
    "DEFAULT_SESSION_MANAGER_TTL_MS",
    "MAX_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS",
    "MIN_SESSION_MANAGER_CACHE_PRUNE_INTERVAL_MS",
    "SessionManagerCache",
    "clear_session_manager_cache",
    "create_session_manager_cache",
    "is_session_manager_cached",
    "prewarm_session_file",
    "set_parse_sqlite_session_file_marker",
    "set_read_session_file_chunk_hook",
    "track_session_manager_access",
]
