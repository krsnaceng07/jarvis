"""recall_state — TTL cache + circuit breaker for active-memory.

OpenClaw parity: mirrors ``extensions/active-memory/recall-state.ts``.

Phase 4.2a ships the in-process state primitives the rest of
the plugin needs:

- **TTL cache** — keyed by ``agentId:sessionKeyOrId:query_hash``;
  each entry has an ``expiresAt`` timestamp; the cache
  sweeps expired entries on every Nth write and caps at
  ``DEFAULT_MAX_CACHE_ENTRIES`` (1000).
- **Per-agent/model circuit breaker** — opens after
  ``circuitBreakerMaxTimeouts`` consecutive timeouts for the
  same key; resets after ``circuitBreakerCooldownMs``; one
  attempt is allowed through after the cooldown expires.
- **Log helpers** — single-line collapse + truncate to
  ``MAX_LOG_VALUE_CHARS`` for safe logging of free-form
  values.

The state is module-level (a process-wide singleton), matching
OpenClaw's design. Tests reset the state via
``reset_active_recall_state_for_tests``.

Surface
-------
- ``build_cache_key(params)`` → ``str``
- ``get_cached_result(cache_key)`` → ``dict | None``
- ``set_cached_result(cache_key, result, ttl_ms)`` → ``None``
- ``should_cache_result(result)`` → ``bool``
- ``build_circuit_breaker_key(agent_id, provider?, model?)`` → ``str``
- ``is_circuit_breaker_open(key, max_timeouts, cooldown_ms)`` → ``bool``
- ``record_circuit_breaker_timeout(key)`` → ``None``
- ``reset_circuit_breaker(key)`` → ``None``
- ``get_circuit_breaker_entry(key)`` → ``dict | None``
- ``to_single_line_log_value(value)`` → ``str``
- ``reset_active_recall_state_for_tests()`` → ``None``
"""

# ruff: noqa: S324, PLW0603, N803, N806, C901, PLR0912, PLR0915, S110, S112, SIM105, UP038

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any

from jarvis_sdk import (
    as_date_timestamp_ms,
    resolve_expires_at_ms_from_duration_ms,
    truncate_utf16_safe,
)

from .types import (
    CACHE_SWEEP_INTERVAL_MS,
    DEFAULT_MAX_CACHE_ENTRIES,
    MAX_LOG_VALUE_CHARS,
    ActiveRecallResult,
    CachedActiveRecallResult,
    CircuitBreakerEntry,
)

_log = logging.getLogger("extensions.active_memory.recall_state")

# ── Module-level state ─────────────────────────────────────────────

_lock = threading.Lock()
_active_recall_cache: dict[str, CachedActiveRecallResult] = {}
_timeout_circuit_breaker: dict[str, CircuitBreakerEntry] = {}
_last_active_recall_cache_sweep_at: int = 0


# ── Circuit breaker ────────────────────────────────────────────────


def build_circuit_breaker_key(
    agent_id: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Build the per-agent/model circuit-breaker key.

    Mirrors OpenClaw's ``buildCircuitBreakerKey``. The shape
    is ``<agentId>:<provider-or-unknown>/<model-or-unknown>``.
    """
    return f"{agent_id}:{provider or 'unknown'}/{model or 'unknown'}"


def is_circuit_breaker_open(
    key: str,
    max_timeouts: int,
    cooldown_ms: int,
) -> bool:
    """Return True if the breaker is open for ``key``.

    Mirrors OpenClaw's ``isCircuitBreakerOpen``. Opens
    after ``max_timeouts`` consecutive timeouts; resets
    after ``cooldown_ms``; one attempt is allowed through
    after the cooldown expires.
    """
    entry = _timeout_circuit_breaker.get(key)
    if entry is None or int(entry.get("consecutiveTimeouts", 0)) < max_timeouts:
        return False
    now_ms = _now_ms()
    if now_ms is None:
        return False
    last = int(entry.get("lastTimeoutAt", 0))
    if now_ms - last >= cooldown_ms:
        # Cooldown expired — reset and allow one attempt through.
        _timeout_circuit_breaker.pop(key, None)
        return False
    return True


def record_circuit_breaker_timeout(key: str) -> None:
    """Record a timeout for the breaker keyed by ``key``.

    Mirrors OpenClaw's ``recordCircuitBreakerTimeout``.
    Increments the consecutive-timeouts counter and stamps
    ``lastTimeoutAt`` to now.
    """
    with _lock:
        existing = _timeout_circuit_breaker.get(key)
        if existing is not None:
            existing["consecutiveTimeouts"] = int(existing.get("consecutiveTimeouts", 0)) + 1
            existing["lastTimeoutAt"] = _now_ms_value()
        else:
            _timeout_circuit_breaker[key] = {
                "consecutiveTimeouts": 1,
                "lastTimeoutAt": _now_ms_value(),
            }


def reset_circuit_breaker(key: str) -> None:
    """Clear the breaker entry for ``key``.

    Mirrors OpenClaw's ``resetCircuitBreaker``. Called on
    successful recall.
    """
    with _lock:
        _timeout_circuit_breaker.pop(key, None)


def get_circuit_breaker_entry(key: str) -> CircuitBreakerEntry | None:
    """Return the breaker entry for ``key`` (or ``None``).

    Mirrors OpenClaw's ``getCircuitBreakerEntry``. Test
    helper.
    """
    with _lock:
        entry = _timeout_circuit_breaker.get(key)
        return dict(entry) if entry is not None else None  # type: ignore[return-value]


# ── Cache ───────────────────────────────────────────────────────────


def build_cache_key(params: dict[str, Any]) -> str:
    """Build a cache key for the recall result.

    Mirrors OpenClaw's ``buildCacheKey``. The shape is
    ``<agentId>:<sessionKeyOrIdOrNone>:<sha1(query)>``.
    """
    agent_id = str(params.get("agentId") or "")
    session_key = params.get("sessionKey") or params.get("sessionId")
    query = str(params.get("query") or "")
    digest = hashlib.sha1(query.encode("utf-8")).hexdigest()
    session_part = (
        session_key
        if isinstance(session_key, str) and session_key
        else (params.get("sessionId") if isinstance(params.get("sessionId"), str) else None)
        if params.get("sessionId") is not None
        else "none"
    )
    return f"{agent_id}:{session_part}:{digest}"


def get_cached_result(cache_key: str) -> ActiveRecallResult | None:
    """Return the cached result for ``cache_key`` (or ``None``).

    Mirrors OpenClaw's ``getCachedResult``. Returns
    ``None`` for missing / expired / malformed entries.
    """
    with _lock:
        cached = _active_recall_cache.get(cache_key)
        if cached is None:
            return None
        now_ms = _now_ms()
        expires_at = cached.get("expiresAt")
        if now_ms is None or as_date_timestamp_ms(expires_at) is None or int(expires_at) <= now_ms:
            _active_recall_cache.pop(cache_key, None)
            return None
        return dict(cached.get("result") or {})  # type: ignore[return-value]


def set_cached_result(
    cache_key: str,
    result: ActiveRecallResult,
    ttl_ms: int,
) -> None:
    """Cache ``result`` for ``cache_key`` with ``ttl_ms`` expiry.

    Mirrors OpenClaw's ``setCachedResult``. Sweeps expired
    entries on every Nth write and caps the cache at
    ``DEFAULT_MAX_CACHE_ENTRIES`` (1000).
    """
    global _last_active_recall_cache_sweep_at
    now_ms = _now_ms_value()
    with _lock:
        if (
            len(_active_recall_cache) >= DEFAULT_MAX_CACHE_ENTRIES
            or now_ms - _last_active_recall_cache_sweep_at >= CACHE_SWEEP_INTERVAL_MS
        ):
            _sweep_expired_cache_entries_locked()
            _last_active_recall_cache_sweep_at = now_ms
        expires_at = resolve_expires_at_ms_from_duration_ms(ttl_ms, options={"nowMs": now_ms})
        if expires_at is None:
            _active_recall_cache.pop(cache_key, None)
            return
        # Evict an existing entry to preserve LRU-ish ordering:
        # insertion order is preserved, so re-set bumps to the
        # end of the iteration order. Combined with the cap, this
        # behaves like a bounded LRU without an explicit
        # access-recency map.
        if cache_key in _active_recall_cache:
            _active_recall_cache.pop(cache_key, None)
        _active_recall_cache[cache_key] = {  # type: ignore[typeddict-item]
            "expiresAt": expires_at,
            "result": dict(result),  # type: ignore[arg-type]
        }
        while len(_active_recall_cache) > DEFAULT_MAX_CACHE_ENTRIES:
            oldest_key = next(iter(_active_recall_cache), None)
            if oldest_key is None:
                break
            _active_recall_cache.pop(oldest_key, None)


def _sweep_expired_cache_entries_locked() -> None:
    """Drop expired entries. Caller holds ``_lock``."""
    now_ms = _now_ms()
    if now_ms is None:
        _active_recall_cache.clear()
        return
    expired: list[str] = []
    for cache_key, cached in _active_recall_cache.items():
        expires_at = cached.get("expiresAt")
        if as_date_timestamp_ms(expires_at) is None or int(expires_at) <= now_ms:
            expired.append(cache_key)
    for key in expired:
        _active_recall_cache.pop(key, None)


def should_cache_result(result: ActiveRecallResult) -> bool:
    """Return True if ``result`` is cacheable.

    Mirrors OpenClaw's ``shouldCacheResult``. Only successful
    results with non-empty summaries are cached.
    """
    return (
        result.get("status") == "ok"
        and isinstance(result.get("summary"), str)
        and len(result.get("summary") or "") > 0
    )


# ── Log helpers ─────────────────────────────────────────────────────


def to_single_line_log_value(value: Any) -> str:
    """Collapse ``value`` to a single line + truncate to MAX_LOG_VALUE_CHARS.

    Mirrors OpenClaw's ``toSingleLineLogValue``. Newlines,
    tabs, and runs of whitespace become single spaces; the
    result is truncated with an ellipsis when it exceeds
    ``MAX_LOG_VALUE_CHARS``.
    """
    if isinstance(value, str):
        raw = value
    elif isinstance(value, (int, float, bool)):
        raw = str(value)
    elif value is None:
        raw = ""
    else:
        try:
            raw = json.dumps(value, default=str)
        except Exception:
            raw = str(value)
    single_line = " ".join(raw.split())
    if len(single_line) > MAX_LOG_VALUE_CHARS:
        return f"{truncate_utf16_safe(single_line, MAX_LOG_VALUE_CHARS)}..."
    return single_line


# ── Test helpers ────────────────────────────────────────────────────


def reset_active_recall_state_for_tests() -> None:
    """Clear all module-level state. Tests call this between cases."""
    global _last_active_recall_cache_sweep_at
    with _lock:
        _active_recall_cache.clear()
        _timeout_circuit_breaker.clear()
        _last_active_recall_cache_sweep_at = 0


# ── Memory-search manager cleanup ──────────────────────────────────


def schedule_memory_search_cleanup_after_timeout(
    api: Any,
    log_prefix: str,
    agent_id: str,
) -> None:
    """Schedule an async cleanup of the per-agent memory-search manager.

    Mirrors OpenClaw's ``scheduleMemorySearchCleanupAfterTimeout``.
    Called after a recall timeout so the host can release
    any cached state (LanceDB connection, vector cache, etc.)
    held by the active memory-search manager. Failures are
    logged via ``api.logger.warn`` and never propagate.
    """
    cfg: Any = None
    try:
        runtime_config = getattr(getattr(api, "runtime", None), "config", None)
        if runtime_config is not None and hasattr(runtime_config, "current"):
            cfg = runtime_config.current()
        if cfg is None:
            cfg = getattr(api, "config", None)
    except Exception:
        cfg = getattr(api, "config", None)

    def _cleanup() -> None:
        from jarvis_sdk import close_active_memory_search_manager

        try:
            close_active_memory_search_manager({"cfg": cfg, "agentId": agent_id})
            try:
                api.logger.debug(f"{log_prefix} released memory search managers after timeout")
            except Exception:
                pass
        except Exception as exc:
            try:
                api.logger.warn(
                    f"{log_prefix} failed to release memory search managers after timeout: "
                    f"{to_single_line_log_value(exc)}"
                )
            except Exception:
                pass

    try:
        import asyncio as _asyncio

        try:
            loop = _asyncio.get_running_loop()
            loop.call_soon(_cleanup)
            return
        except RuntimeError:
            pass
    except Exception:
        # If asyncio is unavailable in the caller's context,
        # the cleanup simply doesn't run — the next recall
        # will retry it.
        pass


# ── Internal time helpers ──────────────────────────────────────────


def _now_ms() -> int | None:
    return as_date_timestamp_ms(int(time.time() * 1000))


def _now_ms_value() -> int:
    return int(time.time() * 1000)


__all__ = [
    "build_cache_key",
    "build_circuit_breaker_key",
    "get_cached_result",
    "get_circuit_breaker_entry",
    "is_circuit_breaker_open",
    "record_circuit_breaker_timeout",
    "reset_active_recall_state_for_tests",
    "reset_circuit_breaker",
    "set_cached_result",
    "should_cache_result",
    "to_single_line_log_value",
]
